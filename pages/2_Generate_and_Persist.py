# pages/2_Generate_and_Persist.py
import os, glob
import streamlit as st
from datetime import datetime
import duckdb
import pandas as pd

from hl7_demo.pipeline import run_pipeline
from storage_duckdb_entities import DEFAULT_DB_PATH, init_db

st.set_page_config(page_title="MediLacra — Generate & Persist", layout="wide")
st.title("🗂️ MediLacra — Generate & Persist to DuckDB")

with st.sidebar:
    st.header("Run Settings")
    n = st.number_input("Patients", 1, 10000, 5, key="gp_n")
    seed = st.number_input("Seed (optional)", 0, 10_000_000, 0, key="gp_seed")
    use_seed = st.checkbox("Lock seed", value=False, key="gp_lockseed")
    per_enc = st.toggle("Per-encounter files", value=False, key="gp_perenc")
    report_glob = st.text_input("Report CSV glob", "./input/reports/*.csv", key="gp_glob")
    out_dir = st.text_input("Output folder", "./output", key="gp_outdir")
    include_sdoh = st.checkbox(
        "Include external SDOH enrichment",
        value=False,
        key="gp_sdoh",
        help=(
            "Opt in to AirNow, Census, PLACES, and BLS lookups. "
            "When off, generation stays offline and vitals use neutral local inputs."
        ),
    )
    miles = st.number_input(
        "AirNow radius (miles)",
        1,
        200,
        75,
        key="gp_miles",
        disabled=not include_sdoh,
    )
    db_path = st.text_input("DuckDB path", DEFAULT_DB_PATH, key="gp_db")
    go = st.button("Run & Persist", type="primary", use_container_width=True)
    include_labs = st.checkbox("Include Labs (ORM + ORU)", value=True, key="gp_labs")
    include_x12 = st.checkbox(
        "Include X12 Eligibility (270/271)",
        value=False,
        key="gp_x12",
        help="Generate one X12 270/271 pair per encounter and persist payer primitives.",
    )
    include_fhir_eligibility = st.checkbox(
        "Include FHIR Eligibility (R4 4.0.1)",
        value=False,
        key="gp_fhir_eligibility",
        help=(
            "Generate one FHIR CoverageEligibilityRequest/Response bundle "
            "pair per encounter directly from synthetic reality."
        ),
    )
    add_places_obesity_obx = st.checkbox(
        "Add Places/Obesity OBX to ADT",
        value=False,
        key="gp_places",
        disabled=not include_sdoh,
    )
    add_unemployment_obx = st.checkbox(
        "Add Unemployment OBX to ADT",
        value=False,
        key="gp_unemp",
        disabled=not include_sdoh,
    )
    col1, col2 = st.columns(2)

# Ensure DB/tables exist
init_db(db_path)

if go:
    counts = run_pipeline(
        n_patients=int(n),
        report_glob=report_glob,
        seed=int(seed) if use_seed else None,
        per_encounter=bool(per_enc),
        bulk=not bool(per_enc),
        out_dir=out_dir,
        miles=int(miles),
        add_places_obesity_obx=bool(add_places_obesity_obx),
        add_unemployment_obx=bool(add_unemployment_obx),
        include_labs=bool(include_labs),
        include_sdoh=bool(include_sdoh),
        include_x12=bool(include_x12),
        include_fhir_eligibility=bool(include_fhir_eligibility),
        persist="duckdb",
        duckdb_path=db_path,
    )

    summary = (
        f"Done. ADT: {counts.get('ADT',0)}, "
        f"ORU: {counts.get('ORU',0)}, DFT: {counts.get('DFT',0)}, "
        f"ORM: {counts.get('ORM',0)}, ORU_LABS: {counts.get('ORU_LABS',0)}"
    )
    if include_x12:
        summary += (
            f", X12_270: {counts.get('X12_270',0)}, "
            f"X12_271: {counts.get('X12_271',0)}"
        )
    if include_fhir_eligibility:
        summary += (
            ", FHIR requests: "
            f"{counts.get('FHIR_ELIGIBILITY_REQUEST',0)}, "
            "FHIR responses: "
            f"{counts.get('FHIR_ELIGIBILITY_RESPONSE',0)}"
        )
    st.success(summary)

    # Show recent message files
    recent_paths = (
        glob.glob(os.path.join(out_dir, "*.hl7"))
        + glob.glob(os.path.join(out_dir, "*.x12"))
        + glob.glob(os.path.join(out_dir, "*.json"))
        + glob.glob(os.path.join(out_dir, "*.ndjson"))
    )
    files = sorted(recent_paths, key=os.path.getmtime, reverse=True)[:25]
    st.subheader("Recent message files")
    for f in files:
        st.code(os.path.basename(f))

st.caption("Persists clinical entities/messages plus coverage; payer members, enrollments, and plans are persisted when X12 or FHIR eligibility is enabled. Raw X12/FHIR artifacts remain filesystem-only.")

# -------------------------
# Preview entities section
# -------------------------
st.markdown("---")
st.header("Preview entities")

tables = [
    "patients",
    "coverage_profiles",
    "payer_members",
    "payer_enrollments",
    "payer_plans",
    "encounters",
    "observations",
    "transactions",
    "messages",
]
tab_objs = st.tabs([t.capitalize() for t in tables])

def _fetch_df(table: str, limit: int = 100):
    con = duckdb.connect(db_path)
    try:
        df = con.execute(f"SELECT * FROM {table} LIMIT {int(limit)}").fetchdf()
        return df
    finally:
        con.close()

limits = {t: 50 for t in tables}
for i, table in enumerate(tables):
    with tab_objs[i]:
        st.subheader(table.capitalize())
        limits[table] = st.number_input(f"Limit ({table})", 1, 10000, limits[table], key=f"lim_{table}")
        try:
            df = _fetch_df(table, int(limits[table]))
            if df.empty:
                st.info("No rows yet.")
            else:
                st.dataframe(df)
                csv = df.to_csv(index=False).encode("utf-8")
                st.download_button(
                    label="Download CSV",
                    data=csv,
                    file_name=f"{table}.csv",
                    mime="text/csv",
                    key=f"dl_{table}"
                )
        except Exception as e:
            st.error(str(e))

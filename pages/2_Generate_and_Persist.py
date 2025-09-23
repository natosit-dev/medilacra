# pages/2_Generate_and_Persist.py
import os, glob
import streamlit as st
from datetime import datetime
import duckdb
import pandas as pd

from pipeline_duckdb import run_and_persist
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
    miles = st.number_input("AirNow radius (miles)", 1, 200, 75, key="gp_miles")
    db_path = st.text_input("DuckDB path", DEFAULT_DB_PATH, key="gp_db")
    go = st.button("Run & Persist", type="primary", use_container_width=True)
    include_labs = st.checkbox("Include Labs (ORM + ORU)", value=True, key="gp_labs")
    add_places_obesity_obx = st.checkbox("Add Places/Obesity OBX to ADT", value=False, key="gp_places")
    add_unemployment_obx = st.checkbox("Add Unemployment OBX to ADT", value=False, key="gp_unemp")
    col1, col2 = st.columns(2)

# Ensure DB/tables exist
init_db(db_path)

if go:
    counts = run_and_persist(
        int(n), report_glob, int(seed) if use_seed else None,
        bool(per_enc), not per_enc, out_dir, int(miles), db_path=db_path
    )
    st.success(f"Done. ADT: {counts.get('ADT',0)}, ORU: {counts.get('ORU',0)}, DFT: {counts.get('DFT',0)}")

    # Show recent message files
    files = sorted(glob.glob(os.path.join(out_dir, "*.hl7")), key=os.path.getmtime, reverse=True)[:25]
    st.subheader("Recent message files")
    for f in files:
        st.code(os.path.basename(f))

st.caption("Persists: patients, encounters, observations, transactions, messages (DuckDB).")

# -------------------------
# Preview entities section
# -------------------------
st.markdown("---")
st.header("Preview entities")

tables = ["patients", "encounters", "observations", "transactions", "messages"]
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

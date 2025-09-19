
# pages/5_Generate_and_Persist.py
import os, glob
import streamlit as st
from datetime import datetime
from pipeline_duckdb import run_and_persist
from storage_duckdb_entities import DEFAULT_DB_PATH, init_db

st.set_page_config(page_title="MediLacra — Generate & Persist", layout="wide")
st.title("🗂️ MediLacra — Generate & Persist to DuckDB")

with st.sidebar:
    st.header("Run Settings")
    n = st.number_input("Patients", 1, 10000, 25, key="gp_n")
    seed = st.number_input("Seed (optional)", 0, 10_000_000, 0, key="gp_seed")
    use_seed = st.checkbox("Lock seed", value=False, key="gp_lockseed")
    per_enc = st.toggle("Per-encounter files", value=False, key="gp_perenc")
    report_glob = st.text_input("Report CSV glob", "./input/reports/*.csv", key="gp_glob")
    out_dir = st.text_input("Output folder", "./output", key="gp_outdir")
    miles = st.number_input("AirNow radius (miles)", 1, 200, 75, key="gp_miles")
    db_path = st.text_input("DuckDB path", DEFAULT_DB_PATH, key="gp_db")
    go = st.button("Run & Persist", type="primary", use_container_width=True)

init_db(db_path)

if go:
    counts = run_and_persist(
        int(n), report_glob, int(seed) if use_seed else None,
        bool(per_enc), not per_enc, out_dir, int(miles), db_path=db_path
    )
    st.success(f"Done. ADT: {counts.get('ADT',0)}, ORU: {counts.get('ORU',0)}, DFT: {counts.get('DFT',0)}")
    files = sorted(glob.glob(os.path.join(out_dir, "*.hl7")), key=os.path.getmtime, reverse=True)[:25]
    st.subheader("Recent message files")
    for f in files:
        st.code(os.path.basename(f))
st.caption("Persists: patients, encounters, observations, transactions, messages (DuckDB).")

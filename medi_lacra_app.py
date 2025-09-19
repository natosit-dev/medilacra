
import os
import time
import glob
from datetime import datetime, timedelta

import streamlit as st

# MediLacra (hl7_demo) imports
try:
    from hl7_demo.pipeline import run_pipeline,log_recent_messages_to_bronze
    from hl7_demo.reports import load_reports
    from hl7_demo.refdata import load_zip_table
    from hl7_demo.config import AIRNOW_MILES_DEFAULT
except ModuleNotFoundError:
    # Fallback to local-relative imports if the package name isn't set up
    from pipeline import run_pipeline
    from reports import load_reports
    from refdata import load_zip_table
    from config import AIRNOW_MILES_DEFAULT

st.set_page_config(page_title="MediLacra — HL7 Generator", layout="wide")

st.title("🧪 MediLacra — HL7 Message Generator")
st.caption("Simulated Enriched Medical Data")

with st.sidebar:
    st.header("Run Settings")
    n_patients = st.number_input("Patients to generate", min_value=1, max_value=10000, value=5, step=1)
    seed = st.number_input("Seed (optional)", min_value=0, max_value=10_000_000, value=0, step=1)
    use_seed = st.checkbox("Lock seed", value=False, help="Deterministic runs when checked.")
    per_encounter = st.toggle("Per-encounter files", value=False, help="One file per encounter")
    bulk = not per_encounter
    report_glob = st.text_input("Report CSV glob", "./input/reports/*.csv")
    out_dir = st.text_input("Output folder", "./output")
    miles = st.number_input("AirNow radius (miles)", min_value=1, max_value=200, value=int(AIRNOW_MILES_DEFAULT), step=1)
    run_btn = st.button("Generate Messages", type="primary", use_container_width=True)

# --- Health checks panel ---
col1, col2 = st.columns(2)
with col1:
    st.subheader("Data Sources")
    # Reports
    try:
        df_reports = load_reports(report_glob)
        st.success(f"Reports OK • {len(df_reports):,} rows loaded")
        st.dataframe(df_reports.head(5))
    except Exception as e:
        st.error(f"Reports not ready: {e}")
with col2:
    st.subheader("ZIP Reference")
    try:
        df_zip = load_zip_table()
        st.success(f"ZIP table OK • {len(df_zip):,} rows")
        st.dataframe(df_zip.sample(min(5, len(df_zip))))
    except Exception as e:
        st.error(f"ZIP reference not ready: {e}")

# --- Generate ---
if run_btn:
    os.makedirs(out_dir, exist_ok=True)
    st.info("Starting pipeline...")
    start = time.time()
    with st.spinner("Generating HL7 messages..."):
        counts = run_pipeline(
            int(n_patients),
            report_glob,
            int(seed) if use_seed else None,
            bool(per_encounter),
            bool(bulk),
            out_dir,
            int(miles),
        )
    dur = time.time() - start
    st.success(f"Done in {dur:.2f}s — ADT: {counts.get('ADT',0)}, ORU: {counts.get('ORU',0)}, DFT: {counts.get('DFT',0)}")

    # Show recent files written (last 3 minutes)
    now = time.time()
    rows = []
    for path in glob.glob(os.path.join(out_dir, "*.hl7")):
        try:
            mtime = os.path.getmtime(path)
            rows.append((mtime, path))
        except Exception:
            pass

    if rows:
        rows.sort(reverse=True)
        recent = [(datetime.fromtimestamp(m), p) for m, p in rows if now - m <= 180]
        st.subheader("Recently written files")
        if recent:
            for mtime, path in recent[:200]:
                st.code(f"{mtime:%Y-%m-%d %H:%M:%S}  {os.path.basename(path)}")
        else:
            st.write("No files in the last 3 minutes — showing latest 30 instead.")
            for mtime, path in rows[:30]:
                st.code(f"{datetime.fromtimestamp(mtime):%Y-%m-%d %H:%M:%S}  {os.path.basename(path)}")





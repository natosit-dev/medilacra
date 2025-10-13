import os
import time
import glob
from datetime import datetime
import yaml

import streamlit as st

# --- Logging (from your utils module)
try:
    from utils.log_utils import get_logger  # assumes utils/ is a package (has __init__.py)
except Exception as _e:
    # Minimal fallback so the app still runs if import path isn't ready yet
    import logging
    def get_logger(name="MediLacra", context=None, level=logging.INFO):
        logger = logging.getLogger(name)
        if not logger.handlers:
            logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
        return logger

# MediLacra (hl7_demo) imports
from hl7_demo.pipeline import run_pipeline
from hl7_demo.reports import load_reports
from hl7_demo.refdata import load_zip_table
from hl7_demo.config import AIRNOW_MILES_DEFAULT

try:
    from utils.scenario_profile import load_profile as load_scenario_profile
except Exception:
    load_scenario_profile = None

PROFILE_DIR = "./data/scenario_profiles"

def _list_profiles():
    os.makedirs(PROFILE_DIR, exist_ok=True)
    return sorted([f for f in os.listdir(PROFILE_DIR) if f.lower().endswith(".yaml")])

def _load_profile(filename: str) -> dict:
    if load_scenario_profile:
        return load_scenario_profile(filename)
    path = os.path.join(PROFILE_DIR, filename)
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


st.set_page_config(page_title="MediLacra — HL7 Generator", layout="wide")

# --- App-scoped logger
logger = get_logger(name="MediLacra", context={"component": "app", "module": "medi_lacra_app", "env": "dev"})

st.title("MediLacra — HL7 Message Generator")
st.caption("Simulated Enriched Medical Data")

with st.sidebar:
    st.header("Run Settings")
    n_patients = st.number_input("Patients to generate", min_value=1, max_value=10000, value=5, step=1)
    seed = st.number_input("Seed (optional)", min_value=0, max_value=10_000_000, value=0, step=1)
    use_seed = st.checkbox("Lock seed", value=False, help="Deterministic runs when checked.")
    per_encounter = st.toggle("Per-encounter files", value=False, help="One file per encounter")
    report_glob = st.text_input("Report CSV glob", "./input/reports/*.csv")
    out_dir = st.text_input("Output folder", "./output")
    miles = st.number_input("AirNow radius (miles)", min_value=1, max_value=200, value=int(AIRNOW_MILES_DEFAULT), step=1)
    add_places_obesity_obx = st.checkbox("Include Places/Obesity OBX", value=False)
    add_unemployment_obx = st.checkbox("Include Unemployment OBX", value=False)
    include_labs = st.checkbox("Include Labs (ORM/ORU)", value=True)
    persist = st.radio("Persist to", ["duckdb", "none"], index=0, help="Store entities and messages in DuckDB")
    run_btn = st.button("Generate Messages", type="primary", use_container_width=True)
    st.subheader("Scenario")
    profile_files = ["(none)"] + _list_profiles()
    selected_profile_file = st.selectbox(
        "Scenario Profile",
        profile_files,
        index=0,
        help="YAML saved from the Site & Scenario Setup page"
    )

    scenario_profile = None
    if selected_profile_file != "(none)":
        try:
            scenario_profile = _load_profile(selected_profile_file)
            st.caption(f"Using: {scenario_profile.get('profile_name', selected_profile_file)}")
            logger.info("Scenario profile selected", extra={"extra": {"file": selected_profile_file}})
        except Exception as e:
            st.warning(f"Couldn't load profile: {e}")
            logger.warning("Scenario profile load failed", extra={"extra": {"file": selected_profile_file, "error": str(e)}})

# --- Health checks panel ---
col1, col2 = st.columns(2)
with col1:
    st.subheader("Data Sources")
    # Reports
    try:
        df_reports = load_reports(report_glob)
        st.success(f"Reports OK • {len(df_reports):,} rows loaded")
        st.dataframe(df_reports.head(5))
        logger.info("Reports loaded", extra={"extra": {"glob": report_glob, "rows": int(len(df_reports))}})
    except Exception as e:
        st.error(f"Reports not ready: {e}")
        logger.warning("Reports load failed", extra={"extra": {"glob": report_glob, "error": str(e)}})
with col2:
    st.subheader("ZIP Reference")
    try:
        df_zip = load_zip_table()
        st.success(f"ZIP table OK • {len(df_zip):,} rows")
        st.dataframe(df_zip.sample(min(5, len(df_zip))))
        logger.info("ZIP table loaded", extra={"extra": {"rows": int(len(df_zip))}})
    except Exception as e:
        st.error(f"ZIP reference not ready: {e}")
        logger.warning("ZIP table load failed", extra={"extra": {"error": str(e)}})
    # --- Scenario Profile (optional) ---
   

# --- Generate ---
if run_btn:
    logger.info(
        "Run clicked",
        extra={
            "extra": {
                "patients": int(n_patients),
                "seed_locked": bool(use_seed),
                "seed": int(seed) if use_seed else None,
                "per_encounter": bool(per_encounter),
                "bulk": not bool(per_encounter),
                "report_glob": report_glob,
                "out_dir": out_dir,
                "airnow_miles": int(miles),
                "add_places_obesity_obx": bool(add_places_obesity_obx),
                "add_unemployment_obx": bool(add_unemployment_obx),
                "include_labs": bool(include_labs),
                "persist": persist,
            }
        },
    )

    os.makedirs(out_dir, exist_ok=True)
    st.info("Starting pipeline...")
    start = time.time()
    try:
        with st.spinner("Generating HL7 messages..."):
            counts = run_pipeline(
                n_patients=n_patients,
                report_glob=report_glob,
                seed=seed if use_seed else None,
                per_encounter=per_encounter,
                bulk=not per_encounter,
                out_dir=out_dir,
                miles=miles,
                add_places_obesity_obx=add_places_obesity_obx,
                add_unemployment_obx=add_unemployment_obx,
                include_labs=include_labs,
                persist=persist,
                scenario_profile=scenario_profile
            )
        dur = time.time() - start
        st.success(
            f"Done in {dur:.2f}s — ADT: {counts.get('ADT',0)}, ORU: {counts.get('ORU',0)}, "
            f"DFT: {counts.get('DFT',0)}, ORM: {counts.get('ORM',0)}, ORU_LABS: {counts.get('ORU_LABS',0)}"
        )
        logger.info("Pipeline completed", extra={"extra": {"duration_sec": round(dur, 3), **{k: int(v) for k, v in counts.items()}}})
    except Exception as e:
        dur = time.time() - start
        st.error(f"Pipeline error: {e}")
        logger.error("Pipeline failed", extra={"extra": {"duration_sec": round(dur, 3), "error": str(e)}})

    # Show recent files written (last 3 minutes)
    now = time.time()
    rows = []
    for path in glob.glob(os.path.join(out_dir, "*.hl7")):
        try:
            mtime = os.path.getmtime(path)
            rows.append((mtime, path))
        except Exception as e:
            logger.debug("Error reading file mtime", extra={"extra": {"path": path, "error": str(e)}})

    if rows:
        rows.sort(key=lambda x: x[0], reverse=True)
        recent = [p for m, p in rows if now - m <= 180]
        st.subheader("Recently written files")
        if recent:
            for path in recent[:200]:
                mtime = os.path.getmtime(path)
                st.code(f"{datetime.fromtimestamp(mtime):%Y-%m-%d %H:%M:%S}  {os.path.basename(path)}")
            logger.info("Recent files listed", extra={"extra": {"recent_count": len(recent), "window_sec": 180}})
        else:
            st.info("No files found in the last 3 minutes. Showing the latest 30 files instead.")
            for mtime, path in rows[:30]:
                st.code(f"{datetime.fromtimestamp(mtime):%Y-%m-%d %H:%M:%S}  {os.path.basename(path)}")
            logger.info("Fallback file listing shown", extra={"extra": {"listed_count": min(30, len(rows))}})
    else:
        logger.info("No HL7 files found to list", extra={"extra": {"out_dir": out_dir}})

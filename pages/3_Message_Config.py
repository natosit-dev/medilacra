# pages/3_Message_Config.py

import random
from datetime import datetime

import streamlit as st

# Reuse your app's import pattern (falls back if hl7_demo not installed as a package)

from hl7_demo.reports import load_reports
from hl7_demo.refdata import load_zip_table
from hl7_demo.generators import gen_patient, gen_encounter, gen_observation
from hl7_demo.messages import build_adt, build_oru, build_dft


st.set_page_config(page_title="MediLacra — Message Configurator", layout="wide")
st.title("🧩 HL7 Message Configurator")
st.caption("Turn knobs, see the message change. Save presets for quick reuse.")

with st.sidebar:
    st.header("Inputs")
    # Data inputs
    report_glob = st.text_input("Report CSV glob", "./input/reports/*.csv")
    # Message selection
    msg_type = st.selectbox("Message type", ["ADT^A01", "ORU^R01", "DFT^P03"])
    # Determinism
    lock_seed = st.checkbox("Lock seed (deterministic)", value=False)
    seed_val = st.number_input("Seed", min_value=0, max_value=10_000_000, value=42, step=1, disabled=not lock_seed)

    st.divider()
    st.subheader("SDOH Options (ADT only)")
    add_air_obx = st.checkbox("Include Air Quality OBX", value=True, help="LOINC-coded air quality OBX tied to ZIP")
    add_poverty_obx = st.checkbox("Include Poverty % OBX", value=True)
    add_places_obesity_obx = st.checkbox("Include PLACES Obesity % OBX", value=False)
    add_unemployment_obx = st.checkbox("Include Unemployment % OBX", value=False)

    st.subheader("Gender Harmony (ADT only)")
    add_gi_obx = st.checkbox("Gender Identity (LOINC 76691-5)", value=True)
    add_pronouns_obx = st.checkbox("Personal Pronouns (LOINC 90778-2)", value=True)
    add_spcu_obx = st.checkbox("SPCU (HL7 THO)", value=True)

    st.divider()
    st.subheader("Presets")
    preset_name = st.text_input("Preset name", placeholder="e.g., Demo – Full SDOH + GH")
    save_btn = st.button("Save preset")
    load_list = st.selectbox("Load saved preset", ["—"] + sorted(st.session_state.get("ml_presets", {}).keys()))
    load_btn = st.button("Apply preset")

# Handle presets in-session
if "ml_presets" not in st.session_state:
    st.session_state.ml_presets = {}

if save_btn and preset_name.strip():
    st.session_state.ml_presets[preset_name.strip()] = dict(
        msg_type=msg_type,
        add_air_obx=add_air_obx,
        add_poverty_obx=add_poverty_obx,
        add_places_obesity_obx=add_places_obesity_obx,
        add_unemployment_obx=add_unemployment_obx,
        add_gi_obx=add_gi_obx,
        add_pronouns_obx=add_pronouns_obx,
        add_spcu_obx=add_spcu_obx,
        lock_seed=lock_seed,
        seed_val=int(seed_val),
        report_glob=report_glob,
    )
    st.success(f"Saved preset: {preset_name}")

if load_btn and load_list != "—":
    conf = st.session_state.ml_presets[load_list]
    msg_type = conf["msg_type"]
    add_air_obx = conf["add_air_obx"]
    add_poverty_obx = conf["add_poverty_obx"]
    add_places_obesity_obx = conf["add_places_obesity_obx"]
    add_unemployment_obx = conf["add_unemployment_obx"]
    add_gi_obx = conf["add_gi_obx"]
    add_pronouns_obx = conf["add_pronouns_obx"]
    add_spcu_obx = conf["add_spcu_obx"]
    lock_seed = conf["lock_seed"]
    seed_val = conf["seed_val"]
    report_glob = conf["report_glob"]
    st.info(f"Applied preset: {load_list}")

# Load data sources (mirrors your main page UX)
colA, colB = st.columns(2)
with colA:
    st.subheader("Reports")
    try:
        df_reports = load_reports(report_glob)
        st.success(f"Reports OK • {len(df_reports):,} rows")
        st.dataframe(df_reports.head(5), use_container_width=True)
    except Exception as e:
        df_reports = None
        st.error(f"Reports not ready: {e}")

with colB:
    st.subheader("ZIP Reference")
    try:
        df_zip = load_zip_table()
        st.success(f"ZIP table OK • {len(df_zip):,} rows")
        st.dataframe(df_zip.sample(min(5, len(df_zip))), use_container_width=True)
    except Exception as e:
        st.error(f"ZIP reference not ready: {e}")

st.divider()
st.subheader("Preview Message")

# Generate one synthetic patient/encounter and one observation from reports
if lock_seed:
    random.seed(int(seed_val))

if df_reports is None or len(df_reports) == 0:
    st.warning("No report rows available. Add CSV(s) to ./input/reports or adjust the glob.")
else:
    # Pick one report deterministically if seed locked
    idx = 0 if lock_seed else random.randint(0, len(df_reports) - 1)
    rep_row = df_reports.iloc[idx].to_dict()

    p = gen_patient()
    enc = gen_encounter(p.patient_id)
    obs = gen_observation(enc, rep_row)

    if msg_type.startswith("ADT"):
        # Build ADT using your configurable flags (these map 1:1 to your builder)
        # NOTE: build_adt already appends vitals, SDOH, and Gender Harmony OBXs when enabled.
        msg = build_adt(
            p, enc,
            add_air_obx=add_air_obx,
            add_poverty_obx=add_poverty_obx,
            add_places_obesity_obx=add_places_obesity_obx,
            add_unemployment_obx=add_unemployment_obx,
            add_gi_obx=add_gi_obx,
            add_pronouns_obx=add_pronouns_obx,
            add_spcu_obx=add_spcu_obx,
            obs=obs,  # allows DG1 timing behavior to use obs.completed_time when present
        )
    elif msg_type.startswith("ORU"):
        msg = build_oru(p, enc, [obs])
    else:
        # DFT uses FT1 + DG1s derived from obs_list
        msg = build_dft(p, enc, txs=[], obs_list=[obs])

    # Display some quick facts & the HL7
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Patient", p.patient_id)
    c2.metric("Encounter", enc.visit_number)
    c3.metric("Selected Report Row", f"{idx+1:,}/{len(df_reports):,}")
    c4.metric("Message Type", msg_type)

    st.code(msg, language="hl7")

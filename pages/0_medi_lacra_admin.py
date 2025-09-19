
import os
import json
import streamlit as st

# Try package-style imports first, then local fallbacks
try:
    from hl7_demo.sdoh import (
        get_air_quality_by_zip, build_obx_air_quality,
        get_poverty_pct_by_zcta, build_obx_poverty_pct,
        get_police_station_count_by_zip, build_obx_police_count,
    )
    from hl7_demo.vitals import predict_vitals, build_obx_vitals
    from hl7_demo.config import AIRNOW_API_KEY, AIRNOW_MILES_DEFAULT, ACS_YEAR
except ModuleNotFoundError:
    from sdoh import (
        get_air_quality_by_zip, build_obx_air_quality,
        get_poverty_pct_by_zcta, build_obx_poverty_pct,
        get_police_station_count_by_zip, build_obx_police_count,
    )
    from vitals import predict_vitals, build_obx_vitals
    from config import AIRNOW_API_KEY, AIRNOW_MILES_DEFAULT, ACS_YEAR

st.set_page_config(page_title="MediLacra — Admin / API Tester", layout="wide")
st.title("🔧 MediLacra — Admin / API Tester")
st.caption("Probe SDOH APIs and the demo vitals model, and preview OBX segments.")

with st.sidebar:
    st.header("Global Settings")
    default_key = os.getenv("AIRNOW_API_KEY", "") or AIRNOW_API_KEY
    airnow_key = st.text_input("AirNow API Key", default_key, type="password")
    miles = st.number_input("AirNow radius (miles)", min_value=1, max_value=200, value=int(AIRNOW_MILES_DEFAULT), step=1)
    st.caption(f"ACS Year: {ACS_YEAR}")

tab_aqi, tab_poverty, tab_police, tab_vitals = st.tabs(["AirNow AQI", "Census Poverty %", "ESRI Police Count", "Vitals Model"])

# --- AirNow AQI ---
with tab_aqi:
    st.subheader("AirNow (Current Conditions by ZIP)")
    c1, c2 = st.columns(2)
    with c1:
        zip_code = st.text_input("ZIP code", "02139")
    with c2:
        run_aqi = st.button("Fetch AQI", type="primary")
    if run_aqi:
        # Respect override by temporarily setting env var (sdoh module reads constant but also checks truthiness of key)
        os.environ["AIRNOW_API_KEY"] = airnow_key or ""
        data = get_air_quality_by_zip(zip_code, miles=miles)
        st.write("**Raw Response**")
        st.json(data if data else {"note": "No data returned"})
        st.write("**OBX Preview**")
        st.code(build_obx_air_quality(data) or "(no OBX built)")

# --- Census Poverty % ---
with tab_poverty:
    st.subheader("Census ACS (Poverty % by ZCTA)")
    c1, c2 = st.columns(2)
    with c1:
        zcta = st.text_input("ZCTA (5-digit ZIP)", "02139", key="zcta")
    with c2:
        run_pov = st.button("Fetch Poverty %", type="primary")
    if run_pov:
        pct = get_poverty_pct_by_zcta(zcta)
        st.write("**Raw Value**")
        st.write({"poverty_pct": pct})
        st.write("**OBX Preview**")
        st.code(build_obx_poverty_pct(pct) or "(no OBX built)")

# --- ESRI Police Station Count ---
with tab_police:
    st.subheader("ArcGIS (Police Station Count by ZIP)")
    c1, c2 = st.columns(2)
    with c1:
        zip5 = st.text_input("ZIP code (5-digit)", "02139", key="zip5")
    with c2:
        run_pol = st.button("Fetch Count", type="primary")
    if run_pol:
        cnt = get_police_station_count_by_zip(zip5)
        st.write("**Raw Value**")
        st.write({"station_count": cnt})
        st.write("**OBX Preview**")
        st.code(build_obx_police_count(cnt))

# --- Demo Vitals Model ---
with tab_vitals:
    st.subheader("Demo Vitals Model → LOINC OBXs")
    c1, c2, c3 = st.columns(3)
    with c1:
        age = st.number_input("Age", min_value=18, max_value=95, value=50, step=1)
    with c2:
        pov = st.number_input("Poverty %", min_value=0.0, max_value=100.0, value=15.0, step=0.5)
    with c3:
        aqi = st.number_input("Air Quality (AQI)", min_value=0.0, max_value=500.0, value=60.0, step=1.0)
    if st.button("Predict Vitals", type="primary"):
        vitals = predict_vitals(int(age), float(pov), float(aqi))
        st.write("**Predicted Values**")
        st.json(vitals)
        st.write("**OBX Preview**")
        for obx in build_obx_vitals(vitals):
            st.code(obx)

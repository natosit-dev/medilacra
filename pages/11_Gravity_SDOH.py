from __future__ import annotations

import json
from dataclasses import asdict

import streamlit as st

from connectathon.gravity_sdoh import (
    QUESTIONNAIRE_URL, QUESTIONNAIRE_VERSION, build_artifact_files,
    build_artifact_zip, build_questionnaire, build_questionnaire_response,
    build_sdoh_oru, build_submission_bundle, derive_hvs_risk,
    load_questionnaire_responses, save_questionnaire_response, sdoh_quality_gate,
)
from connectathon.gravity_sdoh_questionnaire import display_for
from connectathon.gravity_sdoh_terminology import (
    HOUSING, HOUSING_WORRY, HVS_Q1, HVS_Q2, HVS_RISK,
    MATERIAL_NEEDS, SOCIAL, STRESS, TRANSPORT,
)
from hl7_demo.generators import gen_patient
from storage_duckdb_entities import DEFAULT_DB_PATH, init_db, upsert_patient
from utils.db import reader

st.set_page_config(page_title="MediLacra — Gravity SDOH",layout="wide")
st.title("Gravity — SDOH Baseline")
st.caption("Standard questions. Preserve the response. See what survives.")

def _load_patients(db_path: str, limit: int=100) -> list[dict]:
    with reader(db_path=db_path) as connection:
        rows=connection.execute(
            """SELECT patient_id, mrn, patient_name, date_of_birth, sex, race,
                      ssn, phone, address, city, state, zip
               FROM patients ORDER BY created_ts DESC LIMIT ?""",
            [int(limit)],
        ).fetchall()
    columns=["patient_id","mrn","patient_name","date_of_birth","sex","race","ssn","phone","address","city","state","zip"]
    return [dict(zip(columns,row)) for row in rows]

def _reset() -> None:
    preserve={"sd_db_path","sd_patient","sd_reset"}
    for key in list(st.session_state.keys()):
        if key.startswith("sd_") and key not in preserve:
            del st.session_state[key]

def _decline(code: str) -> bool:
    state=f"sd_declined_{code}"
    st.session_state.setdefault(state,False)
    label="Answer instead" if st.session_state[state] else "Decline"
    if st.button(label,key=f"sd_decline_button_{code}",use_container_width=True):
        st.session_state[state]=not st.session_state[state]
        st.rerun()
    if st.session_state[state]:
        st.caption("Declined — preserved as DataAbsentReason asked-declined.")
    return bool(st.session_state[state])

def _label(question_code: str, code: str | None) -> str:
    return "Choose an answer" if code is None else (display_for(question_code,code) or code)

def _json_download(label: str, filename: str, value: dict, key: str) -> None:
    st.download_button(label,data=json.dumps(value,indent=2,sort_keys=True,default=str),
                       file_name=filename,mime="application/fhir+json",key=key)

from connectathon.gravity_sdoh_questionnaire import SPECS

reset_cols=st.columns([1,4])
with reset_cols[0]:
    st.button("Reset assessment",key="sd_reset",on_click=_reset,use_container_width=True)

with st.sidebar:
    st.header("Baseline settings")
    db_path=st.text_input("DuckDB path",DEFAULT_DB_PATH,key="sd_db_path")
    st.write(f"Questionnaire version: **{QUESTIONNAIRE_VERSION}**")
    st.write("Instrument: **Hunger Vital Sign + PRAPARE basics**")

init_db(db_path)
patients=_load_patients(db_path)

st.subheader("1. Synthetic patient")
patient_cols=st.columns([4,1])
with patient_cols[1]:
    if st.button("Generate patient",type="secondary",use_container_width=True):
        generated=gen_patient()
        upsert_patient(asdict(generated),db_path=db_path)
        st.rerun()

if not patients:
    st.info("No synthetic patients are persisted yet. Generate one to start.")
    st.stop()

lookup={str(patient["patient_id"]):patient for patient in patients}
selected_patient_id=st.selectbox(
    "Patient",options=list(lookup),
    format_func=lambda pid:f"{pid} — {lookup[pid].get('patient_name') or 'Unnamed synthetic patient'}",
    key="sd_patient",
)
patient=lookup[selected_patient_id]

def _single(code: str) -> tuple[str | None,bool]:
    cols=st.columns([4,1])
    with cols[1]:
        declined=_decline(code)
    options=[None,*[value for value,_display in SPECS[code][1]]]
    with cols[0]:
        value=st.selectbox(
            SPECS[code][0],options=options,
            format_func=lambda answer:_label(code,answer),
            disabled=declined,key=f"sd_value_{code}",
        )
    return value,declined

def _multi(code: str) -> tuple[list[str],bool]:
    cols=st.columns([4,1])
    with cols[1]:
        declined=_decline(code)
    options=[value for value,_display in SPECS[code][1]]
    with cols[0]:
        value=st.multiselect(
            SPECS[code][0],options=options,
            format_func=lambda answer:display_for(code,answer) or answer,
            disabled=declined,key=f"sd_value_{code}",
        )
    return value,declined

st.divider()
st.subheader("2. SDOH Baseline")

st.markdown("#### Hunger Vital Sign")
hvs1,hvs1_declined=_single(HVS_Q1)
hvs2,hvs2_declined=_single(HVS_Q2)
live_declined={code for code,flag in ((HVS_Q1,hvs1_declined),(HVS_Q2,hvs2_declined)) if flag}
live_risk=derive_hvs_risk({HVS_Q1:hvs1,HVS_Q2:hvs2},live_declined)
if live_risk:
    st.info(f"Food insecurity risk — **{display_for(HVS_RISK,live_risk)}** (computed)")
else:
    st.caption("Food insecurity risk — not computed until the available answers support a result.")

st.markdown("#### Housing")
housing,housing_declined=_single(HOUSING)
housing_worry,housing_worry_declined=_single(HOUSING_WORRY)

st.markdown("#### Money and resources")
material,material_declined=_multi(MATERIAL_NEEDS)
transport,transport_declined=_multi(TRANSPORT)

st.markdown("#### Social and emotional health")
social,social_declined=_single(SOCIAL)
stress,stress_declined=_single(STRESS)

st.divider()
submit=st.button("Submit assessment",type="primary",use_container_width=True)

if submit:
    declined={
        code for code,flag in (
            (HVS_Q1,hvs1_declined),(HVS_Q2,hvs2_declined),
            (HOUSING,housing_declined),(HOUSING_WORRY,housing_worry_declined),
            (MATERIAL_NEEDS,material_declined),(TRANSPORT,transport_declined),
            (SOCIAL,social_declined),(STRESS,stress_declined),
        ) if flag
    }
    raw_input={
        HVS_Q1:hvs1,HVS_Q2:hvs2,HOUSING:housing,
        HOUSING_WORRY:housing_worry,MATERIAL_NEEDS:material,
        TRANSPORT:transport,SOCIAL:social,STRESS:stress,
    }
    response=build_questionnaire_response(selected_patient_id,raw_input,declined=declined)
    bundle,cleanup=build_submission_bundle(patient,response)
    hl7v2=build_sdoh_oru(patient,response)
    quality=sdoh_quality_gate(bundle)
    save_questionnaire_response(response,raw_input,bundle=bundle,db_path=db_path)
    st.session_state.sd_last_result={
        "questionnaire":build_questionnaire(),
        "questionnaire_response":response,
        "bundle":bundle,
        "hl7v2":hl7v2,
        "cleanup":cleanup,
        "quality":quality,
    }
    if quality["status"]=="PASS":
        st.success("SDOH baseline materialized. Semantic/conformance checks passed.")
    else:
        st.warning("Assessment was preserved, but one or more checks failed.")

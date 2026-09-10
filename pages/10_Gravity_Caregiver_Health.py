from __future__ import annotations

import json
from dataclasses import asdict

import streamlit as st

from connectathon.gravity_caregiver import build_artifact_files, build_artifact_zip
from connectathon.gravity_materialize import build_submission_bundle
from connectathon.gravity_quality import caregiver_quality_gate
from connectathon.gravity_questionnaire import PHQ_CHOICES, QUESTIONNAIRE_VERSION, build_questionnaire
from connectathon.gravity_response import build_questionnaire_response
from connectathon.gravity_storage import (
    init_questionnaire_storage,
    load_questionnaire_responses,
    save_questionnaire_response,
)
from hl7_demo.generators import gen_patient
from storage_duckdb_entities import DEFAULT_DB_PATH, init_db, upsert_patient
from utils.db import reader


st.set_page_config(page_title="MediLacra — Gravity Caregiver Health", layout="wide")
st.title("Gravity — Caregiver Health Baseline")
st.caption(
    "One boring questionnaire. Preserve the response, materialize standard FHIR, "
    "then check whether the facts survived."
)


def _load_patients(db_path: str, limit: int = 100) -> list[dict]:
    with reader(db_path=db_path) as connection:
        rows = connection.execute(
            """
            SELECT patient_id, mrn, patient_name, date_of_birth, sex, race,
                   ssn, phone, address, city, state, zip
            FROM patients
            ORDER BY created_ts DESC
            LIMIT ?
            """,
            [int(limit)],
        ).fetchall()
    columns = [
        "patient_id",
        "mrn",
        "patient_name",
        "date_of_birth",
        "sex",
        "race",
        "ssn",
        "phone",
        "address",
        "city",
        "state",
        "zip",
    ]
    return [dict(zip(columns, row)) for row in rows]


def _reset_assessment_state() -> None:
    """Reset caregiver questionnaire controls/results while preserving DB and patient selection."""
    preserve = {"cg_db_path", "cg_patient", "cg_reset_assessment"}
    for key in list(st.session_state.keys()):
        if key.startswith("cg_") and key not in preserve:
            del st.session_state[key]


def _decline_control(link_id: str, label: str = "Decline") -> bool:
    state_key = f"cg_declined_{link_id}"
    st.session_state.setdefault(state_key, False)
    button_label = "Answer instead" if st.session_state[state_key] else label
    if st.button(button_label, key=f"cg_decline_button_{link_id}", use_container_width=True):
        st.session_state[state_key] = not st.session_state[state_key]
        st.rerun()
    if st.session_state[state_key]:
        st.caption("Declined — stored as FHIR DataAbsentReason `asked-declined`.")
    return bool(st.session_state[state_key])


def _json_download(label: str, filename: str, value: dict, key: str) -> None:
    st.download_button(
        label,
        data=json.dumps(value, indent=2, sort_keys=True, default=str),
        file_name=filename,
        mime="application/fhir+json",
        key=key,
    )


reset_columns = st.columns([1, 4])
with reset_columns[0]:
    st.button(
        "Reset assessment",
        key="cg_reset_assessment",
        on_click=_reset_assessment_state,
        use_container_width=True,
    )

with st.sidebar:
    st.header("Baseline settings")
    db_path = st.text_input("DuckDB path", DEFAULT_DB_PATH, key="cg_db_path")
    st.write(f"Questionnaire version: **{QUESTIONNAIRE_VERSION}**")
    st.write("IRIS round trip: **Phase 2**")

init_db(db_path)
init_questionnaire_storage(db_path)
patients = _load_patients(db_path)

st.subheader("1. Synthetic caregiver")
patient_columns = st.columns([4, 1])
with patient_columns[1]:
    if st.button("Generate patient", type="secondary", use_container_width=True):
        generated_patient = gen_patient()
        upsert_patient(asdict(generated_patient), db_path=db_path)
        st.rerun()

if not patients:
    st.info("No synthetic patients are persisted yet. Generate one to start the questionnaire.")
    st.stop()

patient_lookup = {str(patient["patient_id"]): patient for patient in patients}
selected_patient_id = st.selectbox(
    "Patient",
    options=list(patient_lookup),
    format_func=lambda patient_id: (
        f"{patient_id} — {patient_lookup[patient_id].get('patient_name') or 'Unnamed synthetic patient'}"
    ),
    key="cg_patient",
)
patient = patient_lookup[selected_patient_id]

st.divider()
st.subheader("2. Caregiver Health Baseline")

st.markdown("#### Sleep")
sleep_columns = st.columns([4, 1])
with sleep_columns[1]:
    sleep_declined = _decline_control("sleep-hours")
with sleep_columns[0]:
    sleep_raw = st.text_input(
        "About how many hours did you sleep in the past 24 hours?",
        value="",
        placeholder="e.g. 6.5",
        disabled=sleep_declined,
        key="cg_sleep_hours",
    )

st.markdown("#### Pain")
pain_columns = st.columns([4, 1])
with pain_columns[1]:
    pain_declined = _decline_control("pain-score")
with pain_columns[0]:
    pain_raw = st.selectbox(
        "On a scale from 0 to 10, where 0 means no pain and 10 means the worst pain imaginable, how would you rate your pain right now?",
        options=[None, *range(0, 11)],
        format_func=lambda value: "Choose a score" if value is None else str(value),
        disabled=pain_declined,
        key="cg_pain_score",
    )

st.markdown("#### PHQ-2")
st.caption("Over the last 2 weeks, how often have you been bothered by the following problems?")
phq_labels = {code: display for code, display, _score in PHQ_CHOICES}
phq_options = [None, *[code for code, _display, _score in PHQ_CHOICES]]

phq1_columns = st.columns([4, 1])
with phq1_columns[1]:
    phq1_declined = _decline_control("phq2-interest")
with phq1_columns[0]:
    phq1_raw = st.selectbox(
        "Little interest or pleasure in doing things",
        options=phq_options,
        format_func=lambda code: "Choose an answer" if code is None else phq_labels[code],
        disabled=phq1_declined,
        key="cg_phq1",
    )

phq2_columns = st.columns([4, 1])
with phq2_columns[1]:
    phq2_declined = _decline_control("phq2-depressed")
with phq2_columns[0]:
    phq2_raw = st.selectbox(
        "Feeling down, depressed, or hopeless",
        options=phq_options,
        format_func=lambda code: "Choose an answer" if code is None else phq_labels[code],
        disabled=phq2_declined,
        key="cg_phq2",
    )

st.markdown("#### Heart rate")
heart_columns = st.columns([4, 1])
with heart_columns[1]:
    heart_declined = _decline_control("heart-rate")
with heart_columns[0]:
    heart_raw = st.text_input(
        "What is your current heart rate?",
        value="",
        placeholder="e.g. 82",
        disabled=heart_declined,
        key="cg_heart_rate",
    )
    st.caption("Enter beats/minute. Clinical abnormality is not treated as invalid data.")

st.markdown("#### Medication reconciliation")
medication_columns = st.columns([4, 1])
with medication_columns[1]:
    medication_declined = _decline_control("medication-status")
with medication_columns[0]:
    medication_status_raw = st.selectbox(
        "Are you currently taking any medications?",
        options=[None, True, False],
        format_func=lambda value: "Choose an answer" if value is None else ("Yes" if value else "No"),
        disabled=medication_declined,
        key="cg_medication_status",
    )

medications: list[dict] = []
if medication_status_raw is True and not medication_declined:
    st.session_state.setdefault("cg_medication_count", 1)
    count_columns = st.columns([1, 1, 4])
    with count_columns[0]:
        if st.button("+ Add medication", use_container_width=True):
            st.session_state.cg_medication_count += 1
            st.rerun()
    with count_columns[1]:
        if st.button(
            "− Remove last",
            disabled=st.session_state.cg_medication_count <= 1,
            use_container_width=True,
        ):
            st.session_state.cg_medication_count -= 1
            st.rerun()

    for index in range(int(st.session_state.cg_medication_count)):
        st.markdown(f"**Medication {index + 1}**")
        row1 = st.columns([4, 1, 1])
        with row1[0]:
            name = st.text_input(
                "Medication",
                placeholder="e.g. lisinopril",
                key=f"cg_med_name_{index}",
            )
        with row1[1]:
            dose_value = st.text_input("Dose", key=f"cg_med_dose_{index}")
        with row1[2]:
            dose_unit = st.text_input("Unit", placeholder="Example: mg", key=f"cg_med_unit_{index}")

        row2 = st.columns(2)
        with row2[0]:
            route = st.selectbox(
                "Route",
                options=["", "oral", "inhaled", "injection", "topical", "other"],
                key=f"cg_med_route_{index}",
            )
        with row2[1]:
            frequency = st.text_input(
                "Frequency",
                placeholder="e.g. daily",
                key=f"cg_med_frequency_{index}",
            )

        medications.append(
            {
                "name": name,
                "dose_value": dose_value,
                "dose_unit": dose_unit,
                "route": route,
                "frequency": frequency,
            }
        )

st.markdown("#### How are you feeling today?")
feeling_columns = st.columns([4, 1])
with feeling_columns[1]:
    feeling_declined = _decline_control("feeling-today")
with feeling_columns[0]:
    feeling_today_raw = st.text_area(
        "How are you feeling today?",
        value="",
        placeholder="Write as much or as little as you want.",
        disabled=feeling_declined,
        key="cg_feeling_today",
        label_visibility="collapsed",
    )

st.markdown("#### What's going on in your life today?")
life_columns = st.columns([4, 1])
with life_columns[1]:
    life_declined = _decline_control("life-today")
with life_columns[0]:
    life_today_raw = st.text_area(
        "What's going on in your life today?",
        value="",
        placeholder="Anything that feels relevant today.",
        disabled=life_declined,
        key="cg_life_today",
        label_visibility="collapsed",
    )

st.divider()
submit = st.button("Submit assessment", type="primary", use_container_width=True)

if submit:
    declined = {
        link_id
        for link_id, is_declined in {
            "sleep-hours": sleep_declined,
            "pain-score": pain_declined,
            "phq2-interest": phq1_declined,
            "phq2-depressed": phq2_declined,
            "heart-rate": heart_declined,
            "medication-status": medication_declined,
            "feeling-today": feeling_declined,
            "life-today": life_declined,
        }.items()
        if is_declined
    }

    raw_input = {
        "sleep-hours": sleep_raw,
        "pain-score": pain_raw,
        "phq2-interest": phq1_raw,
        "phq2-depressed": phq2_raw,
        "heart-rate": heart_raw,
        "medication-status": medication_status_raw,
        "medications": medications,
        "feeling-today": feeling_today_raw,
        "life-today": life_today_raw,
    }

    questionnaire_response = build_questionnaire_response(
        selected_patient_id,
        raw_input,
        declined=declined,
    )
    bundle, cleanup = build_submission_bundle(patient, questionnaire_response)
    quality = caregiver_quality_gate(bundle)

    save_questionnaire_response(
        questionnaire_response,
        raw_input,
        bundle=bundle,
        db_path=db_path,
    )

    st.session_state.cg_last_result = {
        "questionnaire": build_questionnaire(),
        "questionnaire_response": questionnaire_response,
        "bundle": bundle,
        "cleanup": cleanup,
        "quality": quality,
    }

    if quality["status"] == "PASS":
        st.success("Baseline materialized. Local plausibility/conformance checks passed.")
    else:
        st.warning("Assessment was preserved, but one or more plausibility/conformance checks failed.")

result = st.session_state.get("cg_last_result")
if result:
    st.divider()
    st.subheader("3. Materialized artifacts")

    artifact_files = build_artifact_files(result)
    st.download_button(
        "Download all artifacts (.zip)",
        data=build_artifact_zip(result),
        file_name="caregiver_health_phase1_artifacts.zip",
        mime="application/zip",
        key="cg_download_all_artifacts",
        use_container_width=True,
    )
    st.caption(
        "ZIP contains the same individually downloadable Questionnaire, QuestionnaireResponse, "
        "FHIR Bundle, quality report, and Bundle-cleanup receipt shown below."
    )

    tab_questionnaire, tab_response, tab_bundle, tab_quality = st.tabs(
        ["Questionnaire", "QuestionnaireResponse", "FHIR Bundle", "PIQITT-style checks"]
    )

    with tab_questionnaire:
        st.json(result["questionnaire"])
        _json_download(
            "Download Questionnaire",
            f"caregiver_health_baseline_questionnaire_v{QUESTIONNAIRE_VERSION}.json",
            result["questionnaire"],
            "cg_download_questionnaire",
        )

    with tab_response:
        st.json(result["questionnaire_response"])
        _json_download(
            "Download QuestionnaireResponse",
            "caregiver_health_questionnaire_response.json",
            result["questionnaire_response"],
            "cg_download_response",
        )

    with tab_bundle:
        st.caption(f"Existing Connectathon bundle cleanup: {result['cleanup']}")
        st.json(result["bundle"])
        _json_download(
            "Download Bundle",
            "caregiver_health_phase1_bundle.json",
            result["bundle"],
            "cg_download_bundle",
        )
        _json_download(
            "Download Bundle cleanup receipt",
            "caregiver_health_bundle_cleanup.json",
            result["cleanup"],
            "cg_download_cleanup",
        )

    with tab_quality:
        st.write(f"**Result:** {result['quality']['status']}")
        st.write(result["quality"]["claim"])
        st.dataframe(result["quality"]["checks"], use_container_width=True, hide_index=True)
        _json_download(
            "Download quality report",
            "caregiver_health_quality_report.json",
            result["quality"],
            "cg_download_quality",
        )

with st.expander("Recent persisted QuestionnaireResponses"):
    try:
        recent = load_questionnaire_responses(limit=20, db_path=db_path)
        if recent:
            st.dataframe(
                [
                    {
                        "response_id": row["response_id"],
                        "patient_id": row["patient_id"],
                        "authored": row["authored"],
                        "status": row["status"],
                        "created_ts": row["created_ts"],
                    }
                    for row in recent
                ],
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("No caregiver questionnaire responses persisted yet.")
    except Exception as exc:
        st.error(f"Unable to load recent responses: {exc}")
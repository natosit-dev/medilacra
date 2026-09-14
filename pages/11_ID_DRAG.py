from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any

import streamlit as st

from connectathon.id_drag import build_id_drag_artifacts
from hl7_demo.generators import gen_patient
from storage_duckdb_entities import DEFAULT_DB_PATH, init_db, upsert_patient
from utils.db import reader


st.set_page_config(page_title="MediLacra — ID DRAG", layout="wide")
st.title("ID DRAG")
st.caption("Identity Resolution Doesn't Require A Gun")
st.write(
    "Proof of concept: associate a human-verified hand image with a synthetic patient "
    "and carry it through ordinary healthcare interoperability artifacts."
)


def _load_patients(db_path: str, limit: int = 100) -> list[dict[str, Any]]:
    with reader(db_path=db_path) as connection:
        rows = connection.execute(
            """
            SELECT patient_id, mrn, patient_name, date_of_birth, sex,
                   phone, address, city, state, zip
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
        "phone",
        "address",
        "city",
        "state",
        "zip",
    ]
    return [dict(zip(columns, row)) for row in rows]


def _json_download(label: str, filename: str, value: dict[str, Any], key: str) -> None:
    st.download_button(
        label,
        data=json.dumps(value, indent=2, sort_keys=True, default=str),
        file_name=filename,
        mime="application/fhir+json",
        key=key,
        use_container_width=True,
    )


def _observation_preview(observation: dict[str, Any]) -> dict[str, Any]:
    preview = dict(observation)
    payload = str(preview.get("valueString") or "")
    if payload:
        preview["valueString"] = (
            f"{payload[:160]}... <{len(payload)} base64 characters total>"
            if len(payload) > 160
            else payload
        )
    return preview


def _hl7_preview(message: str, payload: str) -> str:
    if payload and payload in message:
        replacement = (
            f"{payload[:120]}...<{len(payload)} base64 characters total>"
            if len(payload) > 120
            else payload
        )
        return message.replace(payload, replacement)
    return message


with st.sidebar:
    st.header("ID DRAG settings")
    db_path = st.text_input("DuckDB path", DEFAULT_DB_PATH, key="id_drag_db_path")
    st.caption("v0.1 — transport/provenance proof of concept")
    st.caption("No fingerprint extraction or biometric matching.")

init_db(db_path)
patients = _load_patients(db_path)

st.subheader("1. Synthetic patient")
patient_columns = st.columns([4, 1])
with patient_columns[1]:
    if st.button(
        "Generate patient",
        type="secondary",
        use_container_width=True,
        key="id_drag_generate_patient",
    ):
        generated_patient = gen_patient()
        upsert_patient(asdict(generated_patient), db_path=db_path)
        st.rerun()

if not patients:
    st.info("No synthetic patients are persisted yet. Generate one to start ID DRAG.")
    st.stop()

patient_lookup = {str(patient["patient_id"]): patient for patient in patients}
selected_patient_id = st.selectbox(
    "Patient",
    options=list(patient_lookup),
    format_func=lambda patient_id: (
        f"{patient_lookup[patient_id].get('patient_name') or 'Unnamed synthetic patient'} "
        f"— {patient_id}"
    ),
    key="id_drag_patient",
)
patient = patient_lookup[selected_patient_id]

identity_columns = st.columns(3)
identity_columns[0].metric("Patient", patient.get("patient_name") or "—")
identity_columns[1].metric("Patient ID", patient.get("patient_id") or "—")
identity_columns[2].metric("Date of birth", str(patient.get("date_of_birth") or "—"))

st.divider()
st.subheader("2. Hand image")

uploaded_image = st.file_uploader(
    "Hand image",
    type=["jpg", "jpeg", "png"],
    accept_multiple_files=False,
    key="id_drag_hand_image",
)

if uploaded_image is not None:
    st.image(uploaded_image, caption=uploaded_image.name, width=480)

verification = st.radio(
    "Does this hand belong to the human?",
    options=["Yes", "No"],
    index=None,
    horizontal=True,
    key="id_drag_human_check",
)

human_verified = verification == "Yes"

if verification == "No":
    st.session_state.pop("id_drag_last_result", None)
    st.warning(
        "No association will be created. Choose another image if you want to continue."
    )
elif verification == "Yes":
    st.success("Human verification recorded for this enrollment attempt.")

can_materialize = uploaded_image is not None and human_verified
create_artifact = st.button(
    "Create ID DRAG artifact",
    type="primary",
    use_container_width=True,
    disabled=not can_materialize,
    key="id_drag_create_artifact",
)

if create_artifact:
    image_bytes = uploaded_image.getvalue()
    result = build_id_drag_artifacts(
        patient,
        image_bytes,
        uploaded_image.type or "",
        human_verified=human_verified,
        source_filename=uploaded_image.name,
    )
    st.session_state.id_drag_last_result = result
    st.success(
        "Hand image associated with the synthetic patient after human verification."
    )

result = st.session_state.get("id_drag_last_result")
result_patient_id = None
if result:
    identifiers = result.get("patient", {}).get("identifier", [])
    if identifiers:
        result_patient_id = str(identifiers[0].get("value") or "")

if result and result_patient_id == selected_patient_id and human_verified:
    st.divider()
    st.subheader("3. Interoperability artifacts")

    status_columns = st.columns(4)
    status_columns[0].metric("Human verified", "YES")
    status_columns[1].metric("Image encoded", "YES")
    status_columns[2].metric("HL7 OBX generated", "YES")
    status_columns[3].metric("FHIR Observation", "YES")

    st.caption(
        f"Source: {result.get('source_filename') or 'uploaded image'} · "
        f"{result.get('content_type')} · "
        f"{len(result.get('image_base64') or '')} base64 characters"
    )

    tab_observation, tab_bundle, tab_hl7 = st.tabs(
        ["FHIR Observation", "FHIR Bundle", "HL7 ORU"]
    )

    with tab_observation:
        st.caption(
            "The display truncates the base64 payload; the downloaded Observation contains it in full."
        )
        st.json(_observation_preview(result["observation"]))
        _json_download(
            "Download FHIR Observation",
            "id_drag_observation.json",
            result["observation"],
            "id_drag_download_observation",
        )

    with tab_bundle:
        bundle_preview = json.loads(json.dumps(result["bundle"], default=str))
        for entry in bundle_preview.get("entry", []):
            resource = entry.get("resource", {})
            if resource.get("resourceType") == "Observation":
                entry["resource"] = _observation_preview(resource)
        st.caption(
            "Collection Bundle contains the synthetic Patient and the full ID DRAG Observation."
        )
        st.json(bundle_preview)
        _json_download(
            "Download FHIR Bundle",
            "id_drag_bundle.json",
            result["bundle"],
            "id_drag_download_bundle",
        )

    with tab_hl7:
        st.caption(
            "The display truncates the ED payload; the downloaded ORU contains the complete base64 image."
        )
        st.code(
            _hl7_preview(result["hl7"], result["image_base64"]),
            language="text",
        )
        st.download_button(
            "Download HL7 ORU",
            data=result["hl7"],
            file_name="id_drag_oru_r01.hl7",
            mime="text/plain",
            key="id_drag_download_hl7",
            use_container_width=True,
        )

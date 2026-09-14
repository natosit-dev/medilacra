"""ID DRAG v0.1 transport/provenance proof of concept.

Identity Resolution Doesn't Require A Gun.

This module deliberately does not perform fingerprint extraction, biometric matching,
or identity proof. It associates a human-verified hand image with an existing synthetic
MediLacra patient and carries that image through ordinary FHIR and HL7 v2 artifacts.
"""

from __future__ import annotations

import base64
import uuid
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from typing import Any, Mapping

from connectathon.gravity_response import build_patient_resource, fhir_id

ID_DRAG_SYSTEM = "https://medilacra.dev/id-drag"
ID_DRAG_IMAGE_CODE = "IDDRAG-HAND-IMAGE"
ID_DRAG_HUMAN_VERIFIED_CODE = "IDDRAG-HUMAN-VERIFIED"
ID_DRAG_CONTENT_TYPE_CODE = "IDDRAG-CONTENT-TYPE"
ID_DRAG_SOURCE_FILENAME_CODE = "IDDRAG-SOURCE-FILENAME"

_SUPPORTED_CONTENT_TYPES = {
    "image/jpeg": "JPEG",
    "image/jpg": "JPEG",
    "image/png": "PNG",
}


def _patient_mapping(patient: Any) -> dict[str, Any]:
    if is_dataclass(patient):
        return asdict(patient)
    if isinstance(patient, Mapping):
        return dict(patient)
    raise TypeError("patient must be a mapping or dataclass")


def normalize_content_type(content_type: str) -> tuple[str, str]:
    normalized = str(content_type or "").strip().lower()
    if normalized not in _SUPPORTED_CONTENT_TYPES:
        raise ValueError("ID DRAG v0.1 accepts JPEG or PNG hand images only")
    if normalized == "image/jpg":
        normalized = "image/jpeg"
    return normalized, _SUPPORTED_CONTENT_TYPES[str(content_type or "").strip().lower()]


def encode_image(image_bytes: bytes) -> str:
    if not isinstance(image_bytes, (bytes, bytearray)) or not image_bytes:
        raise ValueError("image_bytes must contain a non-empty hand image")
    return base64.b64encode(bytes(image_bytes)).decode("ascii")


def _coerce_datetime(value: datetime | None) -> datetime:
    current = value or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return current.astimezone(timezone.utc)


def _coding(code: str, display: str) -> dict[str, Any]:
    return {
        "coding": [
            {
                "system": ID_DRAG_SYSTEM,
                "code": code,
                "display": display,
            }
        ],
        "text": display,
    }


def build_fhir_observation(
    patient: Any,
    image_base64: str,
    content_type: str,
    *,
    human_verified: bool,
    source_filename: str | None = None,
    effective_datetime: datetime | None = None,
) -> dict[str, Any]:
    """Build the intentionally simple v0.1 FHIR Observation.

    The base64 payload is kept directly in Observation.valueString for this proof of
    concept. This is a transport experiment, not a proposed canonical biometric profile.
    """
    if human_verified is not True:
        raise ValueError("A human must verify that the hand belongs to the selected patient")

    patient_resource = build_patient_resource(patient)
    normalized_content_type, _ = normalize_content_type(content_type)
    when = _coerce_datetime(effective_datetime)

    components: list[dict[str, Any]] = [
        {
            "code": _coding(ID_DRAG_HUMAN_VERIFIED_CODE, "Human verified"),
            "valueBoolean": True,
        },
        {
            "code": _coding(ID_DRAG_CONTENT_TYPE_CODE, "Image content type"),
            "valueString": normalized_content_type,
        },
    ]
    if source_filename:
        components.append(
            {
                "code": _coding(ID_DRAG_SOURCE_FILENAME_CODE, "Source filename"),
                "valueString": str(source_filename),
            }
        )

    return {
        "resourceType": "Observation",
        "id": fhir_id(f"id-drag-{uuid.uuid4().hex}", prefix="id-drag"),
        "status": "final",
        "code": _coding(ID_DRAG_IMAGE_CODE, "Hand identity image"),
        "subject": {"reference": f"Patient/{patient_resource['id']}"},
        "effectiveDateTime": when.isoformat().replace("+00:00", "Z"),
        "valueString": image_base64,
        "component": components,
    }


def build_fhir_bundle(
    patient: Any,
    observation: Mapping[str, Any],
) -> dict[str, Any]:
    patient_resource = build_patient_resource(patient)
    observation_resource = dict(observation)
    return {
        "resourceType": "Bundle",
        "type": "collection",
        "entry": [
            {
                "fullUrl": f"urn:uuid:{uuid.uuid4()}",
                "resource": patient_resource,
            },
            {
                "fullUrl": f"urn:uuid:{uuid.uuid4()}",
                "resource": observation_resource,
            },
        ],
    }


def _hl7_escape(value: Any) -> str:
    text = str(value or "")
    # Escape the escape character first, then the other HL7 delimiters.
    text = text.replace("\\", "\\E\\")
    text = text.replace("|", "\\F\\")
    text = text.replace("^", "\\S\\")
    text = text.replace("~", "\\R\\")
    text = text.replace("&", "\\T\\")
    return text


def _hl7_patient_name(raw_name: Any) -> str:
    name = str(raw_name or "").strip()
    if "," in name:
        family, given = [part.strip() for part in name.split(",", 1)]
        return f"{_hl7_escape(family)}^{_hl7_escape(given)}"
    return _hl7_escape(name)


def _hl7_date(raw: Any) -> str:
    text = str(raw or "").strip()
    return text.replace("-", "")[:8]


def build_hl7_oru(
    patient: Any,
    image_base64: str,
    content_type: str,
    *,
    human_verified: bool,
    effective_datetime: datetime | None = None,
) -> str:
    """Build a minimal ORU^R01 carrying the hand image as OBX ED data."""
    if human_verified is not True:
        raise ValueError("A human must verify that the hand belongs to the selected patient")

    src = _patient_mapping(patient)
    _normalized_content_type, subtype = normalize_content_type(content_type)
    when = _coerce_datetime(effective_datetime)
    timestamp = when.strftime("%Y%m%d%H%M%S")
    control_id = f"IDDRAG{uuid.uuid4().hex[:16].upper()}"

    patient_id = _hl7_escape(src.get("patient_id"))
    patient_name = _hl7_patient_name(src.get("patient_name"))
    dob = _hl7_date(src.get("date_of_birth"))
    sex = _hl7_escape(str(src.get("sex") or "").upper()[:1])

    segments = [
        f"MSH|^~\\&|MEDILACRA|IDDRAG|MEDILACRA|IDDRAG|{timestamp}||ORU^R01|{control_id}|P|2.5.1",
        f"PID|1||{patient_id}^^^MEDILACRA^MR||{patient_name}||{dob}|{sex}",
        f"OBR|1|||{ID_DRAG_IMAGE_CODE}^Hand identity image^99MEDILACRA|||||||||||||||||||||F",
        (
            f"OBX|1|ED|{ID_DRAG_IMAGE_CODE}^Hand identity image^99MEDILACRA||"
            f"^IM^{subtype}^Base64^{image_base64}||||||F"
        ),
        (
            f"OBX|2|ID|{ID_DRAG_HUMAN_VERIFIED_CODE}^Human verified^99MEDILACRA||"
            "Y||||||F"
        ),
    ]
    return "\r".join(segments) + "\r"


def build_id_drag_artifacts(
    patient: Any,
    image_bytes: bytes,
    content_type: str,
    *,
    human_verified: bool,
    source_filename: str | None = None,
    effective_datetime: datetime | None = None,
) -> dict[str, Any]:
    """Materialize the complete ID DRAG v0.1 artifact set."""
    if human_verified is not True:
        raise ValueError("A human must verify that the hand belongs to the selected patient")

    normalized_content_type, _ = normalize_content_type(content_type)
    image_base64 = encode_image(image_bytes)
    patient_resource = build_patient_resource(patient)
    observation = build_fhir_observation(
        patient,
        image_base64,
        normalized_content_type,
        human_verified=True,
        source_filename=source_filename,
        effective_datetime=effective_datetime,
    )
    bundle = build_fhir_bundle(patient, observation)
    hl7 = build_hl7_oru(
        patient,
        image_base64,
        normalized_content_type,
        human_verified=True,
        effective_datetime=effective_datetime,
    )

    return {
        "patient": patient_resource,
        "observation": observation,
        "bundle": bundle,
        "hl7": hl7,
        "image_base64": image_base64,
        "content_type": normalized_content_type,
        "source_filename": source_filename,
        "human_verified": True,
    }


__all__ = [
    "ID_DRAG_SYSTEM",
    "ID_DRAG_IMAGE_CODE",
    "ID_DRAG_HUMAN_VERIFIED_CODE",
    "encode_image",
    "normalize_content_type",
    "build_fhir_observation",
    "build_fhir_bundle",
    "build_hl7_oru",
    "build_id_drag_artifacts",
]

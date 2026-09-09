from __future__ import annotations

import re
import uuid
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from typing import Any, Mapping

from connectathon.gravity_questionnaire import (
    DATA_ABSENT_REASON_URL,
    LOINC_SYSTEM,
    PHQ_DISPLAY_BY_CODE,
    PHQ_SCORE_BY_CODE,
    QUESTIONNAIRE_URL,
    QUESTIONNAIRE_VERSION,
    UCUM_SYSTEM,
    data_absent_reason,
)


PATIENT_IDENTIFIER_SYSTEM = "https://medilacra.dev/patient-id"
_FHIR_ID_RE = re.compile(r"[^A-Za-z0-9\-.]")


def fhir_id(raw: str, prefix: str = "id") -> str:
    cleaned = _FHIR_ID_RE.sub("-", str(raw or "").strip()).strip("-.")
    if not cleaned:
        cleaned = f"{prefix}-{uuid.uuid4().hex}"
    return cleaned[:64]


def _patient_mapping(patient: Any) -> dict[str, Any]:
    if is_dataclass(patient):
        return asdict(patient)
    if isinstance(patient, Mapping):
        return dict(patient)
    raise TypeError("patient must be a mapping or dataclass")


def build_patient_resource(patient: Any) -> dict[str, Any]:
    """Materialize an existing MediLacra synthetic Patient as a FHIR Patient."""
    src = _patient_mapping(patient)
    source_patient_id = str(src.get("patient_id") or "")
    patient_id = fhir_id(source_patient_id, prefix="patient")
    sex = str(src.get("sex") or src.get("gender") or "").strip().upper()
    gender = {"M": "male", "F": "female", "O": "other", "U": "unknown"}.get(sex, "unknown")

    patient_resource: dict[str, Any] = {
        "resourceType": "Patient",
        "id": patient_id,
        "identifier": [
            {
                "system": PATIENT_IDENTIFIER_SYSTEM,
                "value": source_patient_id or patient_id,
            }
        ],
        "gender": gender,
    }

    if src.get("patient_name"):
        patient_resource["name"] = [{"text": str(src["patient_name"])}]
    if src.get("date_of_birth"):
        patient_resource["birthDate"] = str(src["date_of_birth"])

    address = {
        "text": src.get("address"),
        "city": src.get("city"),
        "state": src.get("state"),
        "postalCode": src.get("zip_code") or src.get("zip"),
    }
    address = {key: value for key, value in address.items() if value not in (None, "")}
    if address:
        patient_resource["address"] = [address]

    telecom = []
    if src.get("phone"):
        telecom.append({"system": "phone", "value": str(src["phone"])})
    if src.get("email"):
        telecom.append({"system": "email", "value": str(src["email"])})
    if telecom:
        patient_resource["telecom"] = telecom

    return patient_resource


def _absent_answer(reason: str) -> dict[str, Any]:
    return {"extension": [data_absent_reason(reason)]}


def answer_absent_reason(answer: Mapping[str, Any] | None) -> str | None:
    if not isinstance(answer, Mapping):
        return None
    for extension in answer.get("extension", []) or []:
        if not isinstance(extension, Mapping):
            continue
        if extension.get("url") == DATA_ABSENT_REASON_URL and extension.get("valueCode"):
            return str(extension["valueCode"])
    return None


def _item(link_id: str, text: str, answer: Mapping[str, Any] | None = None) -> dict[str, Any]:
    item: dict[str, Any] = {"linkId": link_id, "text": text}
    if answer is not None:
        item["answer"] = [dict(answer)]
    return item


def _parse_float(raw: Any) -> tuple[float | None, str | None]:
    if raw is None or str(raw).strip() == "":
        return None, None
    try:
        value = float(str(raw).strip())
    except (TypeError, ValueError):
        return None, "error"
    if value != value:
        return None, "not-a-number"
    if value == float("inf"):
        return None, "positive-infinity"
    if value == float("-inf"):
        return None, "negative-infinity"
    return value, None


def _parse_int(raw: Any) -> tuple[int | None, str | None]:
    if raw is None or str(raw).strip() == "":
        return None, None
    text = str(raw).strip()
    if re.fullmatch(r"[-+]?\d+", text) is None:
        return None, "error"
    return int(text), None


def _quantity_answer(raw: Any, unit: str, code: str, declined: bool) -> dict[str, Any] | None:
    if declined:
        return _absent_answer("asked-declined")
    value, error = _parse_float(raw)
    if error:
        return _absent_answer(error)
    if value is None:
        return None
    return {
        "valueQuantity": {
            "value": value,
            "unit": unit,
            "system": UCUM_SYSTEM,
            "code": code,
        }
    }


def _integer_answer(raw: Any, declined: bool) -> dict[str, Any] | None:
    if declined:
        return _absent_answer("asked-declined")
    value, error = _parse_int(raw)
    if error:
        return _absent_answer(error)
    if value is None:
        return None
    return {"valueInteger": value}


def _phq_answer(raw: Any, declined: bool) -> dict[str, Any] | None:
    if declined:
        return _absent_answer("asked-declined")
    code = str(raw or "").strip()
    if not code:
        return None
    if code not in PHQ_SCORE_BY_CODE:
        return _absent_answer("error")
    return {
        "valueCoding": {
            "system": LOINC_SYSTEM,
            "code": code,
            "display": PHQ_DISPLAY_BY_CODE[code],
        }
    }


def _boolean_answer(raw: Any, declined: bool) -> dict[str, Any] | None:
    if declined:
        return _absent_answer("asked-declined")
    if raw is None or str(raw).strip() == "":
        return None
    if isinstance(raw, bool):
        return {"valueBoolean": raw}
    text = str(raw).strip().lower()
    if text in {"yes", "y", "true", "1"}:
        return {"valueBoolean": True}
    if text in {"no", "n", "false", "0"}:
        return {"valueBoolean": False}
    return _absent_answer("error")


def _medication_group(raw_medication: Mapping[str, Any], index: int) -> dict[str, Any] | None:
    name = str(raw_medication.get("name") or "").strip()
    rxnorm = str(raw_medication.get("rxnorm") or "").strip()
    raw_dose = raw_medication.get("dose_value")
    unit = str(raw_medication.get("dose_unit") or "").strip()
    route = str(raw_medication.get("route") or "").strip()
    frequency = str(raw_medication.get("frequency") or "").strip()
    dose, dose_error = _parse_float(raw_dose)

    if not any([name, rxnorm, str(raw_dose or "").strip(), unit, route, frequency]):
        return None

    children = [
        _item("medication-name", "Medication name", {"valueString": name}) if name else _item("medication-name", "Medication name"),
        _item("medication-rxnorm", "RxNorm code (if known)", {"valueString": rxnorm}) if rxnorm else _item("medication-rxnorm", "RxNorm code (if known)"),
    ]
    if dose_error:
        children.append(_item("medication-dose-value", "Dose", _absent_answer(dose_error)))
    elif dose is not None:
        children.append(_item("medication-dose-value", "Dose", {"valueDecimal": dose}))
    else:
        children.append(_item("medication-dose-value", "Dose"))
    children.extend(
        [
            _item("medication-dose-unit", "Dose unit", {"valueString": unit}) if unit else _item("medication-dose-unit", "Dose unit"),
            _item("medication-route", "Route", {"valueString": route}) if route else _item("medication-route", "Route"),
            _item("medication-frequency", "Frequency", {"valueString": frequency}) if frequency else _item("medication-frequency", "Frequency"),
        ]
    )

    return {
        "linkId": "medications",
        "text": f"Medication {index}",
        "item": children,
    }


def build_questionnaire_response(
    patient_id: str,
    raw_input: Mapping[str, Any],
    *,
    declined: set[str] | None = None,
    authored: str | None = None,
    response_id: str | None = None,
) -> dict[str, Any]:
    """Build a FHIR QuestionnaireResponse directly from the UI state."""
    declined = declined or set()
    qr_id = fhir_id(response_id or f"caregiver-qr-{uuid.uuid4().hex}", prefix="qr")
    authored = authored or datetime.now(timezone.utc).isoformat(timespec="seconds")

    medication_status = _item(
        "medication-status",
        "Are you currently taking any medications?",
        _boolean_answer(raw_input.get("medication-status"), "medication-status" in declined),
    )

    items: list[dict[str, Any]] = [
        _item(
            "sleep-hours",
            "About how many hours did you sleep in the past 24 hours?",
            _quantity_answer(raw_input.get("sleep-hours"), "hours", "h", "sleep-hours" in declined),
        ),
        _item(
            "pain-score",
            "Pain right now (0-10)",
            _integer_answer(raw_input.get("pain-score"), "pain-score" in declined),
        ),
        {
            "linkId": "phq2",
            "text": "PHQ-2",
            "item": [
                _item(
                    "phq2-interest",
                    "Little interest or pleasure in doing things",
                    _phq_answer(raw_input.get("phq2-interest"), "phq2-interest" in declined),
                ),
                _item(
                    "phq2-depressed",
                    "Feeling down, depressed, or hopeless",
                    _phq_answer(raw_input.get("phq2-depressed"), "phq2-depressed" in declined),
                ),
            ],
        },
        _item(
            "heart-rate",
            "What is your current heart rate?",
            _quantity_answer(raw_input.get("heart-rate"), "beats/minute", "/min", "heart-rate" in declined),
        ),
        medication_status,
    ]

    status_answers = medication_status.get("answer") or []
    taking_medications = bool(status_answers and status_answers[0].get("valueBoolean") is True)
    if taking_medications:
        for index, medication in enumerate(raw_input.get("medications") or [], start=1):
            if isinstance(medication, Mapping):
                group = _medication_group(medication, index)
                if group:
                    items.append(group)

    return {
        "resourceType": "QuestionnaireResponse",
        "id": qr_id,
        "questionnaire": f"{QUESTIONNAIRE_URL}|{QUESTIONNAIRE_VERSION}",
        "status": "completed",
        "subject": {"reference": f"Patient/{fhir_id(patient_id, prefix='patient')}"},
        "authored": authored,
        "item": items,
    }


def iter_response_items(items: list[dict[str, Any]], prefix: str = ""):
    """Yield every QuestionnaireResponse item with a stable local path."""
    for item in items:
        link_id = str(item.get("linkId") or "")
        path = f"{prefix}/{link_id}" if prefix else link_id
        yield path, item
        nested = item.get("item") or []
        if isinstance(nested, list):
            yield from iter_response_items(nested, path)


def find_response_items(resource: Mapping[str, Any], link_id: str) -> list[Mapping[str, Any]]:
    return [
        item
        for _path, item in iter_response_items(list(resource.get("item") or []))
        if item.get("linkId") == link_id
    ]


def first_answer(resource: Mapping[str, Any], link_id: str) -> Mapping[str, Any] | None:
    items = find_response_items(resource, link_id)
    if not items:
        return None
    answers = items[0].get("answer") or []
    return answers[0] if answers and isinstance(answers[0], Mapping) else None

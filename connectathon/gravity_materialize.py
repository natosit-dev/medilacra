from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Mapping

from connectathon.fhir_control import prepare_control_bundle
from connectathon.gravity_questionnaire import (
    HEART_RATE_LOINC,
    LOINC_SYSTEM,
    PAIN_LOINC,
    PHQ2_QUESTION_1,
    PHQ2_QUESTION_2,
    PHQ2_TOTAL,
    PHQ_SCORE_BY_CODE,
    RXNORM_SYSTEM,
    UCUM_SYSTEM,
    build_questionnaire,
    local_coding,
    loinc_coding,
)
from connectathon.gravity_response import (
    build_patient_resource,
    fhir_id,
    find_response_items,
    first_answer,
    iter_response_items,
)


COMMON_DOSE_UNITS = {
    "mg": ("mg", "mg"),
    "g": ("g", "g"),
    "mcg": ("mcg", "ug"),
    "ug": ("mcg", "ug"),
    "ml": ("mL", "mL"),
}

# Tiny baseline terminology bridge, not a medication knowledge base. The questionnaire asks
# the person for medication text; terminology normalization happens downstream. Add entries
# only when the RxNorm concept has been verified.
BASELINE_RXNORM_BY_NAME = {
    "lisinopril": ("29046", "lisinopril"),
    "lisinopril 10 mg oral tablet": ("314076", "lisinopril 10 MG Oral Tablet"),
}


def _normalize_medication_name(name: str) -> str:
    return re.sub(r"\s+", " ", str(name or "").strip().lower())


def resolve_rxnorm(name: str) -> tuple[str, str] | None:
    """Resolve the intentionally tiny v0.1 medication terminology fixture."""
    return BASELINE_RXNORM_BY_NAME.get(_normalize_medication_name(name))


def _quantity_value(resource: Mapping[str, Any], link_id: str) -> float | None:
    answer = first_answer(resource, link_id)
    quantity = answer.get("valueQuantity") if isinstance(answer, Mapping) else None
    value = quantity.get("value") if isinstance(quantity, Mapping) else None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None


def _integer_value(resource: Mapping[str, Any], link_id: str) -> int | None:
    answer = first_answer(resource, link_id)
    value = answer.get("valueInteger") if isinstance(answer, Mapping) else None
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return None


def _coding_value(resource: Mapping[str, Any], link_id: str) -> Mapping[str, Any] | None:
    answer = first_answer(resource, link_id)
    coding = answer.get("valueCoding") if isinstance(answer, Mapping) else None
    return coding if isinstance(coding, Mapping) else None


def _boolean_value(resource: Mapping[str, Any], link_id: str) -> bool | None:
    answer = first_answer(resource, link_id)
    value = answer.get("valueBoolean") if isinstance(answer, Mapping) else None
    return value if isinstance(value, bool) else None


def _child_value(group: Mapping[str, Any], link_id: str, value_key: str) -> Any:
    nested = list(group.get("item") or [])
    for _path, item in iter_response_items(nested):
        if item.get("linkId") != link_id:
            continue
        answers = item.get("answer") or []
        if answers and isinstance(answers[0], Mapping):
            return answers[0].get(value_key)
    return None


def _observation(
    *,
    observation_id: str,
    patient_ref: str,
    authored: str,
    coding: Mapping[str, Any],
    value_key: str,
    value: Any,
    questionnaire_response_id: str,
) -> dict[str, Any]:
    return {
        "resourceType": "Observation",
        "id": fhir_id(observation_id, prefix="obs"),
        "status": "final",
        "code": {"coding": [dict(coding)], "text": coding.get("display")},
        "subject": {"reference": patient_ref},
        "effectiveDateTime": authored,
        "derivedFrom": [{"reference": f"QuestionnaireResponse/{questionnaire_response_id}"}],
        value_key: value,
    }


def extract_clinical_resources(questionnaire_response: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Extract the deliberately small Phase 1 clinical fact set."""
    qr_id = str(questionnaire_response.get("id") or "")
    patient_ref = str((questionnaire_response.get("subject") or {}).get("reference") or "")
    authored = str(
        questionnaire_response.get("authored")
        or datetime.now(timezone.utc).isoformat(timespec="seconds")
    )
    resources: list[dict[str, Any]] = []

    sleep = _quantity_value(questionnaire_response, "sleep-hours")
    if sleep is not None:
        resources.append(
            _observation(
                observation_id=f"{qr_id}-sleep",
                patient_ref=patient_ref,
                authored=authored,
                coding=local_coding("sleep-hours-24h", "Hours slept in past 24 hours"),
                value_key="valueQuantity",
                value={"value": sleep, "unit": "hours", "system": UCUM_SYSTEM, "code": "h"},
                questionnaire_response_id=qr_id,
            )
        )

    pain = _integer_value(questionnaire_response, "pain-score")
    if pain is not None:
        resources.append(
            _observation(
                observation_id=f"{qr_id}-pain",
                patient_ref=patient_ref,
                authored=authored,
                coding=loinc_coding(
                    PAIN_LOINC,
                    "Pain severity - 0-10 verbal numeric rating [Score] - Reported",
                ),
                value_key="valueInteger",
                value=pain,
                questionnaire_response_id=qr_id,
            )
        )

    phq_codes: list[str | None] = []
    for link_id, loinc_code, display in (
        ("phq2-interest", PHQ2_QUESTION_1, "Little interest or pleasure in doing things"),
        ("phq2-depressed", PHQ2_QUESTION_2, "Feeling down, depressed, or hopeless"),
    ):
        answer_coding = _coding_value(questionnaire_response, link_id)
        answer_code = str(answer_coding.get("code")) if answer_coding and answer_coding.get("code") else None
        phq_codes.append(answer_code)
        if answer_coding and answer_code in PHQ_SCORE_BY_CODE:
            resources.append(
                _observation(
                    observation_id=f"{qr_id}-{link_id}",
                    patient_ref=patient_ref,
                    authored=authored,
                    coding=loinc_coding(loinc_code, display),
                    value_key="valueCodeableConcept",
                    value={"coding": [dict(answer_coding)]},
                    questionnaire_response_id=qr_id,
                )
            )

    if len(phq_codes) == 2 and all(code in PHQ_SCORE_BY_CODE for code in phq_codes):
        total = sum(PHQ_SCORE_BY_CODE[str(code)] for code in phq_codes)
        resources.append(
            _observation(
                observation_id=f"{qr_id}-phq2-total",
                patient_ref=patient_ref,
                authored=authored,
                coding=loinc_coding(PHQ2_TOTAL, "PHQ-2 total score"),
                value_key="valueInteger",
                value=total,
                questionnaire_response_id=qr_id,
            )
        )

    heart_rate = _quantity_value(questionnaire_response, "heart-rate")
    if heart_rate is not None:
        resources.append(
            _observation(
                observation_id=f"{qr_id}-heart-rate",
                patient_ref=patient_ref,
                authored=authored,
                coding=loinc_coding(HEART_RATE_LOINC, "Heart rate"),
                value_key="valueQuantity",
                value={
                    "value": heart_rate,
                    "unit": "beats/minute",
                    "system": UCUM_SYSTEM,
                    "code": "/min",
                },
                questionnaire_response_id=qr_id,
            )
        )

    if _boolean_value(questionnaire_response, "medication-status") is True:
        for index, group in enumerate(find_response_items(questionnaire_response, "medications"), start=1):
            name = str(_child_value(group, "medication-name", "valueString") or "").strip()
            dose_value = _child_value(group, "medication-dose-value", "valueDecimal")
            dose_unit = str(_child_value(group, "medication-dose-unit", "valueString") or "").strip()
            route = str(_child_value(group, "medication-route", "valueString") or "").strip()
            frequency = str(_child_value(group, "medication-frequency", "valueString") or "").strip()

            if not any([name, dose_value is not None, dose_unit, route, frequency]):
                continue

            medication_concept: dict[str, Any] = {}
            if name:
                medication_concept["text"] = name
                resolved = resolve_rxnorm(name)
                if resolved:
                    rxnorm_code, rxnorm_display = resolved
                    medication_concept["coding"] = [
                        {
                            "system": RXNORM_SYSTEM,
                            "code": rxnorm_code,
                            "display": rxnorm_display,
                        }
                    ]

            dosage: dict[str, Any] = {}
            if frequency:
                dosage["text"] = frequency
                dosage["timing"] = {"code": {"text": frequency}}
            if route:
                dosage["route"] = {"text": route}
            if isinstance(dose_value, (int, float)) and not isinstance(dose_value, bool):
                dose_quantity: dict[str, Any] = {"value": float(dose_value)}
                normalized = COMMON_DOSE_UNITS.get(dose_unit.lower()) if dose_unit else None
                if normalized:
                    display_unit, code = normalized
                    dose_quantity.update({"unit": display_unit, "system": UCUM_SYSTEM, "code": code})
                elif dose_unit:
                    dose_quantity["unit"] = dose_unit
                dosage["doseAndRate"] = [{"doseQuantity": dose_quantity}]

            statement: dict[str, Any] = {
                "resourceType": "MedicationStatement",
                "id": fhir_id(f"{qr_id}-med-{index}", prefix="med"),
                "status": "active",
                "medicationCodeableConcept": medication_concept or {"text": "Medication reported"},
                "subject": {"reference": patient_ref},
                "dateAsserted": authored,
                "derivedFrom": [{"reference": f"QuestionnaireResponse/{qr_id}"}],
            }
            if dosage:
                statement["dosage"] = [dosage]
            resources.append(statement)

    return resources


def build_submission_bundle(
    patient: Any,
    questionnaire_response: Mapping[str, Any],
    *,
    questionnaire: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build a self-contained collection Bundle using existing Connectathon normalization."""
    if isinstance(patient, Mapping) and patient.get("resourceType") == "Patient":
        patient_resource = dict(patient)
    else:
        patient_resource = build_patient_resource(patient)

    qr = dict(questionnaire_response)
    resources = [
        patient_resource,
        dict(questionnaire or build_questionnaire()),
        qr,
        *extract_clinical_resources(qr),
    ]
    raw_bundle = {
        "resourceType": "Bundle",
        "id": fhir_id(f"caregiver-bundle-{qr.get('id')}", prefix="bundle"),
        "type": "collection",
        "entry": [{"resource": resource} for resource in resources],
    }
    return prepare_control_bundle(raw_bundle)


def bundle_resources(bundle: Mapping[str, Any], resource_type: str | None = None) -> list[Mapping[str, Any]]:
    resources: list[Mapping[str, Any]] = []
    for entry in bundle.get("entry", []) or []:
        resource = entry.get("resource") if isinstance(entry, Mapping) else None
        if not isinstance(resource, Mapping):
            continue
        if resource_type is None or resource.get("resourceType") == resource_type:
            resources.append(resource)
    return resources


def observation_by_loinc(bundle: Mapping[str, Any], code: str) -> Mapping[str, Any] | None:
    for observation in bundle_resources(bundle, "Observation"):
        codings = ((observation.get("code") or {}).get("coding") or [])
        if any(
            isinstance(coding, Mapping)
            and coding.get("system") == LOINC_SYSTEM
            and coding.get("code") == code
            for coding in codings
        ):
            return observation
    return None

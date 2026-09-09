from __future__ import annotations

from typing import Any, Mapping

from connectathon.preflight import preflight_bundle
from connectathon.gravity_materialize import bundle_resources, observation_by_loinc
from connectathon.gravity_questionnaire import (
    HEART_RATE_LOINC,
    PAIN_LOINC,
    PHQ2_TOTAL,
    PHQ_SCORE_BY_CODE,
    RXNORM_SYSTEM,
    UCUM_SYSTEM,
)
from connectathon.gravity_response import (
    answer_absent_reason,
    first_answer,
    iter_response_items,
)


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


def caregiver_quality_gate(bundle: Mapping[str, Any]) -> dict[str, Any]:
    """Run simple Phase 1 plausibility, conformance, and semantic-survival checks.

    The gate intentionally avoids aggregate scoring. A record either makes basic sense and
    preserves the entered facts, or the report says exactly where it does not.
    """
    checks: list[dict[str, str]] = []

    def record(name: str, status: str, detail: str) -> None:
        checks.append({"check": name, "status": status, "detail": detail})

    structural = preflight_bundle(dict(bundle))
    record(
        "bundle.preflight",
        "PASS" if structural.get("status") == "PASS" else "FAIL",
        str(structural.get("claim") or ""),
    )

    patients = bundle_resources(bundle, "Patient")
    questionnaires = bundle_resources(bundle, "Questionnaire")
    responses = bundle_resources(bundle, "QuestionnaireResponse")
    record("patient.exists", "PASS" if len(patients) == 1 else "FAIL", f"patients={len(patients)}")
    record(
        "questionnaire.exists",
        "PASS" if len(questionnaires) == 1 else "FAIL",
        f"questionnaires={len(questionnaires)}",
    )
    record(
        "questionnaire_response.exists",
        "PASS" if len(responses) == 1 else "FAIL",
        f"responses={len(responses)}",
    )

    if not responses:
        return {
            "status": "FAIL",
            "scope": "CAREGIVER_BASELINE",
            "claim": "QuestionnaireResponse is missing; caregiver baseline cannot be evaluated.",
            "checks": checks,
            "structural": structural,
        }

    response = responses[0]
    record(
        "response.authored",
        "PASS" if response.get("authored") else "FAIL",
        f"authored={response.get('authored')!r}",
    )

    patient_full_urls = {
        entry.get("fullUrl")
        for entry in bundle.get("entry", []) or []
        if isinstance(entry, Mapping)
        and isinstance(entry.get("resource"), Mapping)
        and entry["resource"].get("resourceType") == "Patient"
    }
    subject = (response.get("subject") or {}).get("reference")
    record(
        "response.subject",
        "PASS" if subject in patient_full_urls else "FAIL",
        f"subject={subject!r}",
    )

    # Any explicit parse error must remain visible and fail plausibility. Decline is valid.
    response_errors: list[str] = []
    for path, item in iter_response_items(list(response.get("item") or [])):
        for answer in item.get("answer", []) or []:
            reason = answer_absent_reason(answer if isinstance(answer, Mapping) else None)
            if reason in {"error", "not-a-number", "negative-infinity", "positive-infinity"}:
                response_errors.append(f"{path}:{reason}")
    record(
        "response.parse_errors",
        "FAIL" if response_errors else "PASS",
        "none" if not response_errors else ", ".join(response_errors),
    )

    sleep_answer = first_answer(response, "sleep-hours")
    sleep_reason = answer_absent_reason(sleep_answer)
    sleep = _quantity_value(response, "sleep-hours")
    if sleep_reason == "asked-declined":
        record("sleep.plausibility", "PASS", "declined")
    elif sleep_reason:
        record("sleep.plausibility", "FAIL", f"data-absent-reason={sleep_reason}")
    elif sleep is None:
        record("sleep.plausibility", "SKIP", "unanswered")
    else:
        record("sleep.plausibility", "PASS" if 0 <= sleep <= 24 else "FAIL", f"hours={sleep}")

    pain_answer = first_answer(response, "pain-score")
    pain_reason = answer_absent_reason(pain_answer)
    pain = _integer_value(response, "pain-score")
    if pain_reason == "asked-declined":
        record("pain.plausibility", "PASS", "declined")
    elif pain_reason:
        record("pain.plausibility", "FAIL", f"data-absent-reason={pain_reason}")
    elif pain is None:
        record("pain.plausibility", "SKIP", "unanswered")
    else:
        record("pain.plausibility", "PASS" if 0 <= pain <= 10 else "FAIL", f"score={pain}")

    heart_answer = first_answer(response, "heart-rate")
    heart_reason = answer_absent_reason(heart_answer)
    heart_rate = _quantity_value(response, "heart-rate")
    if heart_reason == "asked-declined":
        record("heart_rate.plausibility", "PASS", "declined")
    elif heart_reason:
        record("heart_rate.plausibility", "FAIL", f"data-absent-reason={heart_reason}")
    elif heart_rate is None:
        record("heart_rate.plausibility", "SKIP", "unanswered")
    else:
        # Deliberately broad: 35 and 190 are representable values; negative/zero is not.
        record(
            "heart_rate.plausibility",
            "PASS" if heart_rate > 0 else "FAIL",
            f"heart_rate={heart_rate} /min",
        )

    phq_codes: list[str | None] = []
    phq_invalid = False
    for link_id in ("phq2-interest", "phq2-depressed"):
        answer = first_answer(response, link_id)
        reason = answer_absent_reason(answer)
        coding = _coding_value(response, link_id)
        code = str(coding.get("code")) if coding and coding.get("code") else None
        if reason and reason != "asked-declined":
            phq_invalid = True
        if code and code not in PHQ_SCORE_BY_CODE:
            phq_invalid = True
        phq_codes.append(code)
    record(
        "phq2.answers",
        "FAIL" if phq_invalid else ("PASS" if any(phq_codes) else "SKIP"),
        f"codes={phq_codes}",
    )

    expected_total = None
    if len(phq_codes) == 2 and all(code in PHQ_SCORE_BY_CODE for code in phq_codes):
        expected_total = sum(PHQ_SCORE_BY_CODE[str(code)] for code in phq_codes)
    total_observation = observation_by_loinc(bundle, PHQ2_TOTAL)
    actual_total = total_observation.get("valueInteger") if total_observation else None
    if expected_total is None:
        record(
            "phq2.total",
            "PASS" if total_observation is None else "FAIL",
            "total omitted unless both component answers are present",
        )
    else:
        record(
            "phq2.total",
            "PASS" if actual_total == expected_total else "FAIL",
            f"expected={expected_total}; actual={actual_total}",
        )

    heart_observation = observation_by_loinc(bundle, HEART_RATE_LOINC)
    if heart_rate is None:
        record(
            "heart_rate.materialization",
            "PASS" if heart_observation is None else "FAIL",
            "no answered heart rate -> no heart-rate Observation",
        )
    else:
        quantity = (heart_observation or {}).get("valueQuantity") or {}
        preserved = (
            heart_observation is not None
            and quantity.get("value") == heart_rate
            and quantity.get("system") == UCUM_SYSTEM
            and quantity.get("code") == "/min"
        )
        record(
            "heart_rate.materialization",
            "PASS" if preserved else "FAIL",
            f"entered={heart_rate}; observation={quantity}",
        )

    pain_observation = observation_by_loinc(bundle, PAIN_LOINC)
    if pain is None:
        record(
            "pain.materialization",
            "PASS" if pain_observation is None else "FAIL",
            "no answered pain -> no pain Observation",
        )
    else:
        preserved = pain_observation is not None and pain_observation.get("valueInteger") == pain
        record(
            "pain.materialization",
            "PASS" if preserved else "FAIL",
            f"entered={pain}; observation={(pain_observation or {}).get('valueInteger')}",
        )

    medication_status = _boolean_value(response, "medication-status")
    medications = bundle_resources(bundle, "MedicationStatement")
    if medication_status is True:
        record(
            "medications.cardinality",
            "PASS" if medications else "FAIL",
            f"status=yes; MedicationStatements={len(medications)}",
        )
    elif medication_status is False:
        record(
            "medications.cardinality",
            "PASS" if not medications else "FAIL",
            f"status=no; MedicationStatements={len(medications)}",
        )
    else:
        record(
            "medications.cardinality",
            "PASS" if not medications else "FAIL",
            f"status=unanswered/declined; MedicationStatements={len(medications)}",
        )

    for index, medication in enumerate(medications, start=1):
        concept = medication.get("medicationCodeableConcept") or {}
        for coding in concept.get("coding", []) or []:
            if not isinstance(coding, Mapping) or not coding.get("code"):
                continue
            record(
                f"medication.{index}.coding",
                "PASS" if coding.get("system") == RXNORM_SYSTEM else "FAIL",
                f"system={coding.get('system')!r}; code={coding.get('code')!r}",
            )

        dosages = medication.get("dosage") or []
        if dosages and isinstance(dosages[0], Mapping):
            dose_and_rate = dosages[0].get("doseAndRate") or []
            if dose_and_rate and isinstance(dose_and_rate[0], Mapping):
                quantity = dose_and_rate[0].get("doseQuantity") or {}
                value = quantity.get("value") if isinstance(quantity, Mapping) else None
                record(
                    f"medication.{index}.dose",
                    "PASS" if isinstance(value, (int, float)) and value >= 0 else "FAIL",
                    f"dose={quantity}",
                )

    failed = [check for check in checks if check["status"] == "FAIL"]
    return {
        "status": "FAIL" if failed else "PASS",
        "scope": "CAREGIVER_BASELINE",
        "claim": "Phase 1 caregiver plausibility and semantic-preservation checks.",
        "checks": checks,
        "structural": structural,
    }

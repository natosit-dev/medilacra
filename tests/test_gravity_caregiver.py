from __future__ import annotations

from connectathon.gravity_materialize import (
    build_submission_bundle,
    bundle_resources,
    observation_by_loinc,
)
from connectathon.gravity_quality import caregiver_quality_gate
from connectathon.gravity_questionnaire import (
    HEART_RATE_LOINC,
    LOINC_SYSTEM,
    PAIN_LOINC,
    PHQ2_TOTAL,
    QUESTIONNAIRE_VERSION,
    RXNORM_SYSTEM,
    UCUM_SYSTEM,
    build_questionnaire,
)
from connectathon.gravity_response import (
    answer_absent_reason,
    build_questionnaire_response,
    first_answer,
)
from connectathon.gravity_storage import (
    load_questionnaire_responses,
    save_questionnaire_response,
)


PATIENT = {
    "patient_id": "PAT-GRAVITY-001",
    "patient_name": "CAREGIVER, CASEY",
    "date_of_birth": "1982-03-14",
    "sex": "F",
    "phone": "555-0100",
    "address": "1 Test Way",
    "city": "Lowell",
    "state": "MA",
    "zip": "01852",
}

HAPPY_INPUT = {
    "sleep-hours": "6.5",
    "pain-score": 4,
    "phq2-interest": "LA6569-3",
    "phq2-depressed": "LA6568-5",
    "heart-rate": "82",
    "medication-status": True,
    "medications": [
        {
            "name": "Lisinopril 10 MG Oral Tablet",
            "rxnorm": "314076",
            "dose_value": "10",
            "dose_unit": "mg",
            "route": "oral",
            "frequency": "daily",
        }
    ],
}


def _bundle(raw_input=HAPPY_INPUT, declined=None):
    response = build_questionnaire_response(
        PATIENT["patient_id"],
        raw_input,
        declined=set(declined or []),
        response_id="gravity-test-response",
        authored="2026-09-08T22:00:00+00:00",
    )
    bundle, cleanup = build_submission_bundle(PATIENT, response)
    return response, bundle, cleanup


def test_questionnaire_is_standard_fhir_resource_with_expected_baseline_items():
    questionnaire = build_questionnaire()

    assert questionnaire["resourceType"] == "Questionnaire"
    assert questionnaire["version"] == QUESTIONNAIRE_VERSION

    top_level = {item["linkId"]: item for item in questionnaire["item"]}
    assert set(top_level) == {
        "sleep-hours",
        "pain-score",
        "phq2",
        "heart-rate",
        "medication-status",
        "medications",
    }
    assert top_level["sleep-hours"]["type"] == "quantity"
    assert top_level["pain-score"]["code"][0]["code"] == PAIN_LOINC
    assert top_level["heart-rate"]["code"][0]["code"] == HEART_RATE_LOINC
    assert top_level["medications"]["type"] == "group"
    assert top_level["medications"]["repeats"] is True


def test_happy_path_materializes_recognizable_clinical_facts():
    response, bundle, _cleanup = _bundle()

    assert response["resourceType"] == "QuestionnaireResponse"
    assert response["subject"]["reference"] == "Patient/PAT-GRAVITY-001"

    heart = observation_by_loinc(bundle, HEART_RATE_LOINC)
    assert heart is not None
    assert heart["valueQuantity"] == {
        "value": 82.0,
        "unit": "beats/minute",
        "system": UCUM_SYSTEM,
        "code": "/min",
    }

    pain = observation_by_loinc(bundle, PAIN_LOINC)
    assert pain is not None
    assert pain["valueInteger"] == 4

    phq_total = observation_by_loinc(bundle, PHQ2_TOTAL)
    assert phq_total is not None
    assert phq_total["valueInteger"] == 1

    medications = bundle_resources(bundle, "MedicationStatement")
    assert len(medications) == 1
    medication = medications[0]
    coding = medication["medicationCodeableConcept"]["coding"][0]
    assert coding["system"] == RXNORM_SYSTEM
    assert coding["code"] == "314076"
    assert medication["medicationCodeableConcept"]["text"] == "Lisinopril 10 MG Oral Tablet"

    dosage = medication["dosage"][0]
    assert dosage["route"]["text"] == "oral"
    assert dosage["timing"]["code"]["text"] == "daily"
    assert dosage["doseAndRate"][0]["doseQuantity"] == {
        "value": 10.0,
        "unit": "mg",
        "system": UCUM_SYSTEM,
        "code": "mg",
    }


def test_decline_is_preserved_as_standard_data_absent_reason():
    raw = dict(HAPPY_INPUT)
    raw["sleep-hours"] = ""
    response, bundle, _cleanup = _bundle(raw, declined={"sleep-hours"})

    sleep_answer = first_answer(response, "sleep-hours")
    assert answer_absent_reason(sleep_answer) == "asked-declined"

    sleep_observations = [
        observation
        for observation in bundle_resources(bundle, "Observation")
        if ((observation.get("code") or {}).get("coding") or [{}])[0].get("code") == "sleep-hours-24h"
    ]
    assert sleep_observations == []

    report = caregiver_quality_gate(bundle)
    sleep_check = next(check for check in report["checks"] if check["check"] == "sleep.plausibility")
    assert sleep_check["status"] == "PASS"
    assert sleep_check["detail"] == "declined"


def test_phq_total_is_omitted_when_one_component_is_not_answered():
    raw = dict(HAPPY_INPUT)
    raw["phq2-depressed"] = None
    _response, bundle, _cleanup = _bundle(raw)

    assert observation_by_loinc(bundle, PHQ2_TOTAL) is None
    report = caregiver_quality_gate(bundle)
    total_check = next(check for check in report["checks"] if check["check"] == "phq2.total")
    assert total_check["status"] == "PASS"


def test_unusual_positive_heart_rate_is_plausible_but_negative_is_not():
    high = dict(HAPPY_INPUT)
    high["heart-rate"] = "190"
    _response, high_bundle, _cleanup = _bundle(high)
    high_report = caregiver_quality_gate(high_bundle)
    high_check = next(check for check in high_report["checks"] if check["check"] == "heart_rate.plausibility")
    assert high_check["status"] == "PASS"

    negative = dict(HAPPY_INPUT)
    negative["heart-rate"] = "-12"
    _response, negative_bundle, _cleanup = _bundle(negative)
    negative_report = caregiver_quality_gate(negative_bundle)
    negative_check = next(check for check in negative_report["checks"] if check["check"] == "heart_rate.plausibility")
    assert negative_check["status"] == "FAIL"
    assert negative_report["status"] == "FAIL"


def test_out_of_range_pain_fails_plausibility():
    raw = dict(HAPPY_INPUT)
    raw["pain-score"] = 47
    _response, bundle, _cleanup = _bundle(raw)

    report = caregiver_quality_gate(bundle)
    check = next(check for check in report["checks"] if check["check"] == "pain.plausibility")
    assert check["status"] == "FAIL"


def test_corrupt_numeric_input_stays_error_and_does_not_become_observation():
    raw = dict(HAPPY_INPUT)
    raw["heart-rate"] = "potato"
    response, bundle, _cleanup = _bundle(raw)

    answer = first_answer(response, "heart-rate")
    assert answer_absent_reason(answer) == "error"
    assert observation_by_loinc(bundle, HEART_RATE_LOINC) is None

    report = caregiver_quality_gate(bundle)
    parse_check = next(check for check in report["checks"] if check["check"] == "response.parse_errors")
    assert parse_check["status"] == "FAIL"
    assert report["status"] == "FAIL"


def test_bundle_reuses_connectathon_fullurl_and_reference_normalization():
    _response, bundle, cleanup = _bundle()

    assert bundle["resourceType"] == "Bundle"
    assert bundle["type"] == "collection"
    assert cleanup["full_urls_added"] == len(bundle["entry"])

    full_urls = {entry["fullUrl"] for entry in bundle["entry"]}
    assert len(full_urls) == len(bundle["entry"])
    assert all(url.startswith("urn:uuid:") for url in full_urls)

    questionnaire_response = bundle_resources(bundle, "QuestionnaireResponse")[0]
    assert questionnaire_response["subject"]["reference"] in full_urls

    report = caregiver_quality_gate(bundle)
    assert report["structural"]["status"] == "PASS"


def test_expected_terminology_systems_are_preserved():
    _response, bundle, _cleanup = _bundle()

    for loinc_code in (PAIN_LOINC, HEART_RATE_LOINC, PHQ2_TOTAL):
        observation = observation_by_loinc(bundle, loinc_code)
        assert observation is not None
        coding = observation["code"]["coding"][0]
        assert coding["system"] == LOINC_SYSTEM


def test_duckdb_persistence_keeps_fhir_json_and_nested_struct_projection(tmp_path):
    response, bundle, _cleanup = _bundle()
    db_path = str(tmp_path / "gravity-caregiver.duckdb")

    save_questionnaire_response(
        response,
        HAPPY_INPUT,
        bundle=bundle,
        db_path=db_path,
    )
    rows = load_questionnaire_responses(limit=5, db_path=db_path)

    assert len(rows) == 1
    row = rows[0]
    assert row["response_id"] == "gravity-test-response"
    assert row["patient_id"] == "PAT-GRAVITY-001"
    assert row["questionnaire_version"] == QUESTIONNAIRE_VERSION
    assert isinstance(row["items"], list)
    assert any(item["link_id"] == "heart-rate" and item["value_number"] == 82.0 for item in row["items"])
    assert '"resourceType": "QuestionnaireResponse"' in row["fhir_json"]
    assert '"resourceType": "Bundle"' in row["bundle_json"]

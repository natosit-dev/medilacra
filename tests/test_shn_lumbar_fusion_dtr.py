from __future__ import annotations

import json

import pytest

from connectathon.shn_lumbar_fusion import (
    LUMBAR_FUSION_QUESTIONNAIRE,
    build_lumbar_fusion_reality,
)
from connectathon.shn_lumbar_fusion_dtr import (
    build_lumbar_fusion_dtr_request,
    dtr_expected_invariants,
    extract_questionnaire_canonical,
)


def _crd_response(questionnaire: str = LUMBAR_FUSION_QUESTIONNAIRE) -> dict:
    return {
        "cards": [],
        "systemActions": [
            {
                "type": "update",
                "resource": {
                    "resourceType": "ServiceRequest",
                    "extension": [
                        {
                            "url": (
                                "http://hl7.org/fhir/us/davinci-crd/"
                                "StructureDefinition/ext-coverage-information"
                            ),
                            "extension": [
                                {
                                    "url": "questionnaire",
                                    "valueCanonical": questionnaire,
                                }
                            ],
                        }
                    ],
                },
            }
        ],
    }


def _parameter(request: dict, name: str) -> dict:
    return next(p for p in request["parameter"] if p["name"] == name)


def test_questionnaire_is_extracted_from_crd_response():
    assert (
        extract_questionnaire_canonical(_crd_response())
        == LUMBAR_FUSION_QUESTIONNAIRE
    )


def test_missing_questionnaire_stops_dtr_generation():
    with pytest.raises(ValueError, match="no questionnaire canonical"):
        extract_questionnaire_canonical({"cards": [], "systemActions": []})


def test_multiple_questionnaires_stop_dtr_generation():
    response = _crd_response()
    response["systemActions"].append(
        _crd_response("http://example.org/fhir/Questionnaire/Other")[
            "systemActions"
        ][0]
    )
    with pytest.raises(ValueError, match="multiple questionnaire canonicals"):
        extract_questionnaire_canonical(response)


def test_dtr_request_uses_medilacra_patient_coverage_and_live_canonical():
    reality = build_lumbar_fusion_reality(seed=43)
    request = build_lumbar_fusion_dtr_request(_crd_response(), seed=43)

    coverage = _parameter(request, "coverage")["resource"]
    patient = _parameter(request, "referenced")["resource"]
    questionnaire = _parameter(request, "questionnaire")["valueCanonical"]

    assert patient["id"] == reality.patient.patient_id
    assert coverage["id"] == reality.coverage_id
    assert coverage["beneficiary"]["reference"] == (
        f"Patient/{reality.patient.patient_id}"
    )
    assert questionnaire == LUMBAR_FUSION_QUESTIONNAIRE


def test_dtr_request_preserves_network_route_without_reference_fixture_identity():
    request = build_lumbar_fusion_dtr_request(_crd_response(), seed=43)
    coverage = _parameter(request, "coverage")["resource"]
    serialized = json.dumps(request)

    assert coverage["contained"][0]["identifier"][0] == {
        "system": "urn:oid:2.16.840.1.113883.6.300",
        "value": "00301",
    }
    assert "MBR-COVERED" not in serialized
    assert "HomeHealthAssessment" not in serialized


def test_dtr_invariants_record_questionnaire_provenance():
    invariants = dtr_expected_invariants(_crd_response(), seed=43)

    assert invariants["questionnaire_from_crd"] == LUMBAR_FUSION_QUESTIONNAIRE
    assert invariants["patient_reference"].startswith("Patient/ML-")
    assert invariants["coverage_reference"].startswith("Coverage/COV-")

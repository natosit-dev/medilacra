from __future__ import annotations

import copy

import pytest

from connectathon.shn_dtr_questionnaire_response import (
    materialize_questionnaire_response,
)
from connectathon.shn_lumbar_fusion import (
    LUMBAR_FUSION_QUESTIONNAIRE,
    LUMBAR_SPONDYLOLISTHESIS_ICD10,
    build_lumbar_fusion_reality,
)
from connectathon.shn_lumbar_fusion_pas import (
    EXT_DOCUMENT_INFORMATION,
    EXT_REQUESTED_SERVICE,
    PAS_TEMP_CODES,
    SHN_PAYER_IDENTIFIER_SYSTEM,
    SHN_ROUTE_00301,
    X12_PWK01_SYSTEM,
    build_documented_pas_bundle,
    expected_pas_behavior,
    validate_documented_questionnaire_response,
)


def _dtr_response(seed: int = 300) -> dict:
    reality = build_lumbar_fusion_reality(seed)
    return {
        "resourceType": "Parameters",
        "parameter": [
            {
                "name": "packagebundle",
                "resource": {
                    "resourceType": "Bundle",
                    "type": "collection",
                    "entry": [
                        {
                            "resource": {
                                "resourceType": "Questionnaire",
                                "id": "LumbarSpinalFusion",
                                "url": LUMBAR_FUSION_QUESTIONNAIRE,
                                "status": "active",
                                "item": [
                                    {
                                        "linkId": "1",
                                        "text": "Lumbar Spinal Fusion Documentation",
                                        "type": "group",
                                        "item": [
                                            {
                                                "linkId": "1.1",
                                                "text": "Weeks of conservative therapy completed",
                                                "type": "integer",
                                                "required": True,
                                            },
                                            {
                                                "linkId": "1.2",
                                                "text": "Imaging confirms instability or spondylolisthesis",
                                                "type": "boolean",
                                                "required": True,
                                            },
                                        ],
                                    }
                                ],
                            }
                        },
                        {
                            "resource": {
                                "resourceType": "QuestionnaireResponse",
                                "id": "template",
                                "meta": {
                                    "profile": [
                                        "http://hl7.org/fhir/us/davinci-dtr/StructureDefinition/dtr-questionnaireresponse"
                                    ]
                                },
                                "extension": [
                                    {
                                        "url": (
                                            "http://hl7.org/fhir/us/davinci-dtr/"
                                            "StructureDefinition/qr-coverage"
                                        ),
                                        "valueReference": {
                                            "reference": f"Coverage/{reality.coverage_id}"
                                        },
                                    }
                                ],
                                "questionnaire": LUMBAR_FUSION_QUESTIONNAIRE,
                                "status": "in-progress",
                                "subject": {
                                    "reference": f"Patient/{reality.patient.patient_id}"
                                },
                                "item": [
                                    {
                                        "linkId": "1",
                                        "item": [
                                            {"linkId": "1.1"},
                                            {"linkId": "1.2"},
                                        ],
                                    }
                                ],
                            }
                        },
                    ],
                },
            }
        ],
    }


def _completed_qr(seed: int = 300) -> dict:
    qr, _ = materialize_questionnaire_response(_dtr_response(seed), seed)
    return qr


def _resource(bundle: dict, resource_type: str) -> dict:
    matches = [
        entry["resource"]
        for entry in bundle["entry"]
        if entry["resource"]["resourceType"] == resource_type
    ]
    assert len(matches) == 1
    return matches[0]


def _all_relative_references(value):
    if isinstance(value, dict):
        ref = value.get("reference")
        if isinstance(ref, str) and "://" not in ref and not ref.startswith("#"):
            yield ref
        for child in value.values():
            yield from _all_relative_references(child)
    elif isinstance(value, list):
        for child in value:
            yield from _all_relative_references(child)


def test_documented_pas_preserves_patient_coverage_order_and_service_semantics():
    seed = 300
    reality = build_lumbar_fusion_reality(seed)
    bundle = build_documented_pas_bundle(seed, _completed_qr(seed))

    patient = _resource(bundle, "Patient")
    coverage = _resource(bundle, "Coverage")
    order = _resource(bundle, "ServiceRequest")
    claim = _resource(bundle, "Claim")

    assert patient["id"] == reality.patient.patient_id
    assert coverage["id"] == reality.coverage_id
    assert order["id"] == reality.service_request_id
    assert order["code"]["coding"][0]["code"] == "22633"
    assert order["reasonCode"][0]["coding"][0]["code"] == LUMBAR_SPONDYLOLISTHESIS_ICD10
    assert claim["item"][0]["productOrService"]["coding"][0]["code"] == "22633"
    assert claim["diagnosis"][0]["diagnosisCodeableConcept"]["coding"][0]["code"] == LUMBAR_SPONDYLOLISTHESIS_ICD10
    assert claim["item"][0]["diagnosisSequence"] == [1]


def test_pas_routes_through_00301_and_carries_typed_member_id():
    seed = 300
    reality = build_lumbar_fusion_reality(seed)
    bundle = build_documented_pas_bundle(seed, _completed_qr(seed))
    coverage = _resource(bundle, "Coverage")
    patient = _resource(bundle, "Patient")

    assert coverage["payor"][0]["identifier"] == {
        "system": SHN_PAYER_IDENTIFIER_SYSTEM,
        "value": SHN_ROUTE_00301,
    }
    assert coverage["subscriberId"] == reality.transaction.member_id
    assert coverage["identifier"][0]["type"]["coding"][0]["code"] == "MB"
    assert patient["identifier"][0]["type"]["coding"][0]["code"] == "MB"


def test_pas_attaches_completed_qr_as_additional_information():
    bundle = build_documented_pas_bundle(300, _completed_qr(300))
    claim = _resource(bundle, "Claim")
    qr = _resource(bundle, "QuestionnaireResponse")
    info = claim["supportingInfo"][0]

    assert qr["status"] == "completed"
    assert qr["questionnaire"] == LUMBAR_FUSION_QUESTIONNAIRE
    assert info["category"]["coding"][0] == {
        "system": PAS_TEMP_CODES,
        "code": "additionalInformation",
    }
    assert info["valueReference"]["reference"] == f"QuestionnaireResponse/{qr['id']}"

    doc = next(ext for ext in info["extension"] if ext["url"] == EXT_DOCUMENT_INFORMATION)
    report = next(ext for ext in doc["extension"] if ext["url"] == "reportTypeCode")
    coding = report["valueCodeableConcept"]["coding"][0]
    assert coding["system"] == X12_PWK01_SYSTEM
    assert coding["code"] == "OZ"


def test_pas_requested_service_points_to_bundled_service_request():
    bundle = build_documented_pas_bundle(300, _completed_qr(300))
    claim = _resource(bundle, "Claim")
    order = _resource(bundle, "ServiceRequest")
    ext = next(
        ext
        for ext in claim["item"][0]["extension"]
        if ext["url"] == EXT_REQUESTED_SERVICE
    )

    assert ext["valueReference"]["reference"] == f"ServiceRequest/{order['id']}"


def test_every_relative_reference_resolves_inside_bundle():
    bundle = build_documented_pas_bundle(300, _completed_qr(300))
    refs = {
        f"{entry['resource']['resourceType']}/{entry['resource']['id']}"
        for entry in bundle["entry"]
    }
    unresolved = {
        ref
        for ref in _all_relative_references(bundle)
        if ref not in refs
    }
    assert unresolved == set()


def test_pas_does_not_leak_reference_fixture_or_expected_decision():
    bundle = build_documented_pas_bundle(300, _completed_qr(300))
    text = str(bundle)

    assert "MBR-COVERED" not in text
    assert "G0151" not in text
    assert "Certified in total" not in text
    assert "'A1'" not in text


def test_qr_must_be_completed_and_match_reality():
    qr = _completed_qr(300)

    bad_status = copy.deepcopy(qr)
    bad_status["status"] = "in-progress"
    with pytest.raises(ValueError, match="must be completed"):
        validate_documented_questionnaire_response(bad_status, 300)

    bad_subject = copy.deepcopy(qr)
    bad_subject["subject"]["reference"] = "Patient/WRONG"
    with pytest.raises(ValueError, match="subject does not match"):
        validate_documented_questionnaire_response(bad_subject, 300)

    bad_answer = copy.deepcopy(qr)
    bad_answer["item"][0]["item"][0]["answer"][0]["valueInteger"] = 99
    with pytest.raises(ValueError, match="item 1.1"):
        validate_documented_questionnaire_response(bad_answer, 300)


def test_expected_pas_behavior_is_separate_from_request():
    expected = expected_pas_behavior(300)

    assert expected["expected_live_response"] == {
        "http": 200,
        "claim_response_outcome": "complete",
        "review_action_code": "A1",
        "review_action_display": "Certified in total",
        "communication_request_count": 0,
        "authorization_expected": True,
    }


def test_pas_bundle_is_deterministic():
    qr = _completed_qr(300)
    assert build_documented_pas_bundle(300, qr) == build_documented_pas_bundle(300, qr)

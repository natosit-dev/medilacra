from __future__ import annotations

from dataclasses import replace

import pytest

import connectathon.shn_dtr_questionnaire_response as materializer
from connectathon.shn_lumbar_fusion import (
    ICD10_CM_SYSTEM,
    LUMBAR_SPONDYLOLISTHESIS_DISPLAY,
    LUMBAR_SPONDYLOLISTHESIS_ICD10,
    LUMBAR_FUSION_QUESTIONNAIRE,
    build_lumbar_fusion_reality,
)
from connectathon.shn_mvp0 import supporting_fhir


def _dtr_response(seed: int = 43, *, extra_required: bool = False) -> dict:
    reality = build_lumbar_fusion_reality(seed)
    questionnaire_items = [
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
    ]
    if extra_required:
        questionnaire_items[0]["item"].append(
            {
                "linkId": "1.3",
                "text": "Unexpected required payer fact",
                "type": "boolean",
                "required": True,
            }
        )

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
                                "item": questionnaire_items,
                            }
                        },
                        {
                            "resource": {
                                "resourceType": "QuestionnaireResponse",
                                "id": "LumbarSpinalFusion-__unresolved-member",
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
                                "authored": "2026-10-09T17:06:31+00:00",
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


def _leaf_items(response: dict) -> dict[str, dict]:
    group = response["item"][0]
    return {item["linkId"]: item for item in group["item"]}


def test_lumbar_reality_has_specific_dx_and_imaging_finding():
    reality = build_lumbar_fusion_reality(seed=43)

    assert reality.diagnosis_system == ICD10_CM_SYSTEM
    assert reality.diagnosis_code == LUMBAR_SPONDYLOLISTHESIS_ICD10
    assert reality.diagnosis_display == LUMBAR_SPONDYLOLISTHESIS_DISPLAY
    assert reality.prior_imaging is True
    assert reality.imaging_confirms_instability_or_spondylolisthesis is True


def test_lumbar_service_request_projects_diagnosis_without_changing_service_code():
    reality = build_lumbar_fusion_reality(seed=43)
    request = supporting_fhir(reality)["service_request"]

    diagnosis = request["reasonCode"][0]["coding"][0]
    assert diagnosis == {
        "system": ICD10_CM_SYSTEM,
        "code": LUMBAR_SPONDYLOLISTHESIS_ICD10,
        "display": LUMBAR_SPONDYLOLISTHESIS_DISPLAY,
    }
    assert request["code"]["coding"][0]["code"] == "22633"


def test_materializer_answers_returned_questionnaire_from_reality():
    response, trace = materializer.materialize_questionnaire_response(
        _dtr_response(),
        seed=43,
    )
    items = _leaf_items(response)

    assert response["status"] == "completed"
    assert response["questionnaire"] == LUMBAR_FUSION_QUESTIONNAIRE
    assert items["1.1"]["answer"][0]["valueInteger"] == 12
    assert items["1.2"]["answer"][0]["valueBoolean"] is True
    assert trace["diagnosis"]["code"] == LUMBAR_SPONDYLOLISTHESIS_ICD10
    assert [answer["fact"] for answer in trace["answers"]] == [
        "conservative_therapy_weeks",
        "imaging_confirms_instability_or_spondylolisthesis",
    ]


def test_prior_imaging_alone_cannot_answer_imaging_finding(monkeypatch):
    reality = replace(
        build_lumbar_fusion_reality(seed=43),
        prior_imaging=True,
        imaging_confirms_instability_or_spondylolisthesis=None,
    )
    monkeypatch.setattr(
        materializer,
        "build_lumbar_fusion_reality",
        lambda seed: reality,
    )

    with pytest.raises(ValueError, match="imaging_confirms_instability"):
        materializer.materialize_questionnaire_response(_dtr_response(), seed=43)


def test_unknown_required_payer_question_fails_closed():
    with pytest.raises(ValueError, match="has no semantic mapping"):
        materializer.materialize_questionnaire_response(
            _dtr_response(extra_required=True),
            seed=43,
        )


def test_subject_identity_drift_is_rejected():
    response = _dtr_response()
    package = response["parameter"][0]["resource"]
    qr = package["entry"][1]["resource"]
    qr["subject"]["reference"] = "Patient/WRONG"

    with pytest.raises(ValueError, match="subject does not match"):
        materializer.materialize_questionnaire_response(response, seed=43)

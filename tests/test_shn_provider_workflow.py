from __future__ import annotations

from connectathon.shn_lumbar_fusion import (
    LUMBAR_FUSION_QUESTIONNAIRE,
    build_lumbar_fusion_reality,
)
from connectathon.shn_provider.client import SHNResponse
from connectathon.shn_provider.dtr import materialize_documentation
from connectathon.shn_provider.scenario import get_scenario, list_scenarios
from connectathon.shn_provider.workflow import ProviderWorkflow


COVINFO = (
    "http://hl7.org/fhir/us/davinci-crd/StructureDefinition/"
    "ext-coverage-information"
)


def _crd_response(*, questionnaire: bool = True) -> dict:
    children = [
        {"url": "covered", "valueCode": "conditional"},
        {"url": "pa-needed", "valueCode": "auth-needed"},
        {"url": "doc-needed", "valueCode": "clinical"},
        {"url": "doc-purpose", "valueCode": "withpa"},
        {"url": "info-needed", "valueCode": "OTH"},
    ]
    if questionnaire:
        children.append(
            {
                "url": "questionnaire",
                "valueCanonical": LUMBAR_FUSION_QUESTIONNAIRE,
            }
        )
    return {
        "cards": [],
        "systemActions": [
            {
                "type": "update",
                "resource": {
                    "resourceType": "ServiceRequest",
                    "extension": [
                        {
                            "url": COVINFO,
                            "extension": children,
                        }
                    ],
                },
            }
        ],
    }


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
                                                "text": (
                                                    "Imaging confirms instability or "
                                                    "spondylolisthesis"
                                                ),
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
                                        (
                                            "http://hl7.org/fhir/us/davinci-dtr/"
                                            "StructureDefinition/dtr-questionnaireresponse"
                                        )
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


def _pas_response() -> dict:
    return {
        "resourceType": "Bundle",
        "type": "collection",
        "entry": [
            {
                "resource": {
                    "resourceType": "ClaimResponse",
                    "outcome": "complete",
                    "extension": [
                        {
                            "url": (
                                "http://hl7.org/fhir/us/davinci-pas/"
                                "StructureDefinition/extension-reviewAction"
                            ),
                            "extension": [
                                {
                                    "url": "number",
                                    "valueString": "AUTH-0001",
                                }
                            ],
                        },
                        {
                            "url": (
                                "http://hl7.org/fhir/us/davinci-pas/"
                                "StructureDefinition/extension-reviewActionCode"
                            ),
                            "valueCodeableConcept": {
                                "coding": [
                                    {
                                        "code": "A1",
                                        "display": "Certified in total",
                                    }
                                ]
                            },
                        },
                    ],
                }
            }
        ],
    }


def _response(body: dict, cid: str) -> SHNResponse:
    return SHNResponse(
        status_code=200,
        body=body,
        correlation_id=cid,
        sent_correlation_id=cid,
        leg_id=f"leg-{cid}",
        trace_url=f"https://example.invalid/trace/{cid}",
        elapsed_ms=5.0,
    )


class FakeClient:
    def crd(self, payload, *, correlation_prefix):
        return _response(_crd_response(), "crd-cid")

    def dtr(self, payload, *, correlation_prefix):
        return _response(_dtr_response(), "dtr-cid")

    def pas_submit(self, payload, *, correlation_prefix):
        return _response(_pas_response(), "pas-cid")


def test_json_scenario_registry_preserves_string_route_and_machine_notes():
    scenarios = {scenario.id: scenario for scenario in list_scenarios()}

    assert set(scenarios) == {
        "explicit-not-covered",
        "lumbar-fusion-auth",
        "no-rule-default",
    }
    lumbar = scenarios["lumbar-fusion-auth"]
    assert lumbar.payer_route == "00301"
    assert isinstance(lumbar.payer_route, str)
    assert lumbar.notes
    assert lumbar.raw["provenance"]["date"] == "2026-10-10"


def test_config_driven_materializer_uses_exact_reality_facts():
    scenario = get_scenario("lumbar-fusion-auth")
    qr, provenance = materialize_documentation(
        scenario,
        300,
        _dtr_response(300),
    )
    leaves = {item["linkId"]: item for item in qr["item"][0]["item"]}

    assert qr["status"] == "completed"
    assert leaves["1.1"]["answer"][0]["valueInteger"] == 12
    assert leaves["1.2"]["answer"][0]["valueBoolean"] is True
    assert [row["semantic_name"] for row in provenance["answers"]] == [
        "conservative_therapy_weeks",
        "imaging_confirms_instability_or_spondylolisthesis",
    ]


def test_provider_workflow_runs_lumbar_case_to_certification(tmp_path):
    workflow = ProviderWorkflow(
        client=FakeClient(),
        artifact_root=tmp_path,
        persist_artifacts=True,
    )
    case = workflow.create_case("lumbar-fusion-auth", 300)
    workflow.run_to_completion(case)

    assert case.status == "complete"
    assert case.crd.summary["behavior_match"] is True
    assert case.dtr.summary["questionnaire"] == LUMBAR_FUSION_QUESTIONNAIRE
    assert case.questionnaire_response["status"] == "completed"
    assert case.pas.summary["review_action_code"] == "A1"
    assert case.pas.summary["authorization"] == "AUTH-0001"
    assert case.pas.summary["behavior_match"] is True

    case_dir = tmp_path / case.case_id
    assert (case_dir / "manifest.json").exists()
    assert (case_dir / "crd" / "request.json").exists()
    assert (case_dir / "dtr" / "questionnaire_response.json").exists()
    assert (case_dir / "pas" / "decision.json").exists()


def test_provider_workflow_stops_when_live_crd_has_no_questionnaire(tmp_path):
    class NoDTRClient(FakeClient):
        def crd(self, payload, *, correlation_prefix):
            body = {
                "cards": [],
                "systemActions": [
                    {
                        "resource": {
                            "extension": [
                                {
                                    "url": COVINFO,
                                    "extension": [
                                        {"url": "covered", "valueCode": "conditional"},
                                        {
                                            "url": "info-needed",
                                            "valueCode": "detail-code",
                                        },
                                    ],
                                }
                            ]
                        }
                    }
                ],
            }
            return _response(body, "no-dtr-cid")

    workflow = ProviderWorkflow(
        client=NoDTRClient(),
        artifact_root=tmp_path,
    )
    case = workflow.create_case("no-rule-default", 302)
    workflow.run_to_completion(case)

    assert case.status == "complete"
    assert case.crd.summary["questionnaire"] is None
    assert case.dtr.request is None
    assert case.pas.request is None
    assert "no DTR questionnaire" in case.stop_reason

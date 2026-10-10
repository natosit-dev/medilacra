from __future__ import annotations

from pathlib import Path

from connectathon.shn_bulk_pas import build_pas_batch, write_pas_batch
from connectathon.shn_rule_matrix import build_rule_matrix, write_rule_matrix
from connectathon.shn_bulk_dtr import build_bulk_dtr_plan, write_bulk_dtr_plan
from connectathon.shn_dtr_questionnaire_response import (
    materialize_dtr_batch,
    write_materialized_batch,
)
from connectathon.shn_lumbar_fusion import LUMBAR_FUSION_QUESTIONNAIRE


def _successful_crd_response(case: dict) -> dict:
    return {
        "cards": [],
        "systemActions": [
            {
                "type": "update",
                "resource": {
                    "resourceType": "ServiceRequest",
                    "id": case["service_request_id"],
                    "subject": {"reference": f"Patient/{case['patient_id']}"},
                    "insurance": [{"reference": f"Coverage/{case['coverage_id']}"}],
                    "extension": [
                        {
                            "url": (
                                "http://hl7.org/fhir/us/davinci-crd/"
                                "StructureDefinition/ext-coverage-information"
                            ),
                            "extension": [
                                {
                                    "url": "questionnaire",
                                    "valueCanonical": LUMBAR_FUSION_QUESTIONNAIRE,
                                }
                            ],
                        }
                    ],
                },
            }
        ],
    }


def test_pas_batch_can_skip_seed_300(tmp_path, monkeypatch):
    matrix = build_rule_matrix(start_seed=300, count=4)
    matrix_dir = write_rule_matrix(matrix, tmp_path / "matrix")

    for case in matrix["cases"]:
        if case["expected_crd"].get("questionnaire"):
            live = matrix_dir / "live"
            live.mkdir(parents=True, exist_ok=True)
            (live / f"{case['case_id']}.response.json").write_text(
                __import__("json").dumps(_successful_crd_response(case))
            )

    dtr_plan = build_bulk_dtr_plan([matrix_dir])
    dtr_dir = write_bulk_dtr_plan(dtr_plan, tmp_path / "dtr")

    def fake_materialize(dtr_response, seed):
        from connectathon.shn_lumbar_fusion import build_lumbar_fusion_reality
        reality = build_lumbar_fusion_reality(seed)
        qr = {
            "resourceType": "QuestionnaireResponse",
            "id": f"qr-lumbar-fusion-{seed:04d}",
            "meta": {
                "profile": [
                    "http://hl7.org/fhir/us/davinci-dtr/StructureDefinition/dtr-questionnaireresponse"
                ]
            },
            "extension": [
                {
                    "url": "http://hl7.org/fhir/us/davinci-dtr/StructureDefinition/qr-coverage",
                    "valueReference": {"reference": f"Coverage/{reality.coverage_id}"},
                }
            ],
            "questionnaire": LUMBAR_FUSION_QUESTIONNAIRE,
            "status": "completed",
            "subject": {"reference": f"Patient/{reality.patient.patient_id}"},
            "item": [
                {
                    "linkId": "1",
                    "item": [
                        {
                            "linkId": "1.1",
                            "answer": [{"valueInteger": reality.therapy_weeks}],
                        },
                        {
                            "linkId": "1.2",
                            "answer": [
                                {
                                    "valueBoolean": reality.imaging_confirms_instability_or_spondylolisthesis
                                }
                            ],
                        },
                    ],
                }
            ],
        }
        return qr, {
            "answers": [{}, {}],
            "coverage_reference": f"Coverage/{reality.coverage_id}",
            "diagnosis": {
                "system": reality.diagnosis_system,
                "code": reality.diagnosis_code,
                "display": reality.diagnosis_display,
            },
        }

    import connectathon.shn_dtr_questionnaire_response as qrm
    monkeypatch.setattr(qrm, "materialize_questionnaire_response", fake_materialize)

    for case in dtr_plan["cases"]:
        live = dtr_dir / "live"
        live.mkdir(parents=True, exist_ok=True)
        (live / f"{case['case_id']}.response.json").write_text("{}")

    materialized = materialize_dtr_batch(dtr_dir)
    write_materialized_batch(materialized, dtr_dir)

    batch = build_pas_batch(dtr_dir, {300})

    assert batch["count"] == 1
    assert [case["seed"] for case in batch["cases"]] == [303]

    out = write_pas_batch(batch, tmp_path / "pas")
    assert (out / "cases" / "shn_lumbar_fusion_0303" / "pas_request.json").exists()

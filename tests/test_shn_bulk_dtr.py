from __future__ import annotations

import json

import pytest

from connectathon.shn_bulk_dtr import build_bulk_dtr_plan
from connectathon.shn_lumbar_fusion import LUMBAR_FUSION_QUESTIONNAIRE
from connectathon.shn_rule_matrix import build_rule_matrix, write_rule_matrix


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


def _write_response(matrix_dir, case, response):
    live = matrix_dir / "live"
    live.mkdir(parents=True, exist_ok=True)
    (live / f"{case['case_id']}.response.json").write_text(
        json.dumps(response)
    )


def test_bulk_dtr_selects_only_questionnaire_cases(tmp_path):
    matrix = build_rule_matrix(start_seed=300, count=6)
    matrix_dir = write_rule_matrix(matrix, tmp_path / "matrix")

    auth_cases = [
        case for case in matrix["cases"]
        if case["expected_crd"].get("questionnaire")
    ]
    for case in auth_cases:
        _write_response(matrix_dir, case, _successful_crd_response(case))

    plan = build_bulk_dtr_plan([matrix_dir])

    assert plan["count"] == 2
    assert [case["seed"] for case in plan["cases"]] == [300, 303]
    assert all(
        case["questionnaire"] == LUMBAR_FUSION_QUESTIONNAIRE
        for case in plan["cases"]
    )


def test_retry_matrix_can_supply_previously_throttled_response(tmp_path):
    full = build_rule_matrix(start_seed=360, count=3)
    first_dir = write_rule_matrix(full, tmp_path / "first")
    retry_dir = write_rule_matrix(full, tmp_path / "retry")

    auth_case = full["cases"][0]

    _write_response(
        first_dir,
        auth_case,
        {"resourceType": "OperationOutcome", "issue": [{"code": "throttled"}]},
    )
    _write_response(retry_dir, auth_case, _successful_crd_response(auth_case))

    plan = build_bulk_dtr_plan([first_dir, retry_dir])

    assert plan["count"] == 1
    assert plan["cases"][0]["seed"] == 360
    assert str(retry_dir) in plan["cases"][0]["source_crd_response"]


def test_missing_successful_crd_response_fails_closed(tmp_path):
    matrix = build_rule_matrix(start_seed=300, count=1)
    matrix_dir = write_rule_matrix(matrix, tmp_path / "matrix")

    with pytest.raises(ValueError, match="no successful questionnaire-bearing"):
        build_bulk_dtr_plan([matrix_dir])


def test_conflicting_duplicate_case_is_rejected(tmp_path):
    first = build_rule_matrix(start_seed=300, count=1)
    second = build_rule_matrix(start_seed=300, count=1)
    second["cases"][0]["patient_id"] = "Patient-CONFLICT"

    first_dir = write_rule_matrix(first, tmp_path / "first")
    second_dir = write_rule_matrix(second, tmp_path / "second")

    _write_response(first_dir, first["cases"][0], _successful_crd_response(first["cases"][0]))

    with pytest.raises(ValueError, match="conflicting duplicate"):
        build_bulk_dtr_plan([first_dir, second_dir])

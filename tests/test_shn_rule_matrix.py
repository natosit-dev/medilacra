from __future__ import annotations

import json

import pytest

from connectathon.shn_rule_matrix import (
    EXPLICIT_NOT_COVERED_CPT,
    NO_RULE_DEFAULT_CPT,
    SCENARIOS,
    build_rule_case,
    build_rule_matrix,
)


def _order(case: dict) -> dict:
    return case["crd_request"]["context"]["draftOrders"]["entry"][0]["resource"]


def test_rule_matrix_is_balanced_across_three_behaviors():
    matrix = build_rule_matrix(start_seed=200, repeats=3)

    assert matrix["count"] == 9
    assert matrix["scenarios"] == list(SCENARIOS)

    counts = {
        scenario: sum(case["scenario"] == scenario for case in matrix["cases"])
        for scenario in SCENARIOS
    }
    assert counts == {
        "lumbar-fusion-auth": 3,
        "explicit-not-covered": 3,
        "no-rule-default": 3,
    }


def test_rule_matrix_has_unique_identity_per_case():
    cases = build_rule_matrix(start_seed=200, repeats=3)["cases"]

    for field in (
        "patient_id",
        "coverage_id",
        "service_request_id",
        "encounter_id",
        "member_id",
    ):
        assert len({case[field] for case in cases}) == len(cases)


def test_lumbar_fusion_expected_behavior():
    case = build_rule_case("lumbar-fusion-auth", seed=200)

    assert _order(case)["code"]["coding"][0]["code"] == "22633"
    assert case["expected_crd"] == {
        "covered": "conditional",
        "pa-needed": "auth-needed",
        "doc-needed": "clinical",
        "info-needed": "OTH",
        "questionnaire": "http://example.org/fhir/Questionnaire/LumbarSpinalFusion",
    }


def test_explicit_not_covered_expected_behavior():
    case = build_rule_case("explicit-not-covered", seed=201)

    assert _order(case)["code"]["coding"][0]["code"] == EXPLICIT_NOT_COVERED_CPT
    assert case["expected_crd"] == {
        "covered": "not-covered",
        "pa-needed": None,
    }


def test_no_rule_default_expected_behavior():
    case = build_rule_case("no-rule-default", seed=202)

    assert _order(case)["code"]["coding"][0]["code"] == NO_RULE_DEFAULT_CPT
    assert case["expected_crd"] == {
        "covered": "conditional",
        "pa-needed": None,
        "info-needed": "detail-code",
        "questionnaire": None,
    }


def test_not_covered_probe_has_ent_context_without_reference_fixture_identity():
    case = build_rule_case("explicit-not-covered", seed=201)
    reality = case["reality"]
    serialized = json.dumps(case["crd_request"])

    assert reality["entities"]["encounter"]["hospital_service"] == "ENT"
    assert reality["entities"]["encounter"]["attending_provider_specialty"] == "Otolaryngology"
    assert reality["entities"]["encounter"]["attending_provider_taxonomy"] == "207Y00000X"
    assert "MBR-COVERED" not in serialized


def test_rule_matrix_is_deterministic():
    assert build_rule_matrix(200, 3) == build_rule_matrix(200, 3)
    assert build_rule_matrix(200, 3) != build_rule_matrix(201, 3)


def test_rule_matrix_rejects_zero_repeats():
    with pytest.raises(ValueError, match="at least 1"):
        build_rule_matrix(start_seed=200, repeats=0)



def test_rule_matrix_can_generate_exact_100_case_cohort():
    matrix = build_rule_matrix(start_seed=300, count=100)
    cases = matrix["cases"]

    assert matrix["count"] == 100
    assert matrix["requested_count"] == 100
    assert matrix["start_seed"] == 300
    assert matrix["end_seed"] == 399

    counts = {
        scenario: sum(case["scenario"] == scenario for case in cases)
        for scenario in SCENARIOS
    }
    assert counts == {
        "lumbar-fusion-auth": 34,
        "explicit-not-covered": 33,
        "no-rule-default": 33,
    }

    assert len({case["patient_id"] for case in cases}) == 100
    assert len({case["coverage_id"] for case in cases}) == 100
    assert len({case["service_request_id"] for case in cases}) == 100


def test_rule_matrix_rejects_zero_exact_count():
    with pytest.raises(ValueError, match="count must be at least 1"):
        build_rule_matrix(start_seed=300, count=0)

def test_unknown_rule_scenario_is_rejected():
    with pytest.raises(ValueError, match="unknown scenario"):
        build_rule_case("invented-rule", seed=200)

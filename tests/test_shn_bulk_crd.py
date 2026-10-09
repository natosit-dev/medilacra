from __future__ import annotations

import json

import pytest

from connectathon.shn_bulk_crd import build_bulk_lumbar_fusion_batch
from connectathon.shn_lumbar_fusion import (
    LUMBAR_FUSION_CPT,
    LUMBAR_FUSION_QUESTIONNAIRE,
    build_lumbar_fusion_case,
)


def test_bulk_batch_has_distinct_patient_coverage_and_order_identity():
    batch = build_bulk_lumbar_fusion_batch(start_seed=100, count=10)
    cases = batch["cases"]

    assert len(cases) == 10
    assert len({case["patient_id"] for case in cases}) == 10
    assert len({case["coverage_id"] for case in cases}) == 10
    assert len({case["service_request_id"] for case in cases}) == 10
    assert len({case["encounter_id"] for case in cases}) == 10
    assert len({case["member_id"] for case in cases}) == 10


def test_bulk_batch_holds_clinical_and_network_scenario_constant():
    batch = build_bulk_lumbar_fusion_batch(start_seed=100, count=5)

    assert batch["scenario"] == "lumbar-fusion"
    assert batch["payer_route"] == "00301"
    assert batch["service_code"] == LUMBAR_FUSION_CPT
    assert batch["expected_questionnaire"] == LUMBAR_FUSION_QUESTIONNAIRE

    for descriptor in batch["cases"]:
        assert descriptor["service_code"] == LUMBAR_FUSION_CPT
        case = build_lumbar_fusion_case(seed=descriptor["seed"])
        request = case["crd_request"]
        order = request["context"]["draftOrders"]["entry"][0]["resource"]
        route = request["prefetch"]["coverage"]["contained"][0]["identifier"][0]

        assert order["code"]["coding"][0]["code"] == LUMBAR_FUSION_CPT
        assert route["value"] == "00301"


def test_bulk_batch_contains_no_reference_fixture_patient():
    batch = build_bulk_lumbar_fusion_batch(start_seed=100, count=3)
    for descriptor in batch["cases"]:
        case = build_lumbar_fusion_case(seed=descriptor["seed"])
        assert "MBR-COVERED" not in json.dumps(case["crd_request"])


def test_bulk_batch_is_deterministic():
    assert build_bulk_lumbar_fusion_batch(100, 10) == build_bulk_lumbar_fusion_batch(100, 10)
    assert build_bulk_lumbar_fusion_batch(100, 10) != build_bulk_lumbar_fusion_batch(101, 10)


def test_bulk_batch_rejects_empty_cohort():
    with pytest.raises(ValueError, match="at least 1"):
        build_bulk_lumbar_fusion_batch(start_seed=100, count=0)

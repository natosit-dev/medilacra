from __future__ import annotations

import json

from connectathon.shn_lumbar_fusion import (
    LUMBAR_FUSION_CPT,
    LUMBAR_FUSION_QUESTIONNAIRE,
    SPINE_SPECIALTY,
    SPINE_TAXONOMY,
    build_lumbar_fusion_case,
    build_lumbar_fusion_reality,
)
from connectathon.shn_mvp0 import build_reality


def _draft_order(request: dict) -> dict:
    return request["context"]["draftOrders"]["entry"][0]["resource"]


def test_lumbar_fusion_reality_changes_clinical_scenario_not_patient_identity():
    base = build_reality(seed=43)
    reality = build_lumbar_fusion_reality(seed=43)

    assert reality.patient == base.patient
    assert reality.coverage_id == base.coverage_id
    assert reality.payer_id == base.payer_id

    assert reality.case_id == "shn_lumbar_fusion_0043"
    assert reality.encounter.encounter_id != base.encounter.encounter_id
    assert reality.service_request_id != base.service_request_id
    assert reality.service_code == LUMBAR_FUSION_CPT
    assert reality.encounter.assigned_patient_location == "SPINE_CLINIC1"
    assert reality.encounter.hospital_service == "ORTHO"
    assert reality.encounter.attending_provider_taxonomy == SPINE_TAXONOMY
    assert reality.encounter.attending_provider_specialty == SPINE_SPECIALTY


def test_lumbar_fusion_reality_has_supporting_clinical_facts():
    reality = build_lumbar_fusion_reality(seed=43)

    assert reality.therapy_weeks >= 12
    assert reality.prior_imaging is True
    assert reality.neuro_deficit is False


def test_lumbar_fusion_crd_projects_new_order_with_same_patient_and_coverage():
    case = build_lumbar_fusion_case(seed=43)
    reality = build_lumbar_fusion_reality(seed=43)
    request = case["crd_request"]
    order = _draft_order(request)

    assert request["context"]["patientId"] == reality.patient.patient_id
    assert request["prefetch"]["coverage"]["id"] == reality.coverage_id
    assert order["id"] == reality.service_request_id
    assert order["subject"]["reference"] == f"Patient/{reality.patient.patient_id}"
    assert order["insurance"] == [{"reference": f"Coverage/{reality.coverage_id}"}]
    assert order["code"]["coding"][0]["code"] == LUMBAR_FUSION_CPT
    assert order["status"] == "draft"


def test_lumbar_fusion_crd_does_not_reuse_reference_or_mri_order_semantics():
    request = build_lumbar_fusion_case(seed=43)["crd_request"]
    serialized = json.dumps(request)

    assert "MBR-COVERED" not in serialized
    assert '"72148"' not in serialized
    assert LUMBAR_FUSION_CPT in serialized


def test_lumbar_fusion_expected_network_behavior_is_documented_not_invented_in_request():
    case = build_lumbar_fusion_case(seed=43)
    expected = case["expected_shn_behavior"]
    request = case["crd_request"]

    assert expected["service_code"] == LUMBAR_FUSION_CPT
    assert expected["expected_crd"]["questionnaire"] == LUMBAR_FUSION_QUESTIONNAIRE
    assert expected["expected_crd"]["pa-needed"] == "auth-needed"
    assert expected["expected_crd"]["doc-needed"] == "clinical"

    # These are expectations about the payer's future answer, not claims that
    # MediLacra is allowed to place into the outbound CRD request.
    serialized = json.dumps(request)
    assert LUMBAR_FUSION_QUESTIONNAIRE not in serialized
    assert "auth-needed" not in serialized


def test_lumbar_fusion_case_is_deterministic():
    assert build_lumbar_fusion_case(seed=43) == build_lumbar_fusion_case(seed=43)
    assert build_lumbar_fusion_case(seed=43) != build_lumbar_fusion_case(seed=44)

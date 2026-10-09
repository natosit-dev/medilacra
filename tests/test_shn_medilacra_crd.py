from __future__ import annotations

import json

from connectathon.shn_medilacra_crd import (
    SHN_PAYER_IDENTIFIER_SYSTEM,
    SHN_ROUTE_00301,
    build_crd_case,
    build_crd_order_sign_request,
)
from connectathon.shn_mvp0 import build_reality, supporting_fhir


def _draft_order(request: dict) -> dict:
    return request["context"]["draftOrders"]["entry"][0]["resource"]


def test_crd_is_projected_from_medilacra_reality():
    reality = build_reality(seed=43)
    request = build_crd_order_sign_request(reality)
    source = supporting_fhir(reality)

    patient_ref = f"Patient/{reality.patient.patient_id}"
    coverage_ref = f"Coverage/{reality.coverage_id}"
    order = _draft_order(request)

    assert request["hook"] == "order-sign"
    assert request["context"]["patientId"] == reality.patient.patient_id
    assert request["prefetch"]["patient"]["id"] == reality.patient.patient_id
    assert request["prefetch"]["coverage"]["id"] == reality.coverage_id
    assert request["prefetch"]["coverage"]["beneficiary"]["reference"] == patient_ref
    assert order["id"] == reality.service_request_id
    assert order["subject"]["reference"] == patient_ref
    assert order["insurance"] == [{"reference": coverage_ref}]
    assert order["code"] == source["service_request"]["code"]
    assert order["status"] == "draft"


def test_crd_adds_shn_route_only_at_network_boundary():
    reality = build_reality(seed=43)
    source = supporting_fhir(reality)
    request = build_crd_order_sign_request(reality)
    coverage = request["prefetch"]["coverage"]

    # The source reality keeps its own payer identity.
    assert source["coverage"]["payor"] == [{"reference": f"Organization/{reality.payer_id}"}]
    assert source["payer"]["identifier"][0]["system"] == "urn:medilacra:payer-id"

    # The CRD network projection materializes the SHN route separately.
    assert coverage["payor"] == [{"reference": "#shn-payer"}]
    route_identifier = coverage["contained"][0]["identifier"][0]
    assert route_identifier == {
        "system": SHN_PAYER_IDENTIFIER_SYSTEM,
        "value": SHN_ROUTE_00301,
    }


def test_crd_uses_medilacra_patient_not_reference_fixture_member():
    request = build_crd_order_sign_request(build_reality(seed=43))
    serialized = json.dumps(request)

    assert "MBR-COVERED" not in serialized
    assert request["context"]["patientId"].startswith("ML-")


def test_crd_case_is_deterministic_for_seed():
    assert build_crd_case(seed=43) == build_crd_case(seed=43)
    assert build_crd_case(seed=43) != build_crd_case(seed=44)


def test_crd_invariants_match_request():
    case = build_crd_case(seed=43)
    request = case["crd_request"]
    invariants = case["expected_invariants"]
    order = _draft_order(request)

    assert order["subject"]["reference"] == invariants["patient_reference"]
    assert order["insurance"][0]["reference"] == invariants["coverage_reference"]
    assert order["code"] == invariants["service_code"]
    assert request["prefetch"]["coverage"]["contained"][0]["identifier"][0] == invariants["payer_route"]

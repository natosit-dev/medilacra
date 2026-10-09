from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Any

from connectathon.shn_mvp0 import (
    SHNMVP0Reality,
    build_reality,
    reality_manifest,
    supporting_fhir,
)


SHN_PAYER_IDENTIFIER_SYSTEM = "urn:oid:2.16.840.1.113883.6.300"
SHN_ROUTE_00301 = "00301"


def _empty_searchset() -> dict[str, Any]:
    return {"resourceType": "Bundle", "type": "searchset", "total": 0}


def build_crd_order_sign_request(
    reality: SHNMVP0Reality,
    payer_route: str = SHN_ROUTE_00301,
) -> dict[str, Any]:
    """Project one MediLacra reality into a provider-side CRD order-sign request.

    MediLacra remains the source of the patient, coverage and order semantics.
    The SHN payer route is applied only at this network adapter boundary so the
    generated Coverage can be routed through the provider test endpoint.
    """
    fhir = supporting_fhir(reality)
    patient = copy.deepcopy(fhir["patient"])
    coverage = copy.deepcopy(fhir["coverage"])
    service_request = copy.deepcopy(fhir["service_request"])

    patient_ref = f"Patient/{patient['id']}"
    coverage_ref = f"Coverage/{coverage['id']}"

    # CRD draftOrders carries the order while it is still a draft.
    service_request["status"] = "draft"
    service_request["subject"] = {"reference": patient_ref}
    service_request["insurance"] = [{"reference": coverage_ref}]

    # Route selection belongs to the SHN adapter, not to MediLacra's source
    # reality. Preserve the payer name from reality while materializing the
    # identifier that the provider test endpoint routes on.
    source_payer = fhir["payer"]
    coverage["beneficiary"] = {"reference": patient_ref}
    coverage["payor"] = [{"reference": "#shn-payer"}]
    coverage["contained"] = [
        {
            "resourceType": "Organization",
            "id": "shn-payer",
            "name": f"SHN reference payer route {payer_route}",
            "identifier": [
                {
                    "system": SHN_PAYER_IDENTIFIER_SYSTEM,
                    "value": payer_route,
                }
            ],
        }
    ]

    return {
        "hook": "order-sign",
        "hookInstance": f"{reality.case_id}-order-sign",
        "context": {
            "userId": f"Practitioner/{reality.encounter.ordering_provider_id}",
            "patientId": patient["id"],
            "selections": [],
            "draftOrders": {
                "resourceType": "Bundle",
                "type": "collection",
                "entry": [
                    {
                        "fullUrl": (
                            "https://medilacra.example/fhir/"
                            f"ServiceRequest/{service_request['id']}"
                        ),
                        "resource": service_request,
                    }
                ],
            },
        },
        "prefetch": {
            "patient": patient,
            "coverage": coverage,
            "serviceHistory": _empty_searchset(),
            "deviceHistory": _empty_searchset(),
            "medicationHistory": _empty_searchset(),
            "questionnaireResponses": _empty_searchset(),
        },
    }


def crd_expected_invariants(
    reality: SHNMVP0Reality,
    payer_route: str = SHN_ROUTE_00301,
) -> dict[str, Any]:
    fhir = supporting_fhir(reality)
    return {
        "case_id": reality.case_id,
        "projection": "MediLacra reality -> CRD order-sign",
        "patient_reference": f"Patient/{reality.patient.patient_id}",
        "coverage_reference": f"Coverage/{reality.coverage_id}",
        "service_request_reference": f"ServiceRequest/{reality.service_request_id}",
        "service_code": copy.deepcopy(fhir["service_request"]["code"]),
        "source_payer": {
            "reference": f"Organization/{reality.payer_id}",
            "name": reality.transaction.insurance_plan_name,
        },
        "network_payer_substitution": {
            "name": f"SHN reference payer route {payer_route}",
            "identifier": {
                "system": SHN_PAYER_IDENTIFIER_SYSTEM,
                "value": payer_route,
            },
        },
        "payer_route": {
            "system": SHN_PAYER_IDENTIFIER_SYSTEM,
            "value": payer_route,
        },
        "meaning": [
            "CRD is about the same synthetic patient",
            "the draft order is the same MediLacra service request",
            "the order remains insured by the same MediLacra coverage",
            "the synthetic payer is preserved as source reality",
            "the SHN reference payer is an explicit test-network substitution at the adapter boundary",
        ],
    }


def build_crd_case(seed: int = 43, payer_route: str = SHN_ROUTE_00301) -> dict[str, Any]:
    reality = build_reality(seed)
    return {
        "reality": reality_manifest(reality),
        "crd_request": build_crd_order_sign_request(reality, payer_route=payer_route),
        "expected_invariants": crd_expected_invariants(reality, payer_route=payer_route),
    }


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def write_crd_case(case: dict[str, Any], output_dir: str | Path) -> Path:
    path = Path(output_dir)
    path.mkdir(parents=True, exist_ok=True)
    (path / "reality.json").write_bytes(_json_bytes(case["reality"]))
    (path / "crd_request.json").write_bytes(_json_bytes(case["crd_request"]))
    (path / "expected_invariants.json").write_bytes(_json_bytes(case["expected_invariants"]))
    return path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Project one MediLacra synthetic reality into an SHN CRD order-sign request"
    )
    parser.add_argument("--seed", type=int, default=43)
    parser.add_argument("--payer-route", default=SHN_ROUTE_00301)
    parser.add_argument("--out", default="connectathon/results/shn_medilacra_crd")
    args = parser.parse_args()

    case = build_crd_case(seed=args.seed, payer_route=args.payer_route)
    out = write_crd_case(
        case,
        Path(args.out) / case["reality"]["case_id"],
    )
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

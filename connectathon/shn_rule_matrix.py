from __future__ import annotations

import argparse
import json
import uuid
from dataclasses import replace
from pathlib import Path
from typing import Any

from faker import Faker

from connectathon.shn_lumbar_fusion import (
    LUMBAR_FUSION_CPT,
    LUMBAR_FUSION_QUESTIONNAIRE,
    build_lumbar_fusion_case,
)
from connectathon.shn_medilacra_crd import (
    SHN_ROUTE_00301,
    build_crd_case,
    build_crd_order_sign_request,
    crd_expected_invariants,
)
from connectathon.shn_mvp0 import (
    CASE_NAMESPACE,
    SHNMVP0Reality,
    build_reality,
    reality_manifest,
)


EXPLICIT_NOT_COVERED_CPT = "42999"
NO_RULE_DEFAULT_CPT = "72148"

SCENARIOS: tuple[str, ...] = (
    "lumbar-fusion-auth",
    "explicit-not-covered",
    "no-rule-default",
)


def _matrix_id(seed: int, scenario: str, label: str) -> str:
    value = uuid.uuid5(CASE_NAMESPACE, f"{seed}:rule-matrix:{scenario}:{label}")
    return value.hex[:16]


def _provider_name(seed: int, scenario: str) -> str:
    fake = Faker()
    fake.seed_instance(seed + sum(ord(ch) for ch in scenario))
    parts = fake.name().split()
    return f"{parts[-1].upper()}, {parts[0].upper()}"


def build_explicit_not_covered_reality(seed: int) -> SHNMVP0Reality:
    """Build the 42999 rule probe without pretending it has richer clinical facts."""
    base = build_reality(seed)
    scenario = "explicit-not-covered"
    encounter_id = f"ENC-{_matrix_id(seed, scenario, 'encounter')}"
    service_request_id = f"SR-{_matrix_id(seed, scenario, 'service-request')}"
    provider_id = f"ENT-{_matrix_id(seed, scenario, 'provider')}"
    provider_name = _provider_name(seed, scenario)

    encounter = replace(
        base.encounter,
        encounter_id=encounter_id,
        visit_number=f"VN-{_matrix_id(seed, scenario, 'visit')}",
        account_number=f"ACC-{_matrix_id(seed, scenario, 'account')}",
        assigned_patient_location="ENT_CLINIC1",
        hospital_service="ENT",
        ordering_provider_id=provider_id,
        ordering_provider_name=provider_name,
        attending_provider_id=provider_id,
        attending_provider_name=provider_name,
        attending_provider_taxonomy="207Y00000X",
        attending_provider_specialty="Otolaryngology",
        placer_order_number=service_request_id,
        filler_order_number=f"FIL-{_matrix_id(seed, scenario, 'filler-order')}",
    )

    transaction = replace(
        base.transaction,
        transaction_id=str(
            uuid.uuid5(CASE_NAMESPACE, f"{seed}:rule-matrix:{scenario}:transaction")
        ),
        encounter_id=encounter_id,
        authorization_number=f"AUTH-{_matrix_id(seed, scenario, 'authorization')}",
        billing_provider_id=provider_id,
        billing_provider_name=provider_name,
    )

    return replace(
        base,
        case_id=f"shn_not_covered_{seed:04d}",
        encounter=encounter,
        transaction=transaction,
        service_request_id=service_request_id,
        service_code=EXPLICIT_NOT_COVERED_CPT,
        service_display="Unlisted procedure",
    )


def build_rule_case(
    scenario: str,
    seed: int,
    payer_route: str = SHN_ROUTE_00301,
) -> dict[str, Any]:
    if scenario == "lumbar-fusion-auth":
        case = build_lumbar_fusion_case(seed=seed, payer_route=payer_route)
        return {
            **case,
            "scenario": scenario,
            "expected_crd": {
                "covered": "conditional",
                "pa-needed": "auth-needed",
                "doc-needed": "clinical",
                "info-needed": "OTH",
                "questionnaire": LUMBAR_FUSION_QUESTIONNAIRE,
            },
        }

    if scenario == "no-rule-default":
        case = build_crd_case(seed=seed, payer_route=payer_route)
        return {
            **case,
            "scenario": scenario,
            "expected_crd": {
                "covered": "conditional",
                "pa-needed": None,
                "info-needed": "detail-code",
                "questionnaire": None,
            },
        }

    if scenario == "explicit-not-covered":
        reality = build_explicit_not_covered_reality(seed)
        return {
            "scenario": scenario,
            "reality": reality_manifest(reality),
            "crd_request": build_crd_order_sign_request(
                reality,
                payer_route=payer_route,
            ),
            "expected_invariants": crd_expected_invariants(
                reality,
                payer_route=payer_route,
            ),
            "expected_crd": {
                "covered": "not-covered",
                "pa-needed": None,
            },
        }

    raise ValueError(f"unknown scenario: {scenario}")


def build_rule_matrix(
    start_seed: int = 200,
    repeats: int = 3,
    count: int | None = None,
    payer_route: str = SHN_ROUTE_00301,
) -> dict[str, Any]:
    """Build a CRD matrix across three known payer behaviors.

    If count is supplied, generate exactly that many cases by cycling the
    scenarios in a deterministic near-balanced order. Otherwise preserve the
    original repeats * scenario-count behavior.
    """
    if repeats < 1:
        raise ValueError("repeats must be at least 1")
    if count is not None and count < 1:
        raise ValueError("count must be at least 1")

    target_count = count if count is not None else repeats * len(SCENARIOS)

    cases: list[dict[str, Any]] = []
    seed = start_seed

    for i in range(target_count):
        scenario = SCENARIOS[i % len(SCENARIOS)]
        case = build_rule_case(scenario, seed, payer_route=payer_route)
        reality = case["reality"]
        encounter = reality["entities"]["encounter"]
        transaction = reality["entities"]["transaction"]
        order_code = case["crd_request"]["context"]["draftOrders"]["entry"][0]["resource"][
            "code"
        ]["coding"][0]["code"]

        cases.append(
            {
                "seed": seed,
                "scenario": scenario,
                "case_id": reality["case_id"],
                "patient_id": reality["entities"]["patient"]["patient_id"],
                "coverage_id": transaction["insurance_plan_id"],
                "service_request_id": encounter["placer_order_number"],
                "encounter_id": encounter["encounter_id"],
                "member_id": transaction["member_id"],
                "service_code": order_code,
                "expected_crd": case["expected_crd"],
                "request": f"cases/{reality['case_id']}/crd_request.json",
            }
        )
        seed += 1

    count = len(cases)
    identity_fields = (
        "patient_id",
        "coverage_id",
        "service_request_id",
        "encounter_id",
        "member_id",
    )
    for field in identity_fields:
        if len({case[field] for case in cases}) != count:
            raise ValueError(f"rule matrix contains duplicate {field}")

    return {
        "batch_id": f"shn_rule_matrix_{start_seed:04d}_{seed - 1:04d}",
        "payer_route": payer_route,
        "start_seed": start_seed,
        "end_seed": seed - 1,
        "repeats": repeats,
        "requested_count": count,
        "count": len(cases),
        "experimental_variable": "clinical service / payer-rule behavior",
        "scenarios": list(SCENARIOS),
        "cases": cases,
    }


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def write_rule_matrix(
    matrix: dict[str, Any],
    output_root: str | Path,
) -> Path:
    root = Path(output_root) / matrix["batch_id"]
    cases_root = root / "cases"
    cases_root.mkdir(parents=True, exist_ok=True)

    for descriptor in matrix["cases"]:
        case = build_rule_case(
            descriptor["scenario"],
            descriptor["seed"],
            payer_route=matrix["payer_route"],
        )
        path = cases_root / descriptor["case_id"]
        path.mkdir(parents=True, exist_ok=True)
        (path / "reality.json").write_bytes(_json_bytes(case["reality"]))
        (path / "crd_request.json").write_bytes(_json_bytes(case["crd_request"]))
        (path / "expected_invariants.json").write_bytes(
            _json_bytes(case["expected_invariants"])
        )
        (path / "expected_crd.json").write_bytes(_json_bytes(case["expected_crd"]))

    (root / "manifest.json").write_bytes(_json_bytes(matrix))
    return root


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate a mixed MediLacra CRD payer-rule matrix"
    )
    parser.add_argument("--start-seed", type=int, default=200)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument(
        "--count",
        type=int,
        default=None,
        help="Generate exactly this many cases; cycles scenarios near-evenly",
    )
    parser.add_argument("--payer-route", default=SHN_ROUTE_00301)
    parser.add_argument(
        "--out",
        default="connectathon/results/shn_rule_matrix",
    )
    args = parser.parse_args()

    matrix = build_rule_matrix(
        start_seed=args.start_seed,
        repeats=args.repeats,
        count=args.count,
        payer_route=args.payer_route,
    )
    root = write_rule_matrix(matrix, args.out)
    print(root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

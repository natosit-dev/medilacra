from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from connectathon.shn_lumbar_fusion import (
    LUMBAR_FUSION_CPT,
    LUMBAR_FUSION_QUESTIONNAIRE,
    build_lumbar_fusion_case,
    build_lumbar_fusion_reality,
    write_lumbar_fusion_case,
)
from connectathon.shn_medilacra_crd import SHN_ROUTE_00301


def build_bulk_lumbar_fusion_batch(
    start_seed: int = 100,
    count: int = 10,
    payer_route: str = SHN_ROUTE_00301,
) -> dict[str, Any]:
    """Build a cohort that varies patient identity while holding scenario constant."""
    if count < 1:
        raise ValueError("count must be at least 1")

    cases: list[dict[str, Any]] = []
    for seed in range(start_seed, start_seed + count):
        reality = build_lumbar_fusion_reality(seed)
        cases.append(
            {
                "seed": seed,
                "case_id": reality.case_id,
                "patient_id": reality.patient.patient_id,
                "coverage_id": reality.coverage_id,
                "service_request_id": reality.service_request_id,
                "encounter_id": reality.encounter.encounter_id,
                "member_id": reality.transaction.member_id,
                "service_code": reality.service_code,
                "request": f"cases/{reality.case_id}/crd_request.json",
            }
        )

    patient_ids = {case["patient_id"] for case in cases}
    coverage_ids = {case["coverage_id"] for case in cases}
    order_ids = {case["service_request_id"] for case in cases}
    if len(patient_ids) != count:
        raise ValueError("bulk cohort contains duplicate patient ids")
    if len(coverage_ids) != count:
        raise ValueError("bulk cohort contains duplicate coverage ids")
    if len(order_ids) != count:
        raise ValueError("bulk cohort contains duplicate service request ids")

    end_seed = start_seed + count - 1
    return {
        "batch_id": f"shn_bulk_lumbar_fusion_{start_seed:04d}_{end_seed:04d}",
        "scenario": "lumbar-fusion",
        "payer_route": payer_route,
        "service_code": LUMBAR_FUSION_CPT,
        "expected_questionnaire": LUMBAR_FUSION_QUESTIONNAIRE,
        "start_seed": start_seed,
        "end_seed": end_seed,
        "count": count,
        "experimental_variable": "synthetic patient identity",
        "held_constant": [
            "lumbar-fusion clinical scenario",
            f"CPT {LUMBAR_FUSION_CPT}",
            f"SHN route {payer_route}",
            "CRD order-sign projection",
        ],
        "cases": cases,
    }


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def write_bulk_lumbar_fusion_batch(
    batch: dict[str, Any],
    output_root: str | Path,
) -> Path:
    root = Path(output_root) / batch["batch_id"]
    cases_root = root / "cases"
    cases_root.mkdir(parents=True, exist_ok=True)

    for descriptor in batch["cases"]:
        case = build_lumbar_fusion_case(
            seed=descriptor["seed"],
            payer_route=batch["payer_route"],
        )
        write_lumbar_fusion_case(
            case,
            cases_root / descriptor["case_id"],
        )

    (root / "manifest.json").write_bytes(_json_bytes(batch))
    return root


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Generate multiple independent MediLacra lumbar-fusion CRDs "
            "for an SHN bulk identity test"
        )
    )
    parser.add_argument("--start-seed", type=int, default=100)
    parser.add_argument("--count", type=int, default=10)
    parser.add_argument("--payer-route", default=SHN_ROUTE_00301)
    parser.add_argument(
        "--out",
        default="connectathon/results/shn_bulk_crd",
    )
    args = parser.parse_args()

    batch = build_bulk_lumbar_fusion_batch(
        start_seed=args.start_seed,
        count=args.count,
        payer_route=args.payer_route,
    )
    root = write_bulk_lumbar_fusion_batch(batch, args.out)
    print(root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

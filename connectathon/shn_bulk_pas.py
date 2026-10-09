from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from connectathon.shn_lumbar_fusion_pas import (
    build_documented_pas_bundle,
    expected_pas_behavior,
)


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def build_pas_batch(
    dtr_batch_dir: str | Path,
    skip_seeds: set[int] | None = None,
) -> dict[str, Any]:
    batch_dir = Path(dtr_batch_dir)
    manifest_path = batch_dir / "materialized" / "manifest.json"
    if not manifest_path.exists():
        raise ValueError(f"missing materialized DTR manifest: {manifest_path}")

    skip = skip_seeds or set()
    materialized = _load_json(manifest_path)
    cases: list[dict[str, Any]] = []
    payloads: dict[str, dict[str, Any]] = {}
    expected: dict[str, dict[str, Any]] = {}

    for case in materialized.get("cases", []):
        seed = int(case["seed"])
        if seed in skip:
            continue

        case_id = case["case_id"]
        qr_path = batch_dir / "materialized" / case_id / "questionnaire_response.json"
        if not qr_path.exists():
            raise ValueError(f"missing materialized QuestionnaireResponse: {qr_path}")

        qr = _load_json(qr_path)
        bundle = build_documented_pas_bundle(seed, qr)
        exp = expected_pas_behavior(seed)

        cases.append(
            {
                "seed": seed,
                "case_id": case_id,
                "patient_id": case["patient_id"],
                "coverage_id": case["coverage_id"],
                "service_request_id": case["service_request_id"],
                "questionnaire_response": str(qr_path),
                "request": f"cases/{case_id}/pas_request.json",
                "expected": f"cases/{case_id}/expected_pas_behavior.json",
            }
        )
        payloads[case_id] = bundle
        expected[case_id] = exp

    return {
        "batch_id": "shn_bulk_pas_documented",
        "source_dtr_batch": str(batch_dir),
        "count": len(cases),
        "skipped_seeds": sorted(skip),
        "cases": cases,
        "_payloads": payloads,
        "_expected": expected,
    }


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def write_pas_batch(batch: dict[str, Any], output_root: str | Path) -> Path:
    root = Path(output_root) / batch["batch_id"]
    cases_root = root / "cases"
    cases_root.mkdir(parents=True, exist_ok=True)

    for case in batch["cases"]:
        case_id = case["case_id"]
        case_dir = cases_root / case_id
        case_dir.mkdir(parents=True, exist_ok=True)
        (case_dir / "pas_request.json").write_bytes(
            _json_bytes(batch["_payloads"][case_id])
        )
        (case_dir / "expected_pas_behavior.json").write_bytes(
            _json_bytes(batch["_expected"][case_id])
        )

    manifest = {
        key: value
        for key, value in batch.items()
        if key not in {"_payloads", "_expected"}
    }
    (root / "manifest.json").write_bytes(_json_bytes(manifest))
    return root


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build documented PAS requests from the materialized DTR cohort"
    )
    parser.add_argument("--dtr-batch", required=True)
    parser.add_argument(
        "--skip-seed",
        type=int,
        action="append",
        default=[],
        help="Seed already tested separately; may be repeated",
    )
    parser.add_argument(
        "--out",
        default="connectathon/results/shn_bulk_pas",
    )
    args = parser.parse_args()

    batch = build_pas_batch(args.dtr_batch, set(args.skip_seed))
    root = write_pas_batch(batch, args.out)
    print(root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

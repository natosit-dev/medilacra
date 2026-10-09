from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from connectathon.shn_lumbar_fusion_dtr import (
    build_lumbar_fusion_dtr_request,
    dtr_expected_invariants,
    extract_questionnaire_canonical,
)


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def _case_signature(case: dict[str, Any]) -> tuple[Any, ...]:
    return (
        case["case_id"],
        case["patient_id"],
        case["coverage_id"],
        case["service_request_id"],
        case["service_code"],
        (case.get("expected_crd") or {}).get("questionnaire"),
    )


def build_bulk_dtr_plan(
    source_matrix_dirs: list[str | Path],
) -> dict[str, Any]:
    """Build DTR requests only for CRDs that actually selected a questionnaire.

    Multiple source matrices may overlap. This is intentional: a later retry matrix can
    provide a successful CRD response for a case whose first attempt was throttled.
    """
    if not source_matrix_dirs:
        raise ValueError("at least one source matrix is required")

    expected: dict[int, dict[str, Any]] = {}
    successful_response: dict[int, tuple[Path, dict[str, Any], str]] = {}
    source_paths: list[str] = []

    for raw_dir in source_matrix_dirs:
        matrix_dir = Path(raw_dir)
        manifest_path = matrix_dir / "manifest.json"
        if not manifest_path.exists():
            raise ValueError(f"missing matrix manifest: {manifest_path}")

        manifest = _load_json(manifest_path)
        source_paths.append(str(matrix_dir))

        for case in manifest.get("cases", []):
            expected_questionnaire = (case.get("expected_crd") or {}).get("questionnaire")
            if not expected_questionnaire:
                continue

            seed = int(case["seed"])
            if seed in expected:
                if _case_signature(expected[seed]) != _case_signature(case):
                    raise ValueError(f"conflicting duplicate case for seed {seed}")
            else:
                expected[seed] = case

            response_path = matrix_dir / "live" / f"{case['case_id']}.response.json"
            if not response_path.exists():
                continue

            try:
                response = _load_json(response_path)
                canonical = extract_questionnaire_canonical(response)
            except (json.JSONDecodeError, ValueError):
                continue

            if canonical != expected_questionnaire:
                raise ValueError(
                    f"seed {seed} CRD returned questionnaire {canonical!r}; "
                    f"expected {expected_questionnaire!r}"
                )
            successful_response[seed] = (response_path, response, canonical)

    missing = sorted(set(expected) - set(successful_response))
    if missing:
        joined = ", ".join(str(seed) for seed in missing)
        raise ValueError(
            "no successful questionnaire-bearing CRD response found for seeds: "
            + joined
        )

    cases: list[dict[str, Any]] = []
    payloads: dict[str, dict[str, Any]] = {}
    invariants: dict[str, dict[str, Any]] = {}

    for seed in sorted(expected):
        descriptor = expected[seed]
        response_path, response, canonical = successful_response[seed]
        case_id = descriptor["case_id"]

        request = build_lumbar_fusion_dtr_request(response, seed=seed)
        expected_invariants = dtr_expected_invariants(response, seed=seed)

        cases.append(
            {
                "seed": seed,
                "case_id": case_id,
                "patient_id": descriptor["patient_id"],
                "coverage_id": descriptor["coverage_id"],
                "service_request_id": descriptor["service_request_id"],
                "service_code": descriptor["service_code"],
                "questionnaire": canonical,
                "source_crd_response": str(response_path),
                "request": f"cases/{case_id}/dtr_request.json",
            }
        )
        payloads[case_id] = request
        invariants[case_id] = expected_invariants

    seeds = [case["seed"] for case in cases]
    return {
        "batch_id": f"shn_bulk_dtr_{min(seeds):04d}_{max(seeds):04d}",
        "count": len(cases),
        "source_matrices": source_paths,
        "selection_rule": "live CRD response contains exactly one questionnaire canonical",
        "cases": cases,
        "_payloads": payloads,
        "_invariants": invariants,
    }


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def write_bulk_dtr_plan(
    plan: dict[str, Any],
    output_root: str | Path,
) -> Path:
    root = Path(output_root) / plan["batch_id"]
    cases_root = root / "cases"
    cases_root.mkdir(parents=True, exist_ok=True)

    for case in plan["cases"]:
        case_id = case["case_id"]
        path = cases_root / case_id
        path.mkdir(parents=True, exist_ok=True)
        (path / "dtr_request.json").write_bytes(
            _json_bytes(plan["_payloads"][case_id])
        )
        (path / "dtr_expected_invariants.json").write_bytes(
            _json_bytes(plan["_invariants"][case_id])
        )

    manifest = {
        key: value
        for key, value in plan.items()
        if key not in {"_payloads", "_invariants"}
    }
    (root / "manifest.json").write_bytes(_json_bytes(manifest))
    return root


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build DTR requests from successful live CRD rule-matrix responses"
    )
    parser.add_argument(
        "--source-matrix",
        action="append",
        required=True,
        help="Rule-matrix directory; repeat for retry matrices",
    )
    parser.add_argument(
        "--out",
        default="connectathon/results/shn_bulk_dtr",
    )
    args = parser.parse_args()

    plan = build_bulk_dtr_plan(args.source_matrix)
    root = write_bulk_dtr_plan(plan, args.out)
    print(root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

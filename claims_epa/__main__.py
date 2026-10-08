"""Command-line synthetic Claims/ePA dual-format generation.

Examples:
  python -m claims_epa --seed 43 --count 2 --out /tmp/claims-epa
  python -m claims_epa --seed 43 --authorization-status pended
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from .generation import demo_case, generate, write_artifacts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Synthetic Claims/ePA X12 + FHIR R4 MVP")
    parser.add_argument("--seed", type=int, default=43)
    parser.add_argument("--count", type=int, default=1)
    parser.add_argument("--out", default="connectathon/results/claims_epa_mvp")
    parser.add_argument("--authorization-status", choices=["approved", "pended", "denied"],
                        default="approved")
    parser.add_argument("--claim-status", choices=["paid", "denied"], default="paid")
    parser.add_argument("--at", help="fixed ISO run timestamp, e.g. 2026-10-07T23:00:00")
    args = parser.parse_args(argv)

    if not 1 <= args.count <= 99999:
        parser.error("--count must be 1..99999")
    if args.seed < 0 or args.seed + args.count > 1000000:
        parser.error("--seed and --count exceed demo test-identity range")
    run_at = datetime.fromisoformat(args.at) if args.at else datetime.now()
    root = Path(args.out)
    run_stamp = run_at.strftime("%Y%m%d_%H%M%S")
    cases = []
    for idx in range(args.count):
        ordinal = idx + 1
        case = demo_case(
            seed=args.seed + idx,
            run_at=run_at, ordinal=ordinal,
            authorization_status=args.authorization_status,
            claim_status=args.claim_status,
        )
        artifacts = generate(case, run_at)
        path = root / f"CLAIMS_EPA_{run_stamp}_{ordinal:05d}"
        written = write_artifacts(artifacts, path)
        cases.append({
            "claim_exchange_id": case.claim.exchange_id,
            "authorization_exchange_id": case.authorization.exchange_id,
            "claim_status": case.claim_decision.status,
            "authorization_status": case.authorization_decision.status,
            "path": str(path),
            "artifact_count": len(written),
        })
    print(json.dumps({
        "kind": "synthetic-test-only",
        "FHIR_version": "R4 4.0.1",
        "X12_sets": ["837P", "835", "278 request", "278 response"],
        "count": len(cases),
        "cases": cases,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

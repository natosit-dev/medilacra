"""Replay Claims/ePA representations from a persisted core case, without Faker.

Usage: python -m reality.replay --db ./data/medilacra.duckdb \
    --case-id 'run_20261008_200000:00001' --out ./output/replayed
"""
from __future__ import annotations

import argparse
from datetime import datetime

from claims_epa.generation import generate, write_artifacts
from claims_epa.models import (
    AuthorizationDecision, AuthorizationRequest, ClaimDecision, ClaimRouting,
    CoveragePeriods,
    ClaimSubmission, PostalAddress, PayerContact, PayerSubject,
    RemittanceInstructions, SemanticCase, ServiceLine, RequestedService,
)
from reality.persistence import load_case
from utils.db import reader


def reconstruct_claims_case(payload: dict) -> SemanticCase:
    """Reconstruct nested typed dataclasses from exact, versioned stored facts."""
    needed = ("claim_submission", "claim_decision", "authorization_request",
              "authorization_decision", "payer_subject", "payer_contact")
    if any(k not in payload for k in needed):
        raise ValueError("Case lacks core claims/ePA semantic records")
    claim_data = dict(payload["claim_submission"])
    routing = dict(claim_data.pop("routing"))
    routing["patient_address"] = PostalAddress(**routing["patient_address"])
    routing["billing_address"] = PostalAddress(**routing["billing_address"])
    routing["claim_flags"] = tuple(routing["claim_flags"])
    claim_data["routing"] = ClaimRouting(**routing)
    claim_data["line"] = ServiceLine(**claim_data["line"])
    claim_data["coverage_periods"] = CoveragePeriods(**claim_data["coverage_periods"])
    decision_data = dict(payload["claim_decision"])
    if decision_data.get("remittance") is not None:
        decision_data["remittance"] = RemittanceInstructions(**decision_data["remittance"])
    return SemanticCase(
        claim=ClaimSubmission(**claim_data),
        claim_decision=ClaimDecision(**decision_data),
        authorization=AuthorizationRequest(**{
            **payload["authorization_request"],
            "coverage_periods": CoveragePeriods(
                **payload["authorization_request"]["coverage_periods"])
        }),
        authorization_decision=AuthorizationDecision(**payload["authorization_decision"]),
        payer_subject=PayerSubject(**payload["payer_subject"]),
        payer_contact=PayerContact(**payload["payer_contact"]),
        requested_service=RequestedService(**payload["requested_service"]),
    )


def replay_claims_case(db_path: str, case_id: str):
    """Projection-only replay from DuckDB: no source/scenario generation."""
    payload = load_case(db_path, case_id)
    with reader(db_path=db_path) as con:
        row = con.execute(
            """SELECT sr.started_at
               FROM simulation_cases sc JOIN simulation_runs sr USING (run_id)
               WHERE sc.case_id = ?""",
            [case_id],
        ).fetchone()
    if not row or row[0] is None:
        raise ValueError("Case missing original run timestamp")
    run_at = row[0]
    if isinstance(run_at, str):
        run_at = datetime.fromisoformat(run_at)
    return generate(reconstruct_claims_case(payload), run_at)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True)
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    results = replay_claims_case(args.db, args.case_id)
    paths = write_artifacts(results, args.out)
    for kind, path in sorted(paths.items()):
        print(f"{kind}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

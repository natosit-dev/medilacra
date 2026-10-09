"""Read-only DuckDB source-field completeness audit; outputs metadata, never row values.

Usage:
    python -m scripts.audit_reality_duckdb --db ./data/medilacra.duckdb
    python -m scripts.audit_reality_duckdb --db ./data/medilacra.duckdb --out ./output/db_audit.json
"""
from __future__ import annotations

import argparse
from dataclasses import fields
from datetime import datetime, timezone
import json
from pathlib import Path

import duckdb

from hl7_demo.models import Patient, Encounter, Observation, Transaction, CoverageProfile
from payer.models import MemberRecord, EnrollmentRecord, BenefitPlan

EXPECTED = {
    "patients": (Patient, {"zip_code": "zip"}, {"coverage_profile"}),
    "encounters": (Encounter, {"admit_datetime": "admit_ts",
                               "discharge_datetime": "discharge_ts"}, set()),
    "observations": (Observation, {}, set()),
    "transactions": (Transaction, {}, set()),
    "coverage_profiles": (CoverageProfile, {}, set()),
    "payer_members": (MemberRecord, {}, set()),
    "payer_enrollments": (EnrollmentRecord, {}, set()),
    "payer_plans": (BenefitPlan, {}, set()),
}
OTHER_EXPECTED = ("orders", "messages", "simulation_runs", "simulation_cases",
                  "semantic_records", "artifact_index")


def audit_database(path: str) -> dict:
    db_path = Path(path).expanduser().resolve()
    if not db_path.is_file():
        raise FileNotFoundError(f"Cannot audit missing DuckDB file: {db_path}")
    # Never call init_db, never create schema, and never enumerate raw PHI values.
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        tables = {r[0] for r in con.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema='main'"
        ).fetchall()}
        records = {}
        for table in [*EXPECTED, *OTHER_EXPECTED]:
            if table not in tables:
                records[table] = {"exists": False}
                continue
            # Table name is selected from a fixed whitelist, not user input.
            columns = {r[0] for r in con.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema='main' AND table_name=?", [table],
            ).fetchall()}
            row_count = con.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
            row = {"exists": True, "row_count": row_count,
                   "columns": sorted(columns)}
            if table in EXPECTED:
                cls, aliases, exclude = EXPECTED[table]
                expected_fields = [f.name for f in fields(cls) if f.name not in exclude]
                mapping = {f: aliases.get(f, f) for f in expected_fields}
                missing = [f for f, col in mapping.items() if col not in columns]
                row["missing_model_fields"] = missing
                row["mapped_model_fields"] = mapping
                # Distinguish columns existing in schema from values populated in rows.
                row["null_counts"] = {
                    f: con.execute(
                        f'SELECT COUNT(*) - COUNT("{col}") FROM "{table}"'
                    ).fetchone()[0]
                    for f, col in mapping.items() if col in columns
                }
            records[table] = row
        return {
            "audit_version": 1,
            "audited_at_utc": datetime.now(timezone.utc).isoformat(),
            "db_path": str(db_path),
            "read_only": True,
            "contains_row_values": False,
            "tables": records,
            "expected_table_count": len(EXPECTED) + len(OTHER_EXPECTED),
            "missing_tables": [t for t, x in records.items() if not x["exists"]],
        }
    finally:
        con.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True, help="Path to an existing DuckDB database")
    parser.add_argument("--out", default=None, help="Optional JSON report output path")
    args = parser.parse_args(argv)
    result = audit_database(args.db)
    output = json.dumps(result, indent=2, sort_keys=True)
    if args.out:
        output_file = Path(args.out)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text(output + "\n", encoding="utf-8")
    else:
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

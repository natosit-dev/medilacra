#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sys
import time
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from hl7_demo.pipeline import run_pipeline
from utils import db


CONTROL_RE = re.compile(r"ST\*(?:270|271)\*(\d{9})\*")


def _table_count(db_path: str, table: str) -> int:
    with db.reader(db_path=db_path) as con:
        return int(
            con.execute(
                f"SELECT COUNT(*) FROM {table}"
            ).fetchone()[0]
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Generate a scaled MediLacra eligibility workload in X12 and "
            "FHIR R4 4.0.1 through the normal run_pipeline path."
        )
    )
    parser.add_argument(
        "--n",
        type=int,
        default=1000,
        help="Number of patients/encounters to generate.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=4242,
        help="Synthetic generation seed.",
    )
    parser.add_argument(
        "--reports",
        default="./input/reports/*.csv",
        help="Report CSV glob used by the normal pipeline.",
    )
    args = parser.parse_args()

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = Path("./output") / f"x12_scale_{stamp}"
    db_path = Path("./data") / f"medilacra_x12_scale_{stamp}.duckdb"

    out_dir.mkdir(parents=True, exist_ok=True)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    started = time.perf_counter()

    counts = run_pipeline(
        n_patients=args.n,
        report_glob=args.reports,
        seed=args.seed,
        per_encounter=False,
        bulk=True,
        out_dir=str(out_dir),
        miles=0,
        include_labs=False,
        include_sdoh=False,
        include_x12=True,
        include_fhir_eligibility=True,
        persist="duckdb",
        duckdb_path=str(db_path),
    )

    elapsed = time.perf_counter() - started

    x270_files = list(out_dir.glob("X12_270_*.x12"))
    x271_files = list(out_dir.glob("X12_271_*.x12"))
    fhir_request_files = list(
        out_dir.glob(
            "FHIR_R4_4.0.1_CoverageEligibilityRequest_*.ndjson"
        )
    )
    fhir_response_files = list(
        out_dir.glob(
            "FHIR_R4_4.0.1_CoverageEligibilityResponse_*.ndjson"
        )
    )

    if len(x270_files) != 1 or len(x271_files) != 1:
        raise RuntimeError(
            "Expected exactly one bulk 270 file and one bulk 271 file"
        )
    if (
        len(fhir_request_files) != 1
        or len(fhir_response_files) != 1
    ):
        raise RuntimeError(
            "Expected exactly one bulk FHIR request file and one response file"
        )

    x270 = x270_files[0].read_text(encoding="utf-8")
    x271 = x271_files[0].read_text(encoding="utf-8")

    controls = CONTROL_RE.findall(x270) + CONTROL_RE.findall(x271)
    collisions = len(controls) - len(set(controls))

    fhir_request_count = len(
        fhir_request_files[0].read_text(
            encoding="utf-8"
        ).splitlines()
    )
    fhir_response_count = len(
        fhir_response_files[0].read_text(
            encoding="utf-8"
        ).splitlines()
    )

    patient_count = _table_count(str(db_path), "patients")
    member_count = _table_count(str(db_path), "payer_members")
    enrollment_count = _table_count(
        str(db_path),
        "payer_enrollments",
    )

    print(f"Patients:              {patient_count}")
    print(f"Payer members:         {member_count}")
    print(f"Payer enrollments:     {enrollment_count}")
    print(f"X12 270 generated:     {counts.get('X12_270', 0)}")
    print(f"X12 271 generated:     {counts.get('X12_271', 0)}")
    print(
        "FHIR requests:         "
        f"{counts.get('FHIR_ELIGIBILITY_REQUEST', 0)}"
    )
    print(
        "FHIR responses:        "
        f"{counts.get('FHIR_ELIGIBILITY_RESPONSE', 0)}"
    )
    print(f"FHIR request lines:    {fhir_request_count}")
    print(f"FHIR response lines:   {fhir_response_count}")
    print(f"Control collisions:    {collisions}")
    print(f"Elapsed seconds:       {elapsed:.2f}")
    print(f"Output directory:      {out_dir}")
    print(f"DuckDB:                {db_path}")

    expected = args.n
    if patient_count != expected:
        raise RuntimeError(
            f"Expected {expected} patients, found {patient_count}"
        )
    if member_count != expected:
        raise RuntimeError(
            f"Expected {expected} payer members, found {member_count}"
        )
    if enrollment_count != expected:
        raise RuntimeError(
            f"Expected {expected} payer enrollments, found {enrollment_count}"
        )
    if counts.get("X12_270") != expected:
        raise RuntimeError("270 count does not match requested population")
    if counts.get("X12_271") != expected:
        raise RuntimeError("271 count does not match requested population")
    if counts.get("FHIR_ELIGIBILITY_REQUEST") != expected:
        raise RuntimeError(
            "FHIR request count does not match requested population"
        )
    if counts.get("FHIR_ELIGIBILITY_RESPONSE") != expected:
        raise RuntimeError(
            "FHIR response count does not match requested population"
        )
    if fhir_request_count != expected:
        raise RuntimeError(
            "FHIR request NDJSON line count does not match population"
        )
    if fhir_response_count != expected:
        raise RuntimeError(
            "FHIR response NDJSON line count does not match population"
        )
    if collisions:
        raise RuntimeError(
            f"Found {collisions} X12 control-number collisions"
        )


if __name__ == "__main__":
    main()

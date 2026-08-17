"""CLI for experiment-style MediLacra batch generation."""

from __future__ import annotations

import argparse
from time import perf_counter

from .batch_pipeline import run_batch_pipeline
from .config import configure_logging


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("value must be >= 1")
    return parsed


def nonnegative_int(value: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("value must be >= 0")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "MediLacra batch generator with explicit dataset cardinalities "
            "and no external SDOH API enrichment."
        )
    )
    parser.add_argument("--patients", type=positive_int, default=100)
    parser.add_argument(
        "--encounters-per-patient",
        type=positive_int,
        default=1,
    )
    parser.add_argument(
        "--observations-per-encounter",
        type=nonnegative_int,
        default=1,
    )
    parser.add_argument(
        "--transactions-per-encounter",
        type=nonnegative_int,
        default=1,
    )
    parser.add_argument(
        "--report-glob",
        type=str,
        default="./input/reports/*.csv",
    )
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--out-dir", type=str, default="./output")

    output_mode = parser.add_mutually_exclusive_group()
    output_mode.add_argument(
        "--per-encounter",
        action="store_true",
        help="Write one file per encounter/message type.",
    )
    output_mode.add_argument(
        "--bulk",
        action="store_true",
        help="Append each message type to one run-level file (default).",
    )

    parser.add_argument(
        "--no-labs",
        action="store_true",
        help="Skip separate lab ORM/ORU messages.",
    )
    parser.add_argument(
        "--no-vitals",
        action="store_true",
        help="Skip locally generated vital-sign OBXs.",
    )
    parser.add_argument(
        "--no-gender-harmony",
        action="store_true",
        help="Skip Gender Identity, Pronouns, and SPCU OBXs.",
    )
    return parser


def main() -> None:
    configure_logging()
    args = build_parser().parse_args()

    started = perf_counter()
    counts = run_batch_pipeline(
        patients=args.patients,
        encounters_per_patient=args.encounters_per_patient,
        observations_per_encounter=args.observations_per_encounter,
        transactions_per_encounter=args.transactions_per_encounter,
        report_glob=args.report_glob,
        seed=args.seed,
        out_dir=args.out_dir,
        per_encounter=args.per_encounter,
        include_labs=not args.no_labs,
        include_vitals=not args.no_vitals,
        include_gender_harmony=not args.no_gender_harmony,
    )
    elapsed = perf_counter() - started

    entity_count = sum(
        counts[key]
        for key in ("PATIENT", "ENCOUNTER", "OBSERVATION", "TRANSACTION")
    )
    throughput = entity_count / elapsed if elapsed > 0 else 0.0

    print("Generated:")
    print(f"  patients:     {counts['PATIENT']:,}")
    print(f"  encounters:   {counts['ENCOUNTER']:,}")
    print(f"  observations: {counts['OBSERVATION']:,}")
    print(f"  transactions: {counts['TRANSACTION']:,}")
    print("Messages:")
    print(f"  ADT:          {counts['ADT']:,}")
    print(f"  ORU:          {counts['ORU']:,}")
    print(f"  DFT:          {counts['DFT']:,}")
    print(f"  ORM labs:     {counts['ORM']:,}")
    print(f"  ORU labs:     {counts['ORU_LABS']:,}")
    print("Performance:")
    print(f"  elapsed:      {elapsed:.3f}s")
    print(f"  entity rate:  {throughput:,.0f}/s")
    print(f"Output: {args.out_dir}")


if __name__ == "__main__":
    main()

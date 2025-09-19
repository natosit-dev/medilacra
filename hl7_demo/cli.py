import argparse
from .config import AIRNOW_MILES_DEFAULT, configure_logging
from .pipeline import run_pipeline

def main():
    configure_logging()
    parser = argparse.ArgumentParser(description="Local HL7 generator (modular)")
    parser.add_argument("--patients", type=int, default=100)
    parser.add_argument("--report-glob", type=str, default="./input/reports/*.csv")
    parser.add_argument("--seed", type=int, default=None)
    out = parser.add_mutually_exclusive_group()
    out.add_argument("--per-encounter", action="store_true")
    out.add_argument("--bulk", action="store_true")
    parser.add_argument("--out-dir", type=str, default="./output")
    parser.add_argument("--miles", type=int, default=AIRNOW_MILES_DEFAULT)
    args = parser.parse_args()
    per_encounter = args.per_encounter
    bulk = args.bulk or (not args.per_encounter)
    counts = run_pipeline(args.patients, args.report_glob, args.seed, per_encounter, bulk, args.out_dir, args.miles)
    print(f"Generated {counts['ADT']} ADT, {counts['ORU']} ORU, {counts['DFT']} DFT messages -> {args.out_dir}")

if __name__ == "__main__":
    main()

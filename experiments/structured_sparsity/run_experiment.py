from __future__ import annotations

import argparse
import json
import logging
import random
import sys
from pathlib import Path

import pandas as pd
from faker import Faker


# Allow this file to be run directly from the repository root or elsewhere.
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from hl7_demo.generators import (  # noqa: E402
    gen_encounter,
    gen_observation,
    gen_patient,
    gen_transaction,
)
from hl7_demo.reports import load_reports  # noqa: E402

from layouts import (  # noqa: E402
    LAYOUT_TABLES,
    SyntheticCase,
    create_bespoke_db,
    create_canonical_db,
    propagate_zip_change,
    table_row_counts,
)
from workloads import run_workloads  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Conceptual structured-sparsity experiment: hold MediLacra reality "
            "constant while changing how that reality is materialized."
        )
    )
    parser.add_argument("--patients", type=int, default=1000)
    parser.add_argument("--encounters-per-patient", type=int, default=1)
    parser.add_argument("--observations-per-encounter", type=int, default=1)
    parser.add_argument("--transactions-per-encounter", type=int, default=1)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument(
        "--reports",
        default=str(REPO_ROOT / "input" / "reports" / "*.csv"),
    )
    parser.add_argument(
        "--output-dir",
        default=str(REPO_ROOT / "experiments" / "structured_sparsity" / "output"),
    )
    parser.add_argument(
        "--verbose-generation",
        action="store_true",
        help="Keep MediLacra per-entity INFO logging enabled.",
    )
    return parser.parse_args()


def _require_positive(name: str, value: int) -> None:
    if value < 1:
        raise ValueError(f"{name} must be at least 1")


def generate_cases(
    n_patients: int,
    report_glob: str,
    seed: int,
    encounters_per_patient: int,
    observations_per_encounter: int,
    transactions_per_encounter: int,
) -> list[SyntheticCase]:
    _require_positive("--patients", n_patients)
    _require_positive("--encounters-per-patient", encounters_per_patient)
    _require_positive("--observations-per-encounter", observations_per_encounter)
    _require_positive("--transactions-per-encounter", transactions_per_encounter)

    random.seed(seed)
    Faker.seed(seed)

    reports = load_reports(report_glob)
    if observations_per_encounter > len(reports):
        raise ValueError(
            "--observations-per-encounter exceeds the number of available report rows. "
            "This experiment samples distinct reports within each encounter so the "
            "canonical (encounter_id, observation_id) key remains unique."
        )

    cases: list[SyntheticCase] = []

    for _ in range(n_patients):
        patient = gen_patient()
        encounters: list[object] = []
        transactions: list[object] = []
        observations: list[object] = []

        for _encounter_index in range(encounters_per_patient):
            encounter = gen_encounter(patient.patient_id)
            encounters.append(encounter)

            for _transaction_index in range(transactions_per_encounter):
                transactions.append(gen_transaction(encounter.encounter_id))

            # Sample distinct report rows within this encounter. Across different
            # encounters the same report UID may recur safely because the canonical
            # observation key is (encounter_id, observation_id).
            report_indices = random.sample(
                range(len(reports)),
                k=observations_per_encounter,
            )
            for report_index in report_indices:
                observations.append(
                    gen_observation(encounter, reports.iloc[report_index])
                )

        cases.append(
            SyntheticCase(
                patient=patient,
                encounters=tuple(encounters),
                transactions=tuple(transactions),
                observations=tuple(observations),
            )
        )

    return cases


def build_layout_summary(
    canonical_db: Path,
    bespoke_db: Path,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    summary_rows: list[dict] = []
    table_rows: list[dict] = []

    for layout, db_path in (("canonical", canonical_db), ("bespoke", bespoke_db)):
        counts = table_row_counts(db_path, layout)
        summary_rows.append(
            {
                "layout": layout,
                "table_count": len(LAYOUT_TABLES[layout]),
                "total_materialized_rows": sum(counts.values()),
                "patient_zip_copy_tables": 1 if layout == "canonical" else 4,
                "patient_name_copy_tables": 1 if layout == "canonical" else 4,
                "hospital_service_copy_tables": 1 if layout == "canonical" else 5,
            }
        )
        for table, row_count in counts.items():
            table_rows.append(
                {
                    "layout": layout,
                    "table": table,
                    "row_count": row_count,
                }
            )

    return pd.DataFrame(summary_rows), pd.DataFrame(table_rows)


def main() -> None:
    args = parse_args()

    if not args.verbose_generation:
        # The grain experiment can generate tens of thousands of entities.
        # Keep the terminal focused on experiment-level output by default.
        logging.getLogger("MediLacra").setLevel(logging.WARNING)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    canonical_db = output_dir / "canonical.duckdb"
    bespoke_db = output_dir / "bespoke.duckdb"

    expected_encounters = args.patients * args.encounters_per_patient
    expected_observations = expected_encounters * args.observations_per_encounter
    expected_transactions = expected_encounters * args.transactions_per_encounter

    print(
        "Generating one reality, then dual-materializing it:\n"
        f"  patients:                 {args.patients:,}\n"
        f"  encounters/patient:       {args.encounters_per_patient:,}\n"
        f"  observations/encounter:   {args.observations_per_encounter:,}\n"
        f"  transactions/encounter:   {args.transactions_per_encounter:,}\n"
        f"  expected encounters:      {expected_encounters:,}\n"
        f"  expected observations:    {expected_observations:,}\n"
        f"  expected transactions:    {expected_transactions:,}"
    )

    cases = generate_cases(
        n_patients=args.patients,
        report_glob=args.reports,
        seed=args.seed,
        encounters_per_patient=args.encounters_per_patient,
        observations_per_encounter=args.observations_per_encounter,
        transactions_per_encounter=args.transactions_per_encounter,
    )

    print("Materializing canonical layout...")
    create_canonical_db(canonical_db, cases)

    print("Materializing bespoke layout from the same in-memory objects...")
    create_bespoke_db(bespoke_db, cases)

    print("Running identical semantic workloads...")
    query_results = run_workloads(
        canonical_db,
        bespoke_db,
        repeats=args.repeats,
    )
    query_results.to_csv(output_dir / "query_results.csv", index=False)

    layout_summary, table_counts = build_layout_summary(canonical_db, bespoke_db)
    layout_summary.to_csv(output_dir / "layout_summary.csv", index=False)
    table_counts.to_csv(output_dir / "table_row_counts.csv", index=False)

    # One deliberately simple change-propagation test: change the ZIP for the
    # same generated patient in both layouts and count materialized touch points.
    patient_id = cases[0].patient.patient_id
    new_zip = "99999"
    change_results = pd.DataFrame(
        [
            propagate_zip_change(canonical_db, "canonical", patient_id, new_zip),
            propagate_zip_change(bespoke_db, "bespoke", patient_id, new_zip),
        ]
    )
    change_results.to_csv(output_dir / "change_propagation.csv", index=False)

    config = {
        "patients": args.patients,
        "encounters_per_patient": args.encounters_per_patient,
        "observations_per_encounter": args.observations_per_encounter,
        "transactions_per_encounter": args.transactions_per_encounter,
        "seed": args.seed,
        "repeats": args.repeats,
        "expected_patients": args.patients,
        "expected_encounters": expected_encounters,
        "expected_observations": expected_observations,
        "expected_transactions": expected_transactions,
        "note": (
            "patient_activity_report is intentionally flat across observation "
            "and transaction grain; multiple values on both sides therefore "
            "materialize an encounter-local observation x transaction fan-out."
        ),
    }
    (output_dir / "experiment_config.json").write_text(
        json.dumps(config, indent=2),
        encoding="utf-8",
    )

    print("\nQUERY RESULTS")
    print(query_results.to_string(index=False))
    print("\nLAYOUT SUMMARY")
    print(layout_summary.to_string(index=False))
    print("\nTABLE ROW COUNTS")
    print(table_counts.to_string(index=False))
    print("\nCHANGE PROPAGATION")
    print(change_results.to_string(index=False))

    if not bool(query_results["semantic_match"].all()):
        raise SystemExit(
            "At least one workload returned different semantics across layouts. "
            "Inspect query_results.csv before interpreting performance."
        )

    print(f"\nResults written to: {output_dir}")


if __name__ == "__main__":
    main()

from __future__ import annotations

import argparse
import json
import logging
import platform
import random
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from time import perf_counter

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

from cognition import RESULT_COLUMNS, run_cognition_session  # noqa: E402
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
    parser.add_argument(
        "--skip-cognition",
        action="store_true",
        help="Skip the interactive human cognition test after machine measurements.",
    )
    parser.add_argument(
        "--cognition-questions",
        type=int,
        default=5,
        help="Questions per layout in the interactive cognition test (default: 5).",
    )
    parser.add_argument(
        "--cognition-seed",
        type=int,
        default=None,
        help="Optional separate random seed for cognition stimuli/order.",
    )
    parser.add_argument(
        "--cognition-layout-order",
        choices=["random", "canonical-first", "bespoke-first"],
        default="random",
        help="Counterbalancing control for cognition presentation order.",
    )
    return parser.parse_args()


def _require_positive(name: str, value: int) -> None:
    if value < 1:
        raise ValueError(f"{name} must be at least 1")


def _now() -> datetime:
    return datetime.now().astimezone()


def _iso(dt: datetime) -> str:
    return dt.isoformat(timespec="milliseconds")


def _make_run_id(started_at: datetime) -> str:
    # Windows-safe local timestamp with UTC offset, e.g. 20260813T224100-0400.
    return started_at.strftime("%Y%m%dT%H%M%S%z")


def _git_value(*args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(REPO_ROOT), *args],
            check=True,
            capture_output=True,
            text=True,
            timeout=3,
        )
        value = result.stdout.strip()
        return value or None
    except Exception:
        return None


def _git_metadata() -> dict[str, str | None]:
    return {
        "commit": _git_value("rev-parse", "HEAD"),
        "branch": _git_value("rev-parse", "--abbrev-ref", "HEAD"),
    }


def _phase_row(
    phase: str,
    started_perf: float,
    started_at: datetime,
    artifact_path: Path | None = None,
) -> dict[str, object]:
    ended_at = _now()
    row: dict[str, object] = {
        "phase": phase,
        "started_at": _iso(started_at),
        "ended_at": _iso(ended_at),
        "duration_seconds": round(perf_counter() - started_perf, 6),
        "artifact_path": str(artifact_path) if artifact_path else None,
        "artifact_bytes": None,
    }
    if artifact_path is not None and artifact_path.exists():
        row["artifact_bytes"] = artifact_path.stat().st_size
    return row


def _write_json(path: Path, value: dict[str, object]) -> None:
    path.write_text(json.dumps(value, indent=2, default=str), encoding="utf-8")


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
            "The current experiment samples distinct reports within each encounter so "
            "the canonical (encounter_id, observation_id) key remains unique."
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

            # Distinct report rows inside one encounter preserve the canonical
            # (encounter_id, observation_id) primary key while allowing the same
            # report UID to recur safely across separate encounters.
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
    summary_rows: list[dict[str, object]] = []
    table_rows: list[dict[str, object]] = []

    for layout, db_path in (("canonical", canonical_db), ("bespoke", bespoke_db)):
        counts = table_row_counts(db_path, layout)
        db_bytes = db_path.stat().st_size if db_path.exists() else None
        summary_rows.append(
            {
                "layout": layout,
                "table_count": len(LAYOUT_TABLES[layout]),
                "total_materialized_rows": sum(counts.values()),
                "patient_zip_copy_tables": 1 if layout == "canonical" else 4,
                "patient_name_copy_tables": 1 if layout == "canonical" else 4,
                "hospital_service_copy_tables": 1 if layout == "canonical" else 5,
                "db_file_bytes": db_bytes,
                "db_file_mb": round(db_bytes / (1024 * 1024), 3) if db_bytes is not None else None,
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
    _require_positive("--repeats", args.repeats)
    _require_positive("--cognition-questions", args.cognition_questions)

    if not args.verbose_generation:
        logging.getLogger("MediLacra").setLevel(logging.WARNING)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    run_started_at = _now()
    run_started_perf = perf_counter()
    run_id = _make_run_id(run_started_at)
    cognition_seed = args.cognition_seed if args.cognition_seed is not None else args.seed + 101

    artifacts = {
        "canonical_db": output_dir / f"canonical_{run_id}.duckdb",
        "bespoke_db": output_dir / f"bespoke_{run_id}.duckdb",
        "query_results": output_dir / f"query_results_{run_id}.csv",
        "layout_summary": output_dir / f"layout_summary_{run_id}.csv",
        "table_row_counts": output_dir / f"table_row_counts_{run_id}.csv",
        "change_propagation": output_dir / f"change_propagation_{run_id}.csv",
        "run_metrics": output_dir / f"run_metrics_{run_id}.csv",
        "cognition_results": output_dir / f"cognition_results_{run_id}.csv",
        "experiment_config": output_dir / f"experiment_config_{run_id}.json",
    }

    canonical_db = artifacts["canonical_db"]
    bespoke_db = artifacts["bespoke_db"]

    expected_encounters = args.patients * args.encounters_per_patient
    expected_observations = expected_encounters * args.observations_per_encounter
    expected_transactions = expected_encounters * args.transactions_per_encounter

    git_meta = _git_metadata()
    config: dict[str, object] = {
        "run_id": run_id,
        "run_started_at": _iso(run_started_at),
        "run_ended_at": None,
        "status": "running",
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
        "materialization_strategy": "row_at_a_time_parameterized_insert_single_transaction",
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "git": git_meta,
        "artifacts": {name: path.name for name, path in artifacts.items()},
        "cognition": {
            "enabled": not args.skip_cognition,
            "questions_per_layout": args.cognition_questions,
            "seed": cognition_seed,
            "layout_order_requested": args.cognition_layout_order,
            "status": "pending" if not args.skip_cognition else "skipped",
        },
        "note": (
            "patient_activity_report is intentionally flat across observation "
            "and transaction grain; multiple values on both sides therefore "
            "materialize an encounter-local observation x transaction fan-out."
        ),
    }
    _write_json(artifacts["experiment_config"], config)

    print(
        f"RUN ID: {run_id}\n"
        "Generating one reality, then dual-materializing it:\n"
        f"  patients:                 {args.patients:,}\n"
        f"  encounters/patient:       {args.encounters_per_patient:,}\n"
        f"  observations/encounter:   {args.observations_per_encounter:,}\n"
        f"  transactions/encounter:   {args.transactions_per_encounter:,}\n"
        f"  expected encounters:      {expected_encounters:,}\n"
        f"  expected observations:    {expected_observations:,}\n"
        f"  expected transactions:    {expected_transactions:,}"
    )

    phase_rows: list[dict[str, object]] = []

    phase_started_at = _now()
    phase_started_perf = perf_counter()
    cases = generate_cases(
        n_patients=args.patients,
        report_glob=args.reports,
        seed=args.seed,
        encounters_per_patient=args.encounters_per_patient,
        observations_per_encounter=args.observations_per_encounter,
        transactions_per_encounter=args.transactions_per_encounter,
    )
    phase_rows.append(_phase_row("generation", phase_started_perf, phase_started_at))

    print("Materializing canonical layout...")
    phase_started_at = _now()
    phase_started_perf = perf_counter()
    create_canonical_db(canonical_db, cases)
    phase_rows.append(
        _phase_row("canonical_materialization", phase_started_perf, phase_started_at, canonical_db)
    )

    print("Materializing bespoke layout from the same in-memory objects...")
    phase_started_at = _now()
    phase_started_perf = perf_counter()
    create_bespoke_db(bespoke_db, cases)
    phase_rows.append(
        _phase_row("bespoke_materialization", phase_started_perf, phase_started_at, bespoke_db)
    )

    print("Running identical semantic workloads...")
    phase_started_at = _now()
    phase_started_perf = perf_counter()
    query_results = run_workloads(canonical_db, bespoke_db, repeats=args.repeats)
    query_results.to_csv(artifacts["query_results"], index=False)
    phase_rows.append(_phase_row("workloads", phase_started_perf, phase_started_at))

    phase_started_at = _now()
    phase_started_perf = perf_counter()
    layout_summary, table_counts = build_layout_summary(canonical_db, bespoke_db)
    layout_summary.to_csv(artifacts["layout_summary"], index=False)
    table_counts.to_csv(artifacts["table_row_counts"], index=False)
    phase_rows.append(_phase_row("layout_measurement", phase_started_perf, phase_started_at))

    patient_id = cases[0].patient.patient_id
    new_zip = "99999"
    phase_started_at = _now()
    phase_started_perf = perf_counter()
    change_results = pd.DataFrame(
        [
            propagate_zip_change(canonical_db, "canonical", patient_id, new_zip),
            propagate_zip_change(bespoke_db, "bespoke", patient_id, new_zip),
        ]
    )
    change_results.to_csv(artifacts["change_propagation"], index=False)
    phase_rows.append(_phase_row("change_propagation", phase_started_perf, phase_started_at))

    machine_ended_at = _now()
    phase_rows.append(
        {
            "phase": "machine_total",
            "started_at": _iso(run_started_at),
            "ended_at": _iso(machine_ended_at),
            "duration_seconds": round(perf_counter() - run_started_perf, 6),
            "artifact_path": None,
            "artifact_bytes": None,
        }
    )
    pd.DataFrame(phase_rows).to_csv(artifacts["run_metrics"], index=False)

    semantic_ok = bool(query_results["semantic_match"].all())
    config["machine_semantic_match_all"] = semantic_ok
    config["status"] = "machine_complete" if semantic_ok else "semantic_mismatch"
    _write_json(artifacts["experiment_config"], config)

    print("\nQUERY RESULTS")
    print(query_results.to_string(index=False))
    print("\nLAYOUT SUMMARY")
    print(layout_summary.to_string(index=False))
    print("\nTABLE ROW COUNTS")
    print(table_counts.to_string(index=False))
    print("\nCHANGE PROPAGATION")
    print(change_results.to_string(index=False))
    print(f"\nMachine results written with run ID: {run_id}")

    if not semantic_ok:
        config["run_ended_at"] = _iso(_now())
        _write_json(artifacts["experiment_config"], config)
        raise SystemExit(
            "At least one workload returned different semantics across layouts. "
            f"Inspect {artifacts['query_results'].name} before interpreting performance."
        )

    cognition_meta: dict[str, object]
    cognition_results = pd.DataFrame(columns=RESULT_COLUMNS)

    if args.skip_cognition:
        cognition_meta = {
            "status": "skipped",
            "reason": "--skip-cognition was supplied.",
            "questions_completed": 0,
        }
    elif not sys.stdin.isatty():
        cognition_meta = {
            "status": "skipped",
            "reason": "stdin is not an interactive terminal.",
            "questions_completed": 0,
        }
    else:
        phase_started_at = _now()
        phase_started_perf = perf_counter()
        cognition_results, cognition_meta = run_cognition_session(
            cases,
            questions_per_layout=args.cognition_questions,
            seed=cognition_seed,
            layout_order=args.cognition_layout_order,
        )
        cognition_results.to_csv(artifacts["cognition_results"], index=False)
        phase_rows.append(_phase_row("cognition", phase_started_perf, phase_started_at))

    if cognition_results.empty and not artifacts["cognition_results"].exists():
        cognition_results.to_csv(artifacts["cognition_results"], index=False)

    config["cognition"] = {
        **dict(config["cognition"]),
        **cognition_meta,
    }

    run_ended_at = _now()
    phase_rows.append(
        {
            "phase": "run_total",
            "started_at": _iso(run_started_at),
            "ended_at": _iso(run_ended_at),
            "duration_seconds": round(perf_counter() - run_started_perf, 6),
            "artifact_path": None,
            "artifact_bytes": None,
        }
    )
    pd.DataFrame(phase_rows).to_csv(artifacts["run_metrics"], index=False)

    config["run_ended_at"] = _iso(run_ended_at)
    config["status"] = "complete"
    _write_json(artifacts["experiment_config"], config)

    print(f"\nRUN {run_id} COMPLETE")
    print(f"Semantic workloads: {int(query_results['semantic_match'].sum())}/{len(query_results)} matched")
    for _, row in layout_summary.iterrows():
        print(
            f"{row['layout'].capitalize()} rows: {int(row['total_materialized_rows']):,} "
            f"| DB: {float(row['db_file_mb']):,.3f} MB"
        )

    if not cognition_results.empty:
        print("Cognition:")
        for layout, frame in cognition_results.groupby("layout", sort=False):
            correct = int(frame["correct"].sum())
            median_ms = float(frame["reaction_time_ms"].median())
            print(f"  {layout}: {correct}/{len(frame)} correct, median {median_ms / 1000.0:.3f} s")
    else:
        print(f"Cognition: {cognition_meta.get('status')} - {cognition_meta.get('reason')}")

    print(f"Output directory: {output_dir}")
    print(f"Config: {artifacts['experiment_config'].name}")


if __name__ == "__main__":
    main()

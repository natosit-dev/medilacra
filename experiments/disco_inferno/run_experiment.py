from __future__ import annotations

import argparse
import json
import logging
import random
import sys
from datetime import datetime
from pathlib import Path
from random import Random

import pandas as pd
from faker import Faker

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from hl7_demo.generators import gen_encounter, gen_observation, gen_patient, gen_transaction  # noqa: E402
from hl7_demo.reports import load_reports  # noqa: E402
from experiments.structured_sparsity.layouts import SyntheticCase  # noqa: E402

from experiments.disco_inferno.compare import compare_models, control_is_zero  # noqa: E402
from experiments.disco_inferno.corruptions import (  # noqa: E402
    CorruptionResult,
    control,
    drop_identifier,
    duplicate_record,
    null_field,
)
from experiments.disco_inferno.materialize import materialize_cases, save_model  # noqa: E402
from experiments.disco_inferno.reporting import render_report, write_report  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Disco Inferno MVP: generate one MediLacra reality, materialize Beatrice, "
            "then compare it with deterministic cursed copies of the same model."
        )
    )
    parser.add_argument("--patients", type=int, default=100)
    parser.add_argument("--encounters-per-patient", type=int, default=2)
    parser.add_argument("--observations-per-encounter", type=int, default=2)
    parser.add_argument("--transactions-per-encounter", type=int, default=2)
    parser.add_argument("--reality-seed", type=int, default=42)
    parser.add_argument("--inferno-seed", type=int, default=666)
    parser.add_argument("--null-fraction", type=float, default=0.10)
    parser.add_argument("--duplicate-fraction", type=float, default=0.10)
    parser.add_argument(
        "--reports",
        default=str(REPO_ROOT / "input" / "reports" / "*.csv"),
    )
    parser.add_argument(
        "--output-dir",
        default=str(REPO_ROOT / "experiments" / "disco_inferno" / "output"),
    )
    parser.add_argument("--verbose-generation", action="store_true")
    return parser.parse_args()


def _require_positive(name: str, value: int) -> None:
    if value < 1:
        raise ValueError(f"{name} must be at least 1")


def _require_fraction(name: str, value: float) -> None:
    if not 0.0 <= value <= 1.0:
        raise ValueError(f"{name} must be between 0.0 and 1.0 inclusive")


def _now() -> datetime:
    return datetime.now().astimezone()


def _run_id(now: datetime) -> str:
    return now.strftime("%Y%m%dT%H%M%S%z")


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, default=str), encoding="utf-8")


def generate_cases(
    *,
    n_patients: int,
    report_glob: str,
    seed: int,
    encounters_per_patient: int,
    observations_per_encounter: int,
    transactions_per_encounter: int,
) -> list[SyntheticCase]:
    """Reuse the Structured Sparsity generation pattern to create one fixed reality."""

    _require_positive("--patients", n_patients)
    _require_positive("--encounters-per-patient", encounters_per_patient)
    _require_positive("--observations-per-encounter", observations_per_encounter)
    _require_positive("--transactions-per-encounter", transactions_per_encounter)

    random.seed(seed)
    Faker.seed(seed)
    reports = load_reports(report_glob)
    if observations_per_encounter > len(reports):
        raise ValueError("--observations-per-encounter exceeds available distinct report rows")

    cases: list[SyntheticCase] = []
    for _ in range(n_patients):
        patient = gen_patient()
        encounters: list[object] = []
        observations: list[object] = []
        transactions: list[object] = []

        for _encounter_index in range(encounters_per_patient):
            encounter = gen_encounter(patient.patient_id)
            encounters.append(encounter)

            for _transaction_index in range(transactions_per_encounter):
                transactions.append(gen_transaction(encounter.encounter_id))

            report_indices = random.sample(range(len(reports)), k=observations_per_encounter)
            for report_index in report_indices:
                observations.append(gen_observation(encounter, reports.iloc[report_index]))

        cases.append(
            SyntheticCase(
                patient=patient,
                encounters=tuple(encounters),
                transactions=tuple(transactions),
                observations=tuple(observations),
            )
        )
    return cases


def _run_arms(
    beatrice: dict[str, pd.DataFrame],
    inferno_seed: int,
    null_fraction: float,
    duplicate_fraction: float,
) -> dict[str, CorruptionResult]:
    return {
        "Control": control(beatrice),
        "Charon": drop_identifier(
            beatrice,
            "observations",
            "encounter_id",
            identity_field="observation_id",
        ),
        "Null": null_field(
            beatrice,
            "observations",
            "observation_text",
            null_fraction,
            Random(inferno_seed),
            identity_field="observation_id",
        ),
        "Cerberus": duplicate_record(
            beatrice,
            "transactions",
            duplicate_fraction,
            Random(inferno_seed),
            identity_field="transaction_id",
        ),
    }


def main() -> None:
    args = parse_args()
    _require_fraction("--null-fraction", args.null_fraction)
    _require_fraction("--duplicate-fraction", args.duplicate_fraction)
    if not args.verbose_generation:
        logging.getLogger("MediLacra").setLevel(logging.WARNING)

    started = _now()
    run_id = _run_id(started)
    run_dir = Path(args.output_dir) / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    expected_encounters = args.patients * args.encounters_per_patient
    expected_observations = expected_encounters * args.observations_per_encounter
    expected_transactions = expected_encounters * args.transactions_per_encounter

    print("DISCO INFERNO — MVP")
    print(f"Run: {run_id}")
    print(f"Reality seed: {args.reality_seed} | Inferno seed: {args.inferno_seed}")
    print("Generating one reality for Beatrice...")

    cases = generate_cases(
        n_patients=args.patients,
        report_glob=args.reports,
        seed=args.reality_seed,
        encounters_per_patient=args.encounters_per_patient,
        observations_per_encounter=args.observations_per_encounter,
        transactions_per_encounter=args.transactions_per_encounter,
    )
    beatrice = materialize_cases(cases)
    counts = {name: len(frame) for name, frame in beatrice.items()}

    expected = {
        "patients": args.patients,
        "encounters": expected_encounters,
        "observations": expected_observations,
        "transactions": expected_transactions,
    }
    if counts != expected:
        raise RuntimeError(f"Generated reality counts differ from expected counts: {counts} != {expected}")

    save_model(beatrice, run_dir / "beatrice")
    arms = _run_arms(beatrice, args.inferno_seed, args.null_fraction, args.duplicate_fraction)

    manifests: dict[str, object] = {}
    metrics_by_arm: dict[str, pd.DataFrame] = {}
    combined_metrics: list[pd.DataFrame] = []

    for arm_name, result in arms.items():
        arm_slug = arm_name.lower()
        save_model(result.model, run_dir / "inferno" / arm_slug)
        metrics = compare_models(beatrice, result.model, result.manifest)
        metrics.insert(0, "arm", arm_name)
        metrics_by_arm[arm_name] = metrics
        combined_metrics.append(metrics)
        manifests[arm_name] = result.manifest

    control_metrics = metrics_by_arm["Control"]
    if not control_is_zero(control_metrics):
        raise RuntimeError("Control arm reported non-zero damage; comparison harness is not trustworthy")

    pd.concat(combined_metrics, ignore_index=True).to_csv(run_dir / "metrics.csv", index=False)
    manifest = {
        "experiment": "disco_inferno",
        "run_id": run_id,
        "started_at": started.isoformat(timespec="milliseconds"),
        "reality_seed": args.reality_seed,
        "inferno_seed": args.inferno_seed,
        "source_counts": counts,
        "arms": manifests,
        "status": "complete",
    }
    _write_json(run_dir / "manifest.json", manifest)

    report_arms = {
        name: (arms[name].manifest, metrics_by_arm[name].drop(columns=["arm"]))
        for name in arms
    }
    report = render_report(
        run_id=run_id,
        reality_seed=args.reality_seed,
        inferno_seed=args.inferno_seed,
        counts=counts,
        arms=report_arms,
    )
    write_report(run_dir / "DISCO_INFERNO_REPORT.md", report)

    print("\nBEATRICE")
    for name, count in counts.items():
        print(f"  {name:<14} {count:>6,}")
    print("\nMINOS HAS JUDGED THE DATA")
    for name, result in arms.items():
        manifest_row = result.manifest
        print(
            f"  {name:<9} {manifest_row['operator']:<18} "
            f"affected={int(manifest_row.get('affected_rows', 0)):,}"
        )
    print("\nControl delta: 0 — comparison harness intact")
    print(f"Report: {run_dir / 'DISCO_INFERNO_REPORT.md'}")
    print(f"Manifest: {run_dir / 'manifest.json'}")


if __name__ == "__main__":
    main()

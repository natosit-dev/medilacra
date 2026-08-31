from __future__ import annotations

import argparse
import json
import logging
import random
import sys
from datetime import datetime
from pathlib import Path
from random import Random
from typing import Any

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
from experiments.disco_inferno.exports import (  # noqa: E402
    write_bundle_zip,
    write_hl7_exports,
    write_source_duckdb,
)
from experiments.disco_inferno.materialize import materialize_cases, save_model  # noqa: E402
from experiments.disco_inferno.reporting import render_report, write_report  # noqa: E402


IDENTITY_FIELDS = {
    "patients": "patient_id",
    "encounters": "encounter_id",
    "observations": "observation_id",
    "transactions": "transaction_id",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Disco Inferno: generate one MediLacra reality, materialize Beatrice, "
            "then compare it with deterministic cursed copies of the same model."
        )
    )
    parser.add_argument("--patients", type=int, default=100)
    parser.add_argument("--encounters-per-patient", type=int, default=2)
    parser.add_argument("--observations-per-encounter", type=int, default=2)
    parser.add_argument("--transactions-per-encounter", type=int, default=2)
    parser.add_argument("--reality-seed", type=int, default=42)
    parser.add_argument("--inferno-seed", type=int, default=666)
    parser.add_argument("--charon-table", default="observations")
    parser.add_argument("--charon-field", default="encounter_id")
    parser.add_argument("--null-table", default="observations")
    parser.add_argument("--null-field", default="observation_text")
    parser.add_argument("--null-fraction", type=float, default=0.10)
    parser.add_argument("--duplicate-table", default="transactions")
    parser.add_argument("--duplicate-fraction", type=float, default=0.10)
    parser.add_argument("--no-labs", action="store_true")
    sdoh_group = parser.add_mutually_exclusive_group()
    sdoh_group.add_argument(
        "--with-sdoh",
        action="store_true",
        help="Explicitly enable external Census/AirNow/PLACES/BLS SDOH enrichment.",
    )
    sdoh_group.add_argument(
        "--no-sdoh",
        action="store_true",
        help="Deprecated compatibility flag; SDOH is already disabled by default.",
    )
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


def _identity_field(table: str) -> str | None:
    return IDENTITY_FIELDS.get(table)


def _run_arms(
    beatrice: dict[str, pd.DataFrame],
    *,
    inferno_seed: int,
    charon_table: str,
    charon_field: str,
    null_table: str,
    null_field_name: str,
    null_fraction: float,
    duplicate_table: str,
    duplicate_fraction: float,
) -> dict[str, CorruptionResult]:
    """Minos dispatches three independent corruptions from the same Beatrice model."""

    return {
        "Control": control(beatrice),
        "Charon": drop_identifier(
            beatrice,
            charon_table,
            charon_field,
            identity_field=_identity_field(charon_table),
        ),
        "Null": null_field(
            beatrice,
            null_table,
            null_field_name,
            null_fraction,
            Random(inferno_seed),
            identity_field=_identity_field(null_table),
        ),
        "Cerberus": duplicate_record(
            beatrice,
            duplicate_table,
            duplicate_fraction,
            Random(inferno_seed),
            identity_field=_identity_field(duplicate_table),
        ),
    }


def run_experiment(
    *,
    patients: int = 100,
    encounters_per_patient: int = 2,
    observations_per_encounter: int = 2,
    transactions_per_encounter: int = 2,
    reality_seed: int = 42,
    inferno_seed: int = 666,
    charon_table: str = "observations",
    charon_field: str = "encounter_id",
    null_table: str = "observations",
    null_field_name: str = "observation_text",
    null_fraction: float = 0.10,
    duplicate_table: str = "transactions",
    duplicate_fraction: float = 0.10,
    include_labs: bool = True,
    include_sdoh: bool = False,
    report_glob: str | None = None,
    output_dir: str | Path | None = None,
    verbose_generation: bool = False,
) -> dict[str, Any]:
    """Run one deterministic Beatrice-vs-Inferno experiment and persist its artifact bundle."""

    _require_positive("--patients", patients)
    _require_positive("--encounters-per-patient", encounters_per_patient)
    _require_positive("--observations-per-encounter", observations_per_encounter)
    _require_positive("--transactions-per-encounter", transactions_per_encounter)
    _require_fraction("--null-fraction", null_fraction)
    _require_fraction("--duplicate-fraction", duplicate_fraction)

    if not verbose_generation:
        logging.getLogger("MediLacra").setLevel(logging.WARNING)

    report_glob = report_glob or str(REPO_ROOT / "input" / "reports" / "*.csv")
    root_output = Path(output_dir) if output_dir is not None else REPO_ROOT / "experiments" / "disco_inferno" / "output"

    started = _now()
    run_id = _run_id(started)
    run_dir = root_output / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    expected_encounters = patients * encounters_per_patient
    expected_observations = expected_encounters * observations_per_encounter
    expected_transactions = expected_encounters * transactions_per_encounter

    cases = generate_cases(
        n_patients=patients,
        report_glob=report_glob,
        seed=reality_seed,
        encounters_per_patient=encounters_per_patient,
        observations_per_encounter=observations_per_encounter,
        transactions_per_encounter=transactions_per_encounter,
    )
    beatrice = materialize_cases(cases)
    counts = {name: len(frame) for name, frame in beatrice.items()}

    expected = {
        "patients": patients,
        "encounters": expected_encounters,
        "observations": expected_observations,
        "transactions": expected_transactions,
    }
    if counts != expected:
        raise RuntimeError(f"Generated reality counts differ from expected counts: {counts} != {expected}")

    beatrice_dir = run_dir / "beatrice"
    save_model(beatrice, beatrice_dir, file_suffix=run_id)

    source_db = run_dir / f"source_reality_{run_id}.duckdb"
    write_source_duckdb(beatrice, source_db)

    hl7_dir = run_dir / "hl7"
    hl7_artifacts = write_hl7_exports(
        cases,
        hl7_dir,
        run_id=run_id,
        include_labs=include_labs,
        include_sdoh=include_sdoh,
    )

    arms = _run_arms(
        beatrice,
        inferno_seed=inferno_seed,
        charon_table=charon_table,
        charon_field=charon_field,
        null_table=null_table,
        null_field_name=null_field_name,
        null_fraction=null_fraction,
        duplicate_table=duplicate_table,
        duplicate_fraction=duplicate_fraction,
    )

    manifests: dict[str, object] = {}
    metrics_by_arm: dict[str, pd.DataFrame] = {}
    combined_metrics: list[pd.DataFrame] = []
    inferno_dirs: dict[str, Path] = {}

    for arm_name, result in arms.items():
        arm_slug = arm_name.lower()
        arm_dir = run_dir / "inferno" / arm_slug
        inferno_dirs[arm_name] = arm_dir
        save_model(result.model, arm_dir, file_suffix=run_id)
        metrics = compare_models(beatrice, result.model, result.manifest)
        metrics.insert(0, "arm", arm_name)
        metrics_by_arm[arm_name] = metrics
        combined_metrics.append(metrics)
        manifests[arm_name] = result.manifest

    control_metrics = metrics_by_arm["Control"]
    if not control_is_zero(control_metrics):
        raise RuntimeError("Control arm reported non-zero damage; comparison harness is not trustworthy")

    metrics_path = run_dir / f"metrics_{run_id}.csv"
    pd.concat(combined_metrics, ignore_index=True).to_csv(metrics_path, index=False)

    manifest = {
        "experiment": "disco_inferno",
        "run_id": run_id,
        "started_at": started.isoformat(timespec="milliseconds"),
        "reality_seed": reality_seed,
        "inferno_seed": inferno_seed,
        "source_counts": counts,
        "settings": {
            "patients": patients,
            "encounters_per_patient": encounters_per_patient,
            "observations_per_encounter": observations_per_encounter,
            "transactions_per_encounter": transactions_per_encounter,
            "charon": {"table": charon_table, "field": charon_field},
            "null": {"table": null_table, "field": null_field_name, "fraction": null_fraction},
            "cerberus": {"table": duplicate_table, "fraction": duplicate_fraction},
            "include_labs": include_labs,
            "include_sdoh": include_sdoh,
        },
        "hl7": {
            "message_counts": hl7_artifacts["counts"],
            "files": {name: path.name for name, path in hl7_artifacts["paths"].items()},
        },
        "source_reality_duckdb": source_db.name,
        "arms": manifests,
        "status": "complete",
    }

    manifest_path = run_dir / f"manifest_{run_id}.json"
    _write_json(manifest_path, manifest)

    report_arms = {
        name: (arms[name].manifest, metrics_by_arm[name].drop(columns=["arm"]))
        for name in arms
    }
    report = render_report(
        run_id=run_id,
        reality_seed=reality_seed,
        inferno_seed=inferno_seed,
        counts=counts,
        arms=report_arms,
    )
    report_path = run_dir / f"DISCO_INFERNO_REPORT_{run_id}.md"
    write_report(report_path, report)

    bundle_path = run_dir / f"DISCO_INFERNO_{run_id}.zip"
    write_bundle_zip(run_dir, bundle_path)

    artifacts = {
        "report": report_path,
        "manifest": manifest_path,
        "metrics": metrics_path,
        "source_duckdb": source_db,
        "bundle": bundle_path,
        **{f"hl7_{name.lower()}": path for name, path in hl7_artifacts["paths"].items()},
    }

    return {
        "run_id": run_id,
        "run_dir": run_dir,
        "cases": cases,
        "beatrice": beatrice,
        "arms": arms,
        "metrics_by_arm": metrics_by_arm,
        "manifest": manifest,
        "artifacts": artifacts,
        "beatrice_dir": beatrice_dir,
        "inferno_dirs": inferno_dirs,
    }


def main() -> None:
    args = parse_args()

    print("DISCO INFERNO — MVP")
    print(f"Reality seed: {args.reality_seed} | Inferno seed: {args.inferno_seed}")
    print("Generating one reality for Beatrice...")

    result = run_experiment(
        patients=args.patients,
        encounters_per_patient=args.encounters_per_patient,
        observations_per_encounter=args.observations_per_encounter,
        transactions_per_encounter=args.transactions_per_encounter,
        reality_seed=args.reality_seed,
        inferno_seed=args.inferno_seed,
        charon_table=args.charon_table,
        charon_field=args.charon_field,
        null_table=args.null_table,
        null_field_name=args.null_field,
        null_fraction=args.null_fraction,
        duplicate_table=args.duplicate_table,
        duplicate_fraction=args.duplicate_fraction,
        include_labs=not args.no_labs,
        include_sdoh=bool(args.with_sdoh),
        report_glob=args.reports,
        output_dir=args.output_dir,
        verbose_generation=args.verbose_generation,
    )

    run_id = result["run_id"]
    counts = {name: len(frame) for name, frame in result["beatrice"].items()}
    arms = result["arms"]

    print(f"Run: {run_id}")
    print("\nBEATRICE")
    for name, count in counts.items():
        print(f"  {name:<14} {count:>6,}")
    print("\nMINOS HAS JUDGED THE DATA")
    for name, arm_result in arms.items():
        manifest_row = arm_result.manifest
        print(
            f"  {name:<9} {manifest_row['operator']:<18} "
            f"affected={int(manifest_row.get('affected_rows', 0)):,}"
        )
    print("\nControl delta: 0 — comparison harness intact")
    print(f"Report: {result['artifacts']['report']}")
    print(f"Manifest: {result['artifacts']['manifest']}")
    print(f"Source reality DuckDB: {result['artifacts']['source_duckdb']}")
    print(f"Bundle: {result['artifacts']['bundle']}")


if __name__ == "__main__":
    main()

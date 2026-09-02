from __future__ import annotations

import io
import json
import shutil
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from connectathon.preflight import control_quality_gate, preflight_pair
from experiments.disco_inferno.fhir_corruptions import apply_fhir_mutation, sha256_json


DEFAULT_SCENARIOS: tuple[dict[str, Any], ...] = (
    {
        "case_id": "case_000_control",
        "label": "Control — untouched FHIR",
        "operator": "control",
        "resource": None,
        "path": None,
        "expected": {
            "sam": None,
            "dimension": None,
            "status": "NO_INTRODUCED_FAILURE",
            "provisional": False,
        },
    },
    {
        "case_id": "case_001_availability",
        "label": "Availability — remove Patient.identifier",
        "operator": "remove_element",
        "resource": "Patient",
        "path": "identifier",
        "expected": {
            "sam": "ATTR_ISPOPULATED",
            "dimension": "AV_UNPOP",
            "status": "FAIL",
            "provisional": True,
        },
    },
    {
        "case_id": "case_002_code_system",
        "label": "Availability — remove Observation coding system",
        "operator": "remove_coding_component",
        "resource": "Observation",
        "path": "code.coding[0].system",
        "expected": {
            "sam": "CONCEPT_HASCODESYSTEM",
            "dimension": "AV_UNPOP",
            "status": "FAIL",
            "provisional": True,
        },
    },
    {
        "case_id": "case_003_invalid_member",
        "label": "Conformity — replace Observation code with known non-member",
        "operator": "replace_value",
        "resource": "Observation",
        "path": "code.coding[0].code",
        "replacement": "ZZZ-NOT-A-VALID-CODE",
        "expected": {
            "sam": "CONCEPT_ISVALIDMEMBER",
            "dimension": "CONF_INCOMP",
            "status": "FAIL",
            "provisional": True,
        },
    },
)


def utc_run_id() -> str:
    return datetime.now().astimezone().strftime("%Y%m%dT%H%M%S%z")


def scenario_lookup() -> dict[str, dict[str, Any]]:
    return {scenario["case_id"]: scenario for scenario in DEFAULT_SCENARIOS}


def selected_scenarios(case_ids: Iterable[str] | None = None) -> list[dict[str, Any]]:
    if case_ids is None:
        return [dict(item) for item in DEFAULT_SCENARIOS]
    lookup = scenario_lookup()
    selected: list[dict[str, Any]] = []
    for case_id in case_ids:
        if case_id not in lookup:
            raise KeyError(f"Unknown Connectathon scenario: {case_id}")
        selected.append(dict(lookup[case_id]))
    return selected


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build_scenario_pack(
    baseline_bundle: dict[str, Any],
    output_root: str | Path = "connectathon/results",
    case_ids: Iterable[str] | None = None,
    mutation_seed: int = 666,
    run_id: str | None = None,
    source_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Materialize the control + selected one-defect FHIR cases to disk.

    A scenario pack is only created when the unmutated baseline passes the local control
    quality gate. Intentional mutants are then checked only for structural ingest shape.
    """
    control_gate = control_quality_gate(baseline_bundle)
    if control_gate["status"] != "PASS":
        failed = [row["check"] for row in control_gate["checks"] if row["status"] == "FAIL"]
        raise ValueError(
            "Baseline failed the PIQI control quality gate; refusing to build mutants. "
            f"Failed checks: {', '.join(failed)}"
        )

    run_id = run_id or utc_run_id()
    run_dir = Path(output_root) / run_id
    if run_dir.exists():
        raise FileExistsError(f"Connectathon run already exists: {run_dir}")
    run_dir.mkdir(parents=True, exist_ok=False)

    cases: list[dict[str, Any]] = []
    try:
        _write_json(run_dir / "control_quality_gate.json", control_gate)

        for scenario in selected_scenarios(case_ids):
            case_id = scenario["case_id"]
            case_dir = run_dir / "cases" / case_id
            case_dir.mkdir(parents=True, exist_ok=False)

            mutant, manifest = apply_fhir_mutation(
                baseline_bundle,
                scenario,
                mutation_seed=mutation_seed,
            )
            manifest["source"] = dict(source_metadata or {})
            manifest["scenario_label"] = scenario["label"]
            manifest["experiment_contract"] = {
                "one_declared_mutation": scenario["operator"] != "control",
                "raw_baseline_preserved": True,
                "baseline_control_gate": "PASS",
                "track_targets_provisional": bool(scenario.get("expected", {}).get("provisional")),
            }

            preflight = preflight_pair(baseline_bundle, mutant)

            baseline_path = case_dir / "baseline.fhir.json"
            mutant_path = case_dir / "mutant.fhir.json"
            manifest_path = case_dir / "manifest.json"
            preflight_path = case_dir / "preflight.json"

            _write_json(baseline_path, baseline_bundle)
            _write_json(mutant_path, mutant)
            _write_json(manifest_path, manifest)
            _write_json(preflight_path, preflight)

            cases.append(
                {
                    "case_id": case_id,
                    "label": scenario["label"],
                    "operator": scenario["operator"],
                    "resource": scenario.get("resource"),
                    "path": scenario.get("path"),
                    "expected_sam": scenario.get("expected", {}).get("sam"),
                    "expected_dimension": scenario.get("expected", {}).get("dimension"),
                    "expected_status": scenario.get("expected", {}).get("status"),
                    "preflight": preflight["status"],
                    "baseline_sha256": manifest["baseline_sha256"],
                    "mutant_sha256": manifest["mutant_sha256"],
                    "changed_paths": manifest["changed_paths"],
                    "case_dir": str(case_dir),
                }
            )

        summary = {
            "run_id": run_id,
            "run_dir": str(run_dir),
            "mutation_seed": mutation_seed,
            "baseline_sha256": sha256_json(baseline_bundle),
            "baseline_control_gate": control_gate["status"],
            "source": dict(source_metadata or {}),
            "cases": cases,
            "external_piqi_execution": "NOT_RUN",
            "note": (
                "Baseline passed the local PIQI control quality gate. Case preflight then checks "
                "self-contained Bundle shape only; external PIQI ingest has not yet been exercised."
            ),
        }
        _write_json(run_dir / "run_manifest.json", summary)
        return summary
    except Exception:
        shutil.rmtree(run_dir, ignore_errors=True)
        raise


def zip_run_directory(run_dir: str | Path) -> bytes:
    run_path = Path(run_dir)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(run_path.rglob("*")):
            if path.is_file():
                archive.write(path, arcname=path.relative_to(run_path))
    return buffer.getvalue()


def load_case(run_dir: str | Path, case_id: str) -> dict[str, Any]:
    case_dir = Path(run_dir) / "cases" / case_id
    return {
        "baseline": json.loads((case_dir / "baseline.fhir.json").read_text(encoding="utf-8")),
        "mutant": json.loads((case_dir / "mutant.fhir.json").read_text(encoding="utf-8")),
        "manifest": json.loads((case_dir / "manifest.json").read_text(encoding="utf-8")),
        "preflight": json.loads((case_dir / "preflight.json").read_text(encoding="utf-8")),
    }

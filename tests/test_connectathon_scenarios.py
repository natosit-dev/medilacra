from __future__ import annotations

import json
from pathlib import Path

from connectathon.scenarios import build_scenario_pack, load_case, zip_run_directory


def _bundle() -> dict:
    patient_url = "urn:uuid:11111111-1111-4111-8111-111111111111"
    obs_url = "urn:uuid:22222222-2222-4222-8222-222222222222"
    return {
        "resourceType": "Bundle",
        "type": "collection",
        "id": "bundle-test",
        "entry": [
            {
                "fullUrl": patient_url,
                "resource": {
                    "resourceType": "Patient",
                    "id": "patient-1",
                    "identifier": [{"system": "urn:mrn", "value": "MRN1"}],
                },
            },
            {
                "fullUrl": obs_url,
                "resource": {
                    "resourceType": "Observation",
                    "id": "obs-1",
                    "status": "final",
                    "subject": {"reference": patient_url},
                    "code": {
                        "coding": [
                            {
                                "system": "http://loinc.org",
                                "code": "4548-4",
                                "display": "Hemoglobin A1c",
                            }
                        ]
                    },
                    "valueQuantity": {
                        "value": 6.1,
                        "unit": "%",
                        "system": "http://unitsofmeasure.org",
                        "code": "%",
                    },
                },
            },
        ],
    }


def test_build_pack_writes_control_and_mutant_artifacts(tmp_path: Path):
    run = build_scenario_pack(
        _bundle(),
        output_root=tmp_path,
        case_ids=["case_000_control", "case_002_code_system"],
        mutation_seed=666,
        run_id="test-run",
        source_metadata={"message_type": "ORU^R01"},
    )

    run_dir = Path(run["run_dir"])
    assert (run_dir / "run_manifest.json").exists()
    assert (run_dir / "control_quality_gate.json").exists()
    assert len(run["cases"]) == 2
    assert run["baseline_control_gate"] == "PASS"

    control = load_case(run_dir, "case_000_control")
    mutant = load_case(run_dir, "case_002_code_system")

    assert control["baseline"] == control["mutant"]
    assert mutant["baseline"] != mutant["mutant"]
    assert mutant["manifest"]["expected"]["sam"] == "CONCEPT_HASCODESYSTEM"
    assert mutant["preflight"]["status"] == "PASS"

    manifest = json.loads((run_dir / "run_manifest.json").read_text(encoding="utf-8"))
    assert manifest["external_piqi_execution"] == "NOT_RUN"
    assert manifest["source"]["message_type"] == "ORU^R01"

    zipped = zip_run_directory(run_dir)
    assert zipped[:2] == b"PK"

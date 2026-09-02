from __future__ import annotations

import copy

from experiments.disco_inferno.fhir_corruptions import (
    apply_fhir_mutation,
    get_path,
    sha256_json,
)


def _bundle() -> dict:
    return {
        "resourceType": "Bundle",
        "type": "message",
        "id": "bundle-1",
        "entry": [
            {
                "resource": {
                    "resourceType": "Patient",
                    "id": "patient-1",
                    "identifier": [{"system": "urn:mrn", "value": "MRN1"}],
                }
            },
            {
                "resource": {
                    "resourceType": "Observation",
                    "id": "obs-1",
                    "status": "final",
                    "code": {
                        "coding": [
                            {
                                "system": "http://loinc.org",
                                "code": "4548-4",
                                "display": "Hemoglobin A1c",
                            }
                        ]
                    },
                    "valueQuantity": {"value": 6.1, "unit": "%"},
                }
            },
        ],
    }


def test_control_produces_zero_delta():
    baseline = _bundle()
    mutant, manifest = apply_fhir_mutation(
        baseline,
        {
            "case_id": "case_control",
            "operator": "control",
            "expected": {"status": "NO_INTRODUCED_FAILURE"},
        },
        mutation_seed=666,
    )

    assert mutant == baseline
    assert manifest["baseline_sha256"] == manifest["mutant_sha256"]
    assert manifest["changed_paths"] == []


def test_remove_code_system_changes_exactly_one_path_without_touching_baseline():
    baseline = _bundle()
    original = copy.deepcopy(baseline)
    baseline_hash = sha256_json(baseline)

    mutant, manifest = apply_fhir_mutation(
        baseline,
        {
            "case_id": "case_code_system",
            "operator": "remove_coding_component",
            "resource": "Observation",
            "path": "code.coding[0].system",
            "expected": {"sam": "CONCEPT_HASCODESYSTEM", "status": "FAIL"},
        },
        mutation_seed=666,
    )

    assert baseline == original
    assert sha256_json(baseline) == baseline_hash
    observation = mutant["entry"][1]["resource"]
    assert "system" not in observation["code"]["coding"][0]
    assert manifest["mutation"]["before"] == "http://loinc.org"
    assert manifest["mutation"]["after"] is None
    assert manifest["changed_paths"] == ["entry[1].resource.code.coding[0].system"]


def test_replace_value_is_deterministic():
    spec = {
        "case_id": "case_invalid_member",
        "operator": "replace_value",
        "resource": "Observation",
        "path": "code.coding[0].code",
        "replacement": "ZZZ-NOT-A-VALID-CODE",
        "expected": {"sam": "CONCEPT_ISVALIDMEMBER", "status": "FAIL"},
    }

    mutant_a, manifest_a = apply_fhir_mutation(_bundle(), spec, mutation_seed=42)
    mutant_b, manifest_b = apply_fhir_mutation(_bundle(), spec, mutation_seed=42)

    assert mutant_a == mutant_b
    assert manifest_a["mutation"] == manifest_b["mutation"]
    assert get_path(mutant_a["entry"][1]["resource"], "code.coding[0].code") == "ZZZ-NOT-A-VALID-CODE"

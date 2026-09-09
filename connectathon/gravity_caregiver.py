"""Public Phase 1 API for the MediLacra Gravity caregiver baseline.

Implementation is split by responsibility so the questionnaire definition, response capture,
FHIR materialization, quality checks, and storage can evolve independently without creating a
new healthcare ontology.
"""

from __future__ import annotations

import io
import json
import zipfile
from typing import Any, Mapping

from connectathon.gravity_materialize import (
    build_submission_bundle,
    bundle_resources,
    extract_clinical_resources,
    observation_by_loinc,
)
from connectathon.gravity_quality import caregiver_quality_gate
from connectathon.gravity_questionnaire import (
    QUESTIONNAIRE_ID,
    QUESTIONNAIRE_URL,
    QUESTIONNAIRE_VERSION,
    build_questionnaire,
)
from connectathon.gravity_response import (
    build_patient_resource,
    build_questionnaire_response,
)
from connectathon.gravity_storage import (
    init_questionnaire_storage,
    load_questionnaire_responses,
    save_questionnaire_response,
)


ARTIFACT_FILENAMES = {
    "questionnaire": f"caregiver_health_baseline_questionnaire_v{QUESTIONNAIRE_VERSION}.json",
    "questionnaire_response": "caregiver_health_questionnaire_response.json",
    "bundle": "caregiver_health_phase1_bundle.json",
    "quality": "caregiver_health_quality_report.json",
    "cleanup": "caregiver_health_bundle_cleanup.json",
}


def build_artifact_files(result: Mapping[str, Any]) -> dict[str, bytes]:
    """Serialize every Phase 1 output artifact as an individually downloadable JSON file."""
    files: dict[str, bytes] = {}
    for key, filename in ARTIFACT_FILENAMES.items():
        if key not in result:
            continue
        files[filename] = json.dumps(
            result[key],
            indent=2,
            sort_keys=True,
            default=str,
        ).encode("utf-8")
    return files


def build_artifact_zip(result: Mapping[str, Any]) -> bytes:
    """Package the complete Phase 1 output set into one in-memory ZIP archive."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        for filename, payload in build_artifact_files(result).items():
            archive.writestr(filename, payload)
    return buffer.getvalue()


__all__ = [
    "QUESTIONNAIRE_ID",
    "QUESTIONNAIRE_URL",
    "QUESTIONNAIRE_VERSION",
    "ARTIFACT_FILENAMES",
    "build_questionnaire",
    "build_patient_resource",
    "build_questionnaire_response",
    "extract_clinical_resources",
    "build_submission_bundle",
    "bundle_resources",
    "observation_by_loinc",
    "caregiver_quality_gate",
    "init_questionnaire_storage",
    "save_questionnaire_response",
    "load_questionnaire_responses",
    "build_artifact_files",
    "build_artifact_zip",
]

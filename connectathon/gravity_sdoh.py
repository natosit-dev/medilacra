"""Public API for the MediLacra Gravity SDOH baseline."""

from __future__ import annotations

import io
import json
import zipfile
from typing import Any, Mapping

from connectathon.gravity_sdoh_hl7v2 import build_sdoh_oru
from connectathon.gravity_sdoh_materialize import (
    build_submission_bundle, extract_sdoh_resources, observations_by_loinc,
)
from connectathon.gravity_sdoh_quality import sdoh_quality_gate
from connectathon.gravity_sdoh_questionnaire import (
    QUESTIONNAIRE_ID, QUESTIONNAIRE_URL, QUESTIONNAIRE_VERSION, build_questionnaire,
)
from connectathon.gravity_sdoh_response import (
    answers_for, build_questionnaire_response, derive_hvs_risk,
)
from connectathon.gravity_response import build_patient_resource
from connectathon.gravity_storage import (
    init_questionnaire_storage, load_questionnaire_responses, save_questionnaire_response,
)

ARTIFACT_FILENAMES={
    "questionnaire":f"sdoh_baseline_questionnaire_v{QUESTIONNAIRE_VERSION}.json",
    "questionnaire_response":"sdoh_questionnaire_response.json",
    "bundle":"sdoh_baseline_bundle.json",
    "hl7v2":"sdoh_baseline_oru_r01.hl7",
    "quality":"sdoh_quality_report.json",
    "cleanup":"sdoh_bundle_cleanup.json",
}

def build_artifact_files(result: Mapping[str,Any]) -> dict[str,bytes]:
    files={}
    for key,filename in ARTIFACT_FILENAMES.items():
        if key not in result:
            continue
        value=result[key]
        if isinstance(value,bytes):
            payload=value
        elif isinstance(value,str):
            payload=value.encode("utf-8")
        else:
            payload=json.dumps(value,indent=2,sort_keys=True,default=str).encode("utf-8")
        files[filename]=payload
    return files

def build_artifact_zip(result: Mapping[str,Any]) -> bytes:
    buffer=io.BytesIO()
    with zipfile.ZipFile(buffer,mode="w",compression=zipfile.ZIP_DEFLATED) as archive:
        for filename,payload in build_artifact_files(result).items():
            archive.writestr(filename,payload)
    return buffer.getvalue()

__all__=[
    "QUESTIONNAIRE_ID","QUESTIONNAIRE_URL","QUESTIONNAIRE_VERSION",
    "ARTIFACT_FILENAMES","build_questionnaire","build_questionnaire_response",
    "derive_hvs_risk","answers_for","build_patient_resource",
    "extract_sdoh_resources","build_submission_bundle","observations_by_loinc",
    "build_sdoh_oru","sdoh_quality_gate","init_questionnaire_storage",
    "save_questionnaire_response","load_questionnaire_responses",
    "build_artifact_files","build_artifact_zip",
]

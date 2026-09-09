"""Public Phase 1 API for the MediLacra Gravity caregiver baseline.

Implementation is split by responsibility so the questionnaire definition, response capture,
FHIR materialization, quality checks, and storage can evolve independently without creating a
new healthcare ontology.
"""

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


__all__ = [
    "QUESTIONNAIRE_ID",
    "QUESTIONNAIRE_URL",
    "QUESTIONNAIRE_VERSION",
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
]

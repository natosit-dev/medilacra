from __future__ import annotations

import io
import zipfile

from connectathon.gravity_materialize import bundle_resources
from connectathon.gravity_response import answer_absent_reason
from connectathon.gravity_sdoh import build_artifact_files, build_artifact_zip
from connectathon.gravity_sdoh_materialize import observations_by_loinc
from connectathon.gravity_sdoh_quality import sdoh_quality_gate
from connectathon.gravity_sdoh_questionnaire import (
    QUESTIONNAIRE_VERSION, build_questionnaire,
)
from connectathon.gravity_sdoh_response import (
    answers_for, build_questionnaire_response,
)
from connectathon.gravity_sdoh_terminology import (
    HOUSING, HOUSING_WORRY, HVS_Q1, HVS_Q2, HVS_RISK,
    HVS_RISK_AT_RISK, HVS_RISK_NO_RISK, LOINC, MATERIAL_NEEDS,
    OBS_CAT_SYSTEM, SDOH_CAT_SYSTEM, SOCIAL, STRESS, TRANSPORT,
    US_CORE_CAT_SYSTEM,
)
from connectathon.gravity_sdoh_materialize import build_submission_bundle
from connectathon.gravity_storage import load_questionnaire_responses, save_questionnaire_response

PATIENT={
    "patient_id":"PAT-SDOH-001","mrn":"MRN-SDOH-001",
    "patient_name":"PATIENT, SAM","date_of_birth":"1988-04-05","sex":"F",
    "phone":"555-0101","address":"2 Test Way","city":"Lowell","state":"MA","zip":"01852",
}
HAPPY={
    HVS_Q1:"LA28397-0",
    HVS_Q2:"LA28398-8",
    HOUSING:"LA30190-5",
    HOUSING_WORRY:"LA33-6",
    MATERIAL_NEEDS:["LA30125-1","LA30124-4"],
    TRANSPORT:["LA30133-5"],
    SOCIAL:"LA30130-1",
    STRESS:"LA13909-9",
}

def _bundle(raw=HAPPY,declined=None):
    response=build_questionnaire_response(
        PATIENT["patient_id"],raw,declined=set(declined or []),
        response_id="sdoh-test-response",authored="2026-09-25T12:00:00+00:00",
    )
    bundle,cleanup=build_submission_bundle(PATIENT,response)
    return response,bundle,cleanup

def _question_items(questionnaire):
    return {
        item["linkId"]:item
        for group in questionnaire["item"]
        for item in group.get("item",[])
    }

def _category_pairs(observation):
    return {
        (coding.get("system"),coding.get("code"))
        for category in observation.get("category",[])
        for coding in category.get("coding",[])
    }

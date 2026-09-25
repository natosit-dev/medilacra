from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

from connectathon.fhir_control import prepare_control_bundle
from connectathon.gravity_materialize import bundle_resources
from connectathon.gravity_response import answer_absent_reason, build_patient_resource, fhir_id
from connectathon.gravity_sdoh_questionnaire import build_questionnaire
from connectathon.gravity_sdoh_response import answers_for
from connectathon.gravity_sdoh_terminology import (
    AT_RISK_SOURCE_CODES, DOMAIN_DISPLAY, HOUSING, HOUSING_WORRY,
    HVS_Q1, HVS_Q2, HVS_RISK, HVS_RISK_AT_RISK, LOINC,
    MATERIAL_NEEDS, OBS_CAT_SYSTEM, OBS_INT_SYSTEM, SDOH_CAT_SYSTEM,
    SDOH_OSR_PROFILE, SOCIAL, STRESS, TRANSPORT, US_CORE_CAT_SYSTEM,
)

DATA_ABSENT_SYSTEM="http://terminology.hl7.org/CodeSystem/data-absent-reason"

DOMAINS={
    HVS_Q1:["food-insecurity"],
    HVS_Q2:["food-insecurity"],
    HVS_RISK:["food-insecurity"],
    HOUSING:["homelessness","housing-instability"],
    HOUSING_WORRY:["housing-instability"],
    MATERIAL_NEEDS:["material-hardship"],
    TRANSPORT:["transportation-insecurity"],
    SOCIAL:["social-connection"],
    STRESS:["stress"],
}

def _categories(question_code: str) -> list[dict[str,Any]]:
    values=[
        {"coding":[{"system":OBS_CAT_SYSTEM,"code":"survey","display":"Survey"}]},
        {"coding":[{"system":US_CORE_CAT_SYSTEM,"code":"sdoh","display":"SDOH"}]},
    ]
    for code in DOMAINS[question_code]:
        values.append({"coding":[{"system":SDOH_CAT_SYSTEM,"code":code,"display":DOMAIN_DISPLAY[code]}]})
    return values

def _is_positive(question_code: str, answer_code: str) -> bool:
    if question_code in {HVS_Q1,HVS_Q2}:
        return answer_code in AT_RISK_SOURCE_CODES
    return question_code==HVS_RISK and answer_code==HVS_RISK_AT_RISK

def _observation_base(
    question_code: str, text: str, patient_ref: str, authored: str,
    qr_id: str, observation_id: str,
) -> dict[str,Any]:
    return {
        "resourceType":"Observation",
        "id":fhir_id(observation_id,prefix="obs"),
        "meta":{"profile":[SDOH_OSR_PROFILE]},
        "status":"final",
        "category":_categories(question_code),
        "code":{"coding":[{"system":LOINC,"code":question_code,"display":text}],"text":text},
        "subject":{"reference":patient_ref},
        "effectiveDateTime":authored,
        "derivedFrom":[{"reference":f"QuestionnaireResponse/{qr_id}"}],
    }

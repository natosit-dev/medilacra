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

def extract_sdoh_resources(questionnaire_response: Mapping[str,Any]) -> list[dict[str,Any]]:
    qr_id=str(questionnaire_response.get("id") or "")
    patient_ref=str((questionnaire_response.get("subject") or {}).get("reference") or "")
    authored=str(questionnaire_response.get("authored") or datetime.now(timezone.utc).isoformat(timespec="seconds"))
    resources=[]
    for question_code in DOMAINS:
        items=[item for _path,item in __import__("connectathon.gravity_response",fromlist=["iter_response_items"]).iter_response_items(list(questionnaire_response.get("item") or [])) if item.get("linkId")==question_code]
        if not items:
            continue
        text=str(items[0].get("text") or question_code)
        answers=answers_for(questionnaire_response,question_code)
        for index,answer in enumerate(answers,start=1):
            suffix=f"-{index}" if len(answers)>1 else ""
            obs=_observation_base(
                question_code,text,patient_ref,authored,qr_id,
                f"{qr_id}-{question_code}{suffix}",
            )
            reason=answer_absent_reason(answer)
            if reason:
                obs["dataAbsentReason"]={
                    "coding":[{"system":DATA_ABSENT_SYSTEM,"code":reason,"display":reason.replace("-"," ").title()}]
                }
                resources.append(obs)
                continue
            coding=answer.get("valueCoding")
            if not isinstance(coding,Mapping) or not coding.get("code"):
                continue
            obs["valueCodeableConcept"]={"coding":[dict(coding)],"text":coding.get("display")}
            if _is_positive(question_code,str(coding["code"])):
                obs["interpretation"]=[{
                    "coding":[{"system":OBS_INT_SYSTEM,"code":"POS","display":"Positive"}]
                }]
            resources.append(obs)
    return resources

def build_submission_bundle(
    patient: Any,
    questionnaire_response: Mapping[str,Any],
    *,
    questionnaire: Mapping[str,Any] | None=None,
) -> tuple[dict[str,Any],dict[str,Any]]:
    patient_resource=(
        dict(patient)
        if isinstance(patient,Mapping) and patient.get("resourceType")=="Patient"
        else build_patient_resource(patient)
    )
    qr=dict(questionnaire_response)
    resources=[patient_resource,dict(questionnaire or build_questionnaire()),qr,*extract_sdoh_resources(qr)]
    raw={
        "resourceType":"Bundle",
        "id":fhir_id(f"sdoh-bundle-{qr.get('id')}",prefix="bundle"),
        "type":"collection",
        "entry":[{"resource":resource} for resource in resources],
    }
    return prepare_control_bundle(raw)

def observations_by_loinc(bundle: Mapping[str,Any], code: str) -> list[Mapping[str,Any]]:
    found=[]
    for obs in bundle_resources(bundle,"Observation"):
        codings=((obs.get("code") or {}).get("coding") or [])
        if any(isinstance(c,Mapping) and c.get("system")==LOINC and c.get("code")==code for c in codings):
            found.append(obs)
    return found

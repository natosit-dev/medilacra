from __future__ import annotations

from typing import Any, Sequence

from connectathon.gravity_sdoh_terminology import (
    ALL_CODES, HOUSING, HOUSING_OPTIONS, HOUSING_TEXT, HOUSING_WORRY,
    HOUSING_WORRY_TEXT, HVS_OPTIONS, HVS_Q1, HVS_Q1_TEXT, HVS_Q2,
    HVS_Q2_TEXT, HVS_RISK, HVS_RISK_OPTIONS, LOINC, MATERIAL_NEEDS,
    MATERIAL_OPTIONS, MATERIAL_TEXT, REPEATING_CODES, SOCIAL, SOCIAL_OPTIONS,
    SOCIAL_TEXT, STRESS, STRESS_OPTIONS, STRESS_TEXT, TRANSPORT,
    TRANSPORT_OPTIONS, TRANSPORT_TEXT, YES_NO_DECLINE,
)

QUESTIONNAIRE_ID="medilacra-sdoh-baseline"
QUESTIONNAIRE_VERSION="0.1"
QUESTIONNAIRE_URL="https://medilacra.dev/fhir/Questionnaire/sdoh-baseline"
HVS_SOURCE="http://hl7.org/fhir/us/sdoh-clinicalcare/Questionnaire/SDOHCC-QuestionnaireHungerVitalSign"
PRAPARE_SOURCE="http://hl7.org/fhir/us/sdoh-clinicalcare/Questionnaire/SDOHCC-QuestionnairePRAPARE"

SPECS={
    HVS_Q1:(HVS_Q1_TEXT,HVS_OPTIONS),
    HVS_Q2:(HVS_Q2_TEXT,HVS_OPTIONS),
    HVS_RISK:("Food insecurity risk",HVS_RISK_OPTIONS),
    HOUSING:(HOUSING_TEXT,HOUSING_OPTIONS),
    HOUSING_WORRY:(HOUSING_WORRY_TEXT,YES_NO_DECLINE),
    MATERIAL_NEEDS:(MATERIAL_TEXT,MATERIAL_OPTIONS),
    TRANSPORT:(TRANSPORT_TEXT,TRANSPORT_OPTIONS),
    SOCIAL:(SOCIAL_TEXT,SOCIAL_OPTIONS),
    STRESS:(STRESS_TEXT,STRESS_OPTIONS),
}

def coding(code: str, display: str) -> dict[str,str]:
    return {"system":LOINC,"code":code,"display":display}

def answer_options(options: Sequence[tuple[str,str]]) -> list[dict[str,Any]]:
    return [{"valueCoding":coding(code,display)} for code,display in options]

def question(code: str, *, read_only: bool=False) -> dict[str,Any]:
    text, options=SPECS[code]
    item={
        "linkId":code,
        "text":text,
        "type":"choice",
        "required":False,
        "repeats":code in REPEATING_CODES,
        "code":[coding(code,text)],
        "answerOption":answer_options(options),
    }
    if read_only:
        item["readOnly"]=True
    return item

def group(link_id: str, text: str, codes: Sequence[str]) -> dict[str,Any]:
    return {
        "linkId":link_id,
        "text":text,
        "type":"group",
        "required":False,
        "repeats":False,
        "item":[question(code,read_only=(code==HVS_RISK)) for code in codes],
    }

def build_questionnaire() -> dict[str,Any]:
    return {
        "resourceType":"Questionnaire",
        "id":QUESTIONNAIRE_ID,
        "url":QUESTIONNAIRE_URL,
        "version":QUESTIONNAIRE_VERSION,
        "name":"MediLacraSDOHBaseline",
        "title":"MediLacra SDOH Baseline",
        "status":"active",
        "experimental":True,
        "date":"2026-09-25",
        "publisher":"MediLacra",
        "description":"MediLacra-owned baseline composed from Hunger Vital Sign and selected PRAPARE questions for semantic-preservation testing.",
        "subjectType":["Patient"],
        "derivedFrom":[HVS_SOURCE,PRAPARE_SOURCE],
        "item":[
            group("hvs","Hunger Vital Sign",[HVS_Q1,HVS_Q2,HVS_RISK]),
            group("housing","Housing",[HOUSING,HOUSING_WORRY]),
            group("resources","Money and resources",[MATERIAL_NEEDS,TRANSPORT]),
            group("social-emotional","Social and emotional health",[SOCIAL,STRESS]),
        ],
    }

def allowed_codes(code: str) -> set[str]:
    return {value for value,_display in SPECS[code][1]}

def display_for(code: str, answer_code: str) -> str | None:
    return next((display for value,display in SPECS[code][1] if value==answer_code),None)

assert set(SPECS)==set(ALL_CODES)

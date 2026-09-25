from __future__ import annotations

from typing import Any, Mapping

from connectathon.preflight import preflight_bundle
from connectathon.gravity_materialize import bundle_resources
from connectathon.gravity_response import answer_absent_reason
from connectathon.gravity_sdoh_materialize import DOMAINS, observations_by_loinc
from connectathon.gravity_sdoh_questionnaire import (
    QUESTIONNAIRE_URL, QUESTIONNAIRE_VERSION, allowed_codes,
)
from connectathon.gravity_sdoh_response import answers_for
from connectathon.gravity_sdoh_terminology import (
    AT_RISK_SOURCE_CODES, HVS_NEVER_CODE, HVS_Q1, HVS_Q2, HVS_RISK,
    HVS_RISK_AT_RISK, HVS_RISK_NO_RISK, INPUT_CODES, LOINC,
    OBS_CAT_SYSTEM, OBS_INT_SYSTEM, SDOH_CAT_SYSTEM, US_CORE_CAT_SYSTEM,
)

def _coding(answer: Mapping[str,Any]) -> Mapping[str,Any] | None:
    value=answer.get("valueCoding")
    return value if isinstance(value,Mapping) else None

def _code(answer: Mapping[str,Any] | None) -> str | None:
    coding=_coding(answer) if isinstance(answer,Mapping) else None
    return str(coding.get("code")) if coding and coding.get("code") else None

def _category_codes(obs: Mapping[str,Any]) -> set[tuple[str,str]]:
    out=set()
    for category in obs.get("category",[]) or []:
        for coding in (category.get("coding") or []) if isinstance(category,Mapping) else []:
            if isinstance(coding,Mapping) and coding.get("system") and coding.get("code"):
                out.add((str(coding["system"]),str(coding["code"])))
    return out

def _risk_from_response(response: Mapping[str,Any]) -> str | None:
    source=[]
    for q in (HVS_Q1,HVS_Q2):
        answers=answers_for(response,q)
        source.append(_code(answers[0]) if len(answers)==1 else None)
    if any(code in AT_RISK_SOURCE_CODES for code in source if code):
        return HVS_RISK_AT_RISK
    if source==[HVS_NEVER_CODE,HVS_NEVER_CODE]:
        return HVS_RISK_NO_RISK
    return None

def sdoh_quality_gate(bundle: Mapping[str,Any]) -> dict[str,Any]:
    checks=[]
    def record(name: str, status: str, detail: str) -> None:
        checks.append({"check":name,"status":status,"detail":detail})

    structural=preflight_bundle(dict(bundle))
    record("bundle.preflight","PASS" if structural.get("status")=="PASS" else "FAIL",str(structural.get("claim") or ""))

    patients=bundle_resources(bundle,"Patient")
    questionnaires=bundle_resources(bundle,"Questionnaire")
    responses=bundle_resources(bundle,"QuestionnaireResponse")
    record("patient.exists","PASS" if len(patients)==1 else "FAIL",f"patients={len(patients)}")
    record("questionnaire.exists","PASS" if len(questionnaires)==1 else "FAIL",f"questionnaires={len(questionnaires)}")
    record("questionnaire_response.exists","PASS" if len(responses)==1 else "FAIL",f"responses={len(responses)}")
    if not responses:
        return {"status":"FAIL","scope":"SDOH_BASELINE","claim":"QuestionnaireResponse missing.","checks":checks,"structural":structural}

    response=responses[0]
    canonical=str(response.get("questionnaire") or "")
    expected=f"{QUESTIONNAIRE_URL}|{QUESTIONNAIRE_VERSION}"
    record("response.questionnaire","PASS" if canonical==expected else "FAIL",f"expected={expected}; actual={canonical}")

    patient_full_urls={
        entry.get("fullUrl") for entry in bundle.get("entry",[]) or []
        if isinstance(entry,Mapping) and isinstance(entry.get("resource"),Mapping)
        and entry["resource"].get("resourceType")=="Patient"
    }
    subject=(response.get("subject") or {}).get("reference")
    record("response.subject","PASS" if subject in patient_full_urls else "FAIL",f"subject={subject!r}")

    parse_errors=[]
    for code in INPUT_CODES:
        for answer in answers_for(response,code):
            reason=answer_absent_reason(answer)
            if reason and reason!="asked-declined":
                parse_errors.append(f"{code}:{reason}")
            value=_code(answer)
            if value and value not in allowed_codes(code):
                parse_errors.append(f"{code}:invalid-code:{value}")
    record("response.valid_codes","FAIL" if parse_errors else "PASS","none" if not parse_errors else ", ".join(parse_errors))

    expected_risk=_risk_from_response(response)
    risk_answers=answers_for(response,HVS_RISK)
    actual_risk=_code(risk_answers[0]) if len(risk_answers)==1 else None
    record("hvs.derived_risk","PASS" if actual_risk==expected_risk else "FAIL",f"expected={expected_risk}; actual={actual_risk}")

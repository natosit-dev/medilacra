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

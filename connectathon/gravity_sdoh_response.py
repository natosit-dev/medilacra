from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Mapping

from connectathon.gravity_questionnaire import data_absent_reason
from connectathon.gravity_response import (
    answer_absent_reason, build_patient_resource, fhir_id,
    find_response_items, first_answer, iter_response_items,
)
from connectathon.gravity_sdoh_questionnaire import (
    QUESTIONNAIRE_URL, QUESTIONNAIRE_VERSION, SPECS,
    allowed_codes, display_for,
)
from connectathon.gravity_sdoh_terminology import (
    HVS_AT_RISK_CODES, HVS_NEVER_CODE, HVS_Q1, HVS_Q2, HVS_RISK,
    HVS_RISK_AT_RISK, HVS_RISK_NO_RISK, HOUSING, HOUSING_WORRY,
    LOINC, MATERIAL_NEEDS, REPEATING_CODES, SOCIAL, STRESS, TRANSPORT,
)

SDC_QR_PROFILE="http://hl7.org/fhir/uv/sdc/StructureDefinition/sdc-questionnaireresponse"

def _absent(reason: str) -> dict[str,Any]:
    return {"extension":[data_absent_reason(reason)]}

def _coded_answer(question_code: str, code: str) -> dict[str,Any]:
    display=display_for(question_code,code)
    if not display:
        return _absent("error")
    return {"valueCoding":{"system":LOINC,"code":code,"display":display}}

def _raw_codes(raw: Any, repeats: bool) -> list[str]:
    if raw is None or raw=="":
        return []
    values=list(raw) if isinstance(raw,(list,tuple,set)) else [raw]
    codes=[str(value).strip() for value in values if str(value).strip()]
    if not repeats and len(codes)>1:
        return ["__error__"]
    return codes

def response_item(question_code: str, raw: Any, declined: bool=False) -> dict[str,Any]:
    text=SPECS[question_code][0]
    item={"linkId":question_code,"text":text}
    if declined:
        item["answer"]=[_absent("asked-declined")]
        return item
    codes=_raw_codes(raw,question_code in REPEATING_CODES)
    if not codes:
        return item
    if any(code not in allowed_codes(question_code) for code in codes):
        item["answer"]=[_absent("error")]
        return item
    item["answer"]=[_coded_answer(question_code,code) for code in codes]
    return item

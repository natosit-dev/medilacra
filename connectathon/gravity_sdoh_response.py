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

def derive_hvs_risk(raw_input: Mapping[str,Any], declined: set[str] | None=None) -> str | None:
    declined=declined or set()
    if HVS_Q1 in declined or HVS_Q2 in declined:
        source=[]
    else:
        source=[]
    for question_code in (HVS_Q1,HVS_Q2):
        if question_code in declined:
            continue
        codes=_raw_codes(raw_input.get(question_code),False)
        if len(codes)==1 and codes[0] in allowed_codes(question_code):
            source.append(codes[0])
        else:
            source.append(None)
    if any(code in HVS_AT_RISK_CODES for code in source if code):
        return HVS_RISK_AT_RISK
    if source==[HVS_NEVER_CODE,HVS_NEVER_CODE]:
        return HVS_RISK_NO_RISK
    return None

def _group(link_id: str, text: str, items: list[dict[str,Any]]) -> dict[str,Any]:
    return {"linkId":link_id,"text":text,"item":items}

def build_questionnaire_response(
    patient_id: str,
    raw_input: Mapping[str,Any],
    *,
    declined: set[str] | None=None,
    authored: str | None=None,
    response_id: str | None=None,
) -> dict[str,Any]:
    declined=declined or set()
    authored=authored or datetime.now(timezone.utc).isoformat(timespec="seconds")
    qr_id=fhir_id(response_id or f"sdoh-qr-{uuid.uuid4().hex}",prefix="qr")
    risk=derive_hvs_risk(raw_input,declined)
    risk_item=response_item(HVS_RISK,risk,False) if risk else {"linkId":HVS_RISK,"text":SPECS[HVS_RISK][0]}
    return {
        "resourceType":"QuestionnaireResponse",
        "id":qr_id,
        "meta":{"profile":[SDC_QR_PROFILE]},
        "questionnaire":f"{QUESTIONNAIRE_URL}|{QUESTIONNAIRE_VERSION}",
        "status":"completed",
        "subject":{"reference":f"Patient/{fhir_id(patient_id,prefix='patient')}"},
        "authored":authored,
        "item":[
            _group("hvs","Hunger Vital Sign",[
                response_item(HVS_Q1,raw_input.get(HVS_Q1),HVS_Q1 in declined),
                response_item(HVS_Q2,raw_input.get(HVS_Q2),HVS_Q2 in declined),
                risk_item,
            ]),
            _group("housing","Housing",[
                response_item(HOUSING,raw_input.get(HOUSING),HOUSING in declined),
                response_item(HOUSING_WORRY,raw_input.get(HOUSING_WORRY),HOUSING_WORRY in declined),
            ]),
            _group("resources","Money and resources",[
                response_item(MATERIAL_NEEDS,raw_input.get(MATERIAL_NEEDS),MATERIAL_NEEDS in declined),
                response_item(TRANSPORT,raw_input.get(TRANSPORT),TRANSPORT in declined),
            ]),
            _group("social-emotional","Social and emotional health",[
                response_item(SOCIAL,raw_input.get(SOCIAL),SOCIAL in declined),
                response_item(STRESS,raw_input.get(STRESS),STRESS in declined),
            ]),
        ],
    }

def answers_for(resource: Mapping[str,Any], link_id: str) -> list[Mapping[str,Any]]:
    items=find_response_items(resource,link_id)
    if not items:
        return []
    return [answer for answer in (items[0].get("answer") or []) if isinstance(answer,Mapping)]

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

    for code in (*INPUT_CODES,HVS_RISK):
        answers=answers_for(response,code)
        observations=observations_by_loinc(bundle,code)
        if not answers:
            record(f"{code}.materialization","PASS" if not observations else "FAIL",f"answers=0; observations={len(observations)}")
            continue
        record(f"{code}.cardinality","PASS" if len(observations)==len(answers) else "FAIL",f"answers={len(answers)}; observations={len(observations)}")

        expected_values=[]
        expected_absent=[]
        for answer in answers:
            reason=answer_absent_reason(answer)
            if reason:
                expected_absent.append(reason)
            else:
                expected_values.append(_code(answer))
        actual_values=[]
        actual_absent=[]
        categories_ok=True
        no_neg=True
        for obs in observations:
            value=(obs.get("valueCodeableConcept") or {}).get("coding") or []
            actual_values.extend(str(c["code"]) for c in value if isinstance(c,Mapping) and c.get("system")==LOINC and c.get("code"))
            dar=(obs.get("dataAbsentReason") or {}).get("coding") or []
            actual_absent.extend(str(c["code"]) for c in dar if isinstance(c,Mapping) and c.get("code"))
            cats=_category_codes(obs)
            required={(OBS_CAT_SYSTEM,"survey"),(US_CORE_CAT_SYSTEM,"sdoh")}
            required.update((SDOH_CAT_SYSTEM,domain) for domain in DOMAINS[code])
            categories_ok=categories_ok and required.issubset(cats)
            for interpretation in obs.get("interpretation",[]) or []:
                for coding in (interpretation.get("coding") or []) if isinstance(interpretation,Mapping) else []:
                    if isinstance(coding,Mapping) and coding.get("system")==OBS_INT_SYSTEM and coding.get("code")=="NEG":
                        no_neg=False

        preserved=sorted(v for v in expected_values if v)==sorted(actual_values) and sorted(expected_absent)==sorted(actual_absent)
        record(f"{code}.semantic_survival","PASS" if preserved else "FAIL",f"response={expected_values or expected_absent}; observations={actual_values or actual_absent}")
        record(f"{code}.categories","PASS" if categories_ok else "FAIL",f"domains={DOMAINS[code]}")
        record(f"{code}.no_negative_interpretation","PASS" if no_neg else "FAIL","NEG is not emitted by this baseline")

    failed=[check for check in checks if check["status"]=="FAIL"]
    return {
        "status":"FAIL" if failed else "PASS",
        "scope":"SDOH_BASELINE",
        "claim":"SDOH baseline preserved across QuestionnaireResponse and screening Observations." if not failed else f"{len(failed)} SDOH baseline checks failed.",
        "checks":checks,
        "structural":structural,
    }

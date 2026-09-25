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

def test_questionnaire_freezes_hvs_and_prapare_basics():
    q=build_questionnaire()
    items=_question_items(q)
    assert q["resourceType"]=="Questionnaire"
    assert q["version"]==QUESTIONNAIRE_VERSION
    assert set(items)=={HVS_Q1,HVS_Q2,HVS_RISK,HOUSING,HOUSING_WORRY,MATERIAL_NEEDS,TRANSPORT,SOCIAL,STRESS}
    assert items[HVS_RISK]["readOnly"] is True
    assert items[MATERIAL_NEEDS]["repeats"] is True
    assert items[TRANSPORT]["repeats"] is True
    assert items[HVS_Q1]["code"][0]["system"]==LOINC

def test_hvs_risk_is_computed_not_human_entered():
    response,_,_=_bundle()
    risk=answers_for(response,HVS_RISK)
    assert risk[0]["valueCoding"]["code"]==HVS_RISK_AT_RISK

    no_risk=dict(HAPPY)
    no_risk[HVS_Q1]="LA28398-8"
    no_risk[HVS_Q2]="LA28398-8"
    response,_,_=_bundle(no_risk)
    assert answers_for(response,HVS_RISK)[0]["valueCoding"]["code"]==HVS_RISK_NO_RISK

    incomplete=dict(no_risk)
    incomplete[HVS_Q2]=None
    response,_,_=_bundle(incomplete)
    assert answers_for(response,HVS_RISK)==[]

def test_coded_refusal_is_distinct_from_explicit_decline():
    raw=dict(HAPPY)
    raw[HVS_Q1]="LA15775-2"
    response,_,_=_bundle(raw)
    answer=answers_for(response,HVS_Q1)[0]
    assert answer["valueCoding"]["code"]=="LA15775-2"
    assert answer_absent_reason(answer) is None

    raw[HVS_Q1]=None
    response,_,_=_bundle(raw,declined={HVS_Q1})
    answer=answers_for(response,HVS_Q1)[0]
    assert answer_absent_reason(answer)=="asked-declined"
    assert "valueCoding" not in answer

def test_multiselect_answers_survive_as_separate_observations():
    response,bundle,_=_bundle()
    assert [a["valueCoding"]["code"] for a in answers_for(response,MATERIAL_NEEDS)]==["LA30125-1","LA30124-4"]
    observations=observations_by_loinc(bundle,MATERIAL_NEEDS)
    assert len(observations)==2
    values=[
        obs["valueCodeableConcept"]["coding"][0]["code"]
        for obs in observations
    ]
    assert values==["LA30125-1","LA30124-4"]

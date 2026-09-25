from __future__ import annotations

from connectathon.gravity_sdoh_hl7v2 import build_sdoh_oru
from connectathon.gravity_sdoh_response import build_questionnaire_response
from connectathon.gravity_sdoh_terminology import (
    HOUSING, HOUSING_WORRY, HVS_Q1, HVS_Q2, MATERIAL_NEEDS,
    SOCIAL, STRESS, TRANSPORT,
)

PATIENT={
    "patient_id":"PAT-SDOH-001","mrn":"MRN-SDOH-001",
    "patient_name":"PATIENT, SAM","date_of_birth":"1988-04-05","sex":"F",
    "phone":"555-0101","address":"2 Test Way","city":"Lowell","state":"MA","zip":"01852",
}
RAW={
    HVS_Q1:"LA28397-0",HVS_Q2:"LA28398-8",
    HOUSING:"LA30190-5",HOUSING_WORRY:"LA33-6",
    MATERIAL_NEEDS:["LA30125-1","LA30124-4"],
    TRANSPORT:["LA30133-5"],SOCIAL:"LA30130-1",STRESS:"LA13909-9",
}

def _response(raw=RAW,declined=None):
    return build_questionnaire_response(
        PATIENT["patient_id"],raw,declined=set(declined or []),
        response_id="sdoh-v2-test",authored="2026-09-25T12:00:00+00:00",
    )

def _segments(message: str, name: str):
    return [
        segment.split("|") for segment in message.strip("\\r").split("\\r")
        if segment.startswith(f"{name}|")
    ]

def test_sdoh_oru_does_not_invent_encounter_order_or_referral_segments():
    message=build_sdoh_oru(PATIENT,_response(),control_id="SDOH-TEST")
    names=[segment.split("|",1)[0] for segment in message.strip("\\r").split("\\r")]
    assert names[:3]==["MSH","PID","OBR"]
    assert "PV1" not in names
    assert "ORC" not in names
    assert "RXE" not in names
    msh=_segments(message,"MSH")[0]
    assert msh[8]=="ORU^R01^ORU_R01"
    assert msh[9]=="SDOH-TEST"
    assert msh[11]=="2.5"

def test_sdoh_oru_preserves_coded_multiselect_and_derived_risk():
    obxs=_segments(build_sdoh_oru(PATIENT,_response()),"OBX")
    hvs=next(obx for obx in obxs if obx[3].startswith(f"{HVS_Q1}^"))
    assert hvs[2]=="CWE"
    assert hvs[5]=="LA28397-0^Often true^LN"

    material=[obx for obx in obxs if obx[3].startswith(f"{MATERIAL_NEEDS}^")]
    assert len(material)==2
    assert [obx[4] for obx in material]==["1","2"]
    assert [obx[5].split("^")[0] for obx in material]==["LA30125-1","LA30124-4"]

    risk=next(obx for obx in obxs if obx[3].startswith("88124-3^"))
    assert risk[5]=="LA19952-3^At risk^LN"

def test_sdoh_oru_preserves_decline_as_explicit_absent_reason():
    raw=dict(RAW)
    raw[HOUSING_WORRY]=None
    obxs=_segments(build_sdoh_oru(PATIENT,_response(raw,declined={HOUSING_WORRY})),"OBX")
    direct=[obx for obx in obxs if obx[3].startswith(f"{HOUSING_WORRY}^")]
    absent=[obx for obx in obxs if obx[3].startswith(f"{HOUSING_WORRY}-data-absent-reason^")]
    assert direct==[]
    assert len(absent)==1
    assert absent[0][5]=="asked-declined^Asked but declined^99MEDILACRA"

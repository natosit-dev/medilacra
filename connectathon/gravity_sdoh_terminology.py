from __future__ import annotations

LOINC = "http://loinc.org"
SDOH_CAT_SYSTEM = "http://hl7.org/fhir/us/sdoh-clinicalcare/CodeSystem/SDOHCC-CodeSystemTemporaryCodes"
US_CORE_CAT_SYSTEM = "http://hl7.org/fhir/us/core/CodeSystem/us-core-category"
OBS_CAT_SYSTEM = "http://terminology.hl7.org/CodeSystem/observation-category"
OBS_INT_SYSTEM = "http://terminology.hl7.org/CodeSystem/v3-ObservationInterpretation"
SDOH_OSR_PROFILE = "http://hl7.org/fhir/us/sdoh-clinicalcare/StructureDefinition/SDOHCC-ObservationScreeningResponse"

HVS_Q1="88122-7"
HVS_Q2="88123-5"
HVS_RISK="88124-3"
HOUSING="71802-3"
HOUSING_WORRY="93033-9"
MATERIAL_NEEDS="93031-3"
TRANSPORT="93030-5"
SOCIAL="93029-7"
STRESS="93038-8"

HVS_OPTIONS=[
    ("LA28397-0","Often true"),
    ("LA6729-3","Sometimes true"),
    ("LA28398-8","Never true"),
    ("LA15775-2","Don't know/refused"),
]
HVS_RISK_OPTIONS=[("LA19952-3","At risk"),("LA19983-8","No risk")]
AT_RISK_SOURCE_CODES={"LA28397-0","LA6729-3"}
NEVER_CODE="LA28398-8"

HOUSING_OPTIONS=[
    ("LA30189-7","I have housing"),
    ("LA30190-5","I do not have housing (staying with others, in a hotel, in a shelter, living outside on the street, on a beach, in a car, or in a park)"),
    ("LA30122-8","I choose not to answer this question"),
]
YES_NO_DECLINE=[
    ("LA33-6","Yes"),
    ("LA32-8","No"),
    ("LA30122-8","I choose not to answer this question"),
]
MATERIAL_OPTIONS=[
    ("LA30125-1","Food"),
    ("LA30126-9","Clothing"),
    ("LA30124-4","Utilities"),
    ("LA30127-7","Child care"),
    ("LA30128-5","Medicine or Any Health Care (Medical, Dental, Mental Health, Vision)"),
    ("LA30129-3","Phone"),
    ("LA46-8","Other"),
    ("LA30122-8","I choose not to answer this question"),
]

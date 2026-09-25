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

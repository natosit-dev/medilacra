# demo_oru.py
from pathlib import Path
from schemas.xml_to_registry import load_iris_schema
from templating.jinja_setup import build_env, render
from hl7.hl7_validate import validate_message

# 1) Load schema registry from IRIS XML
XML_PATH = "schemas/HL7v25_from_IRIS.xml"  # <-- your exported file
registry = load_iris_schema(XML_PATH, version_hint="2.5")

# 2) Build Jinja env (your template folder)
env = build_env("templates/v25")

# 3) Prepare synthetic payload (minimal)
patient = {
    "mrn": "P0001",
    "id": "PAT-1",
    "first": "Ada",
    "last": "Lovelace",
    "dob": "18151210",
    "sex": "F",
}
encounter = {
    "event_ts": "20250101103000",
    "control_id": "CTRL-123",
    "cls": "O",
    "location": "RAD^01^ROOM",
    "visit_number": "V123",
    "placer": "PL123",
    "filler": "FIL456",
    "ordering_provider_id": "99999",
    "ordering_provider_name": "Curie^Marie",
    "collection_ts": "20250101102000",
    "result_provider_id": "88888",
    "result_provider_name": "Hopper^Grace",
}
panel = {"code": "24323-8", "text": "Basic Metabolic Panel"}
observations = [
    {"datatype": "NM", "code": "2951-2", "text": "Sodium", "value": "140", "units": "mmol/L", "status": "F", "datetime": "20250101102500"},
    {"datatype": "NM", "code": "17861-6", "text": "Calcium", "value": "9.4", "units": "mg/dL", "status": "F", "datetime": "20250101102500"},
]
payload = {"patient": patient, "encounter": encounter, "panel": panel, "observations": observations}

# Optional flavor overrides (e.g., force OBX-13=R)
flavor = {"msh3": "MEDILACRA", "msh4": "SYNTH", "msh5": "DEST", "msh6": "DESTFAC", "obx13": "R"}

# 4) Render
hl7_text = render(env, "ORU_R01.hl7.j2", payload, flavor=flavor)
print(hl7_text)

# 5) Validate against registry
issues = validate_message(hl7_text, registry)
for iss in issues:
    print(f"{iss.level} {iss.segment}-{iss.field_pos}: {iss.message}")

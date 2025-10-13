
import json
from uuid import uuid4
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple

def _norm(s: str) -> str:
    return s.replace("\r\n", "\n").replace("\r", "\n")

def split_segments(hl7: str) -> List[str]:
    lines = [ln for ln in _norm(hl7).split("\n") if ln.strip()]
    return lines

def parse_segment(line: str) -> tuple[str, list[str]]:
    parts = line.split("|")
    seg = parts[0].strip()
    fields = parts[1:]
    return seg, fields

def get_field(fields: List[str], idx_1_based: int) -> str:
    if idx_1_based - 1 < 0 or idx_1_based - 1 >= len(fields):
        return ""
    return fields[idx_1_based - 1]

def comp(field: str, i: int) -> str:
    comps = field.split("^") if field else []
    return comps[i-1] if 0 <= i-1 < len(comps) else ""

def reps(field: str) -> List[str]:
    return field.split("~") if field else []

def split_messages(hl7_text: str) -> List[str]:
    lines = split_segments(hl7_text)
    starts = [i for i, ln in enumerate(lines) if ln.startswith("MSH|")]
    messages = []
    for idx, start in enumerate(starts):
        end = starts[idx + 1] if idx + 1 < len(starts) else len(lines)
        block = "\n".join(lines[start:end]).strip()
        if block:
            messages.append(block)
    return messages

def parse_hl7(hl7_text: str) -> Dict[str, Any]:
    segments = split_segments(hl7_text)
    out: Dict[str, Any] = {"MSH": [], "PID": [], "PV1": [], "OBR": [], "OBX": [], "FT1": []}
    ordered = []
    for line in segments:
        seg, fields = parse_segment(line)
        ordered.append((seg, fields))
        entry = {"_fields": fields}
        if seg in out:
            out[seg].append(entry)
        else:
            out[seg] = out.get(seg, []) + [entry]
    out["_order"] = ordered
    return out

def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid4()}"

def to_gender(sex: str) -> str:
    sx = (sex or "").strip().upper()
    return {"M":"male","F":"female","O":"other","U":"unknown"}.get(sx, "unknown")

def to_iso_date(d: str):
    if not d:
        return None
    d = d.strip()
    if len(d) == 8 and d.isdigit():
        return f"{d[0:4]}-{d[4:6]}-{d[6:8]}"
    try:
        from datetime import datetime as _dt
        return _dt.fromisoformat(d).date().isoformat()
    except Exception:
        return None

def codeable_concept_from_ce(ce_field: str) -> Dict[str, Any]:
    code = comp(ce_field, 1)
    text = comp(ce_field, 2)
    system = comp(ce_field, 3)
    coding = []
    if code:
        coding.append({
            "system": "http://loinc.org" if (system and system.upper() in ["LN", "LOINC"]) else f"urn:hl7v2:{system}" if system else "urn:hl7v2",
            "code": code,
            "display": text or None
        })
    cc = {"coding": coding} if coding else {}
    if text and not coding:
        cc["text"] = text
    return cc

def build_message_header(msh_fields: List[str]) -> Dict[str, Any]:
    ev = get_field(msh_fields, 9)
    ev_code = comp(ev, 1)
    ev_trigger = comp(ev, 2)
    sending_app = get_field(msh_fields, 3)
    sending_fac = get_field(msh_fields, 4)
    receiving_app = get_field(msh_fields, 5)
    receiving_fac = get_field(msh_fields, 6)
    return {
        "resourceType": "MessageHeader",
        "id": new_id("msg"),
        "eventCoding": {
            "system": "http://terminology.hl7.org/CodeSystem/v2-0003",
            "code": f"{ev_code}^{ev_trigger}" if ev_trigger else ev_code
        },
        "source": {"name": f"{sending_app}|{sending_fac}".strip("|") or "Unknown"},
        "destination": [{"name": f"{receiving_app}|{receiving_fac}".strip("|") or "Unknown"}],
        "timestamp": __import__("datetime").datetime.utcnow().isoformat(timespec="seconds") + "Z"
    }

def build_patient_from_pid(pid_fields: List[str]) -> Dict[str, Any]:
    pid3 = get_field(pid_fields, 3)
    identifiers = []
    for rep in reps(pid3):
        id_val = comp(rep, 1)
        id_assigner = comp(rep, 4)
        if id_val:
            identifiers.append({
                "system": f"urn:oid:{id_assigner}" if id_assigner else "urn:mrn",
                "value": id_val
            })
    name = get_field(pid_fields, 5)
    family = comp(name, 1)
    given = comp(name, 2)
    dob_raw = get_field(pid_fields, 7)
    birth_date = to_iso_date(dob_raw)
    gender = to_gender(get_field(pid_fields, 8))
    addr = get_field(pid_fields, 11)
    street = comp(addr, 1)
    city = comp(addr, 3)
    state = comp(addr, 4)
    postal = comp(addr, 5)
    patient = {
        "resourceType": "Patient",
        "id": new_id("pat"),
        "identifier": identifiers or None,
        "name": [{"family": family, "given": [given] if given else []}],
        "gender": gender,
        "birthDate": birth_date,
        "address": [{
            "line": [street] if street else [],
            "city": city or None,
            "state": state or None,
            "postalCode": postal or None
        }]
    }
    patient["identifier"] = [i for i in (patient["identifier"] or []) if i.get("value")]
    if not patient["identifier"]:
        patient.pop("identifier", None)
    if not patient["address"][0]["line"] and not patient["address"][0]["city"] and not patient["address"][0]["state"] and not patient["address"][0]["postalCode"]:
        patient.pop("address", None)
    return patient

def build_encounter_from_pv1(pv1_fields: List[str], patient_ref: str) -> Dict[str, Any]:
    cls = get_field(pv1_fields, 2)
    loc = get_field(pv1_fields, 3)
    pof = comp(loc, 1)
    room = comp(loc, 2)
    bed = comp(loc, 3)
    facility = comp(loc, 4)
    encounter = {
        "resourceType": "Encounter",
        "id": new_id("enc"),
        "status": "finished",
        "class": {"code": cls or "UNK"},
        "subject": {"reference": patient_ref},
    }
    extensions = []
    if any([pof, room, bed, facility]):
        extensions.append({
            "url": "http://example.org/fhir/StructureDefinition/hl7v2-location",
            "extension": [
                {"url": "pointOfCare", "valueString": pof},
                {"url": "room", "valueString": room},
                {"url": "bed", "valueString": bed},
                {"url": "facility", "valueString": facility}
            ]
        })
    if extensions:
        encounter["extension"] = extensions
    return encounter

def build_observation_from_obx(obx_fields: List[str], patient_ref: str, encounter_ref: Optional[str]) -> Dict[str, Any]:
    vtype = get_field(obx_fields, 2).upper()
    id_ce = get_field(obx_fields, 3)
    val = get_field(obx_fields, 5)
    units = get_field(obx_fields, 6)
    dt_obs = get_field(obx_fields, 14)
    obs = {
        "resourceType": "Observation",
        "id": new_id("obs"),
        "status": "final",
        "code": codeable_concept_from_ce(id_ce) or {"text": "Observation"},
        "subject": {"reference": patient_ref},
    }
    if encounter_ref:
        obs["encounter"] = {"reference": encounter_ref}
    if dt_obs:
        try:
            ts = dt_obs[:14]
            iso = f"{ts[0:4]}-{ts[4:6]}-{ts[6:8]}T{ts[8:10]}:{ts[10:12]}:{ts[12:14]}"
            obs["effectiveDateTime"] = iso
        except Exception:
            pass
    if vtype in ("TX", "ST"):
        obs["valueString"] = val
    elif vtype == "NM":
        try:
            obs["valueQuantity"] = {"value": float(val)}
            if units:
                obs["valueQuantity"]["unit"] = comp(units, 2) or comp(units, 1)
        except Exception:
            obs["valueString"] = val
    elif vtype == "CE":
        obs["valueCodeableConcept"] = codeable_concept_from_ce(val)
    elif vtype in ("DT", "TS"):
        try:
            d = val[:8]
            iso = f"{d[0:4]}-{d[4:6]}-{d[6:8]}"
            obs["valueDateTime"] = iso
        except Exception:
            obs["valueString"] = val
    else:
        obs["valueString"] = val
    return obs

def build_diagnostic_report_from_obr(obr_fields: List[str], patient_ref: str, encounter_ref: Optional[str], observations_refs: List[str]) -> Dict[str, Any]:
    svc = get_field(obr_fields, 4)
    code = codeable_concept_from_ce(svc)
    dr = {
        "resourceType": "DiagnosticReport",
        "id": new_id("dr"),
        "status": "final",
        "code": code or {"text": "Diagnostic Report"},
        "subject": {"reference": patient_ref},
        "result": [{"reference": r} for r in observations_refs]
    }
    if encounter_ref:
        dr["encounter"] = {"reference": encounter_ref}
    return dr

def build_account_from_ft1(ft1_fields: List[str], patient_ref: str, encounter_ref: Optional[str]) -> Dict[str, Any]:
    dt = get_field(ft1_fields, 4)
    code = get_field(ft1_fields, 6)
    desc = get_field(ft1_fields, 7)
    amt = get_field(ft1_fields, 10)
    claim = {
        "resourceType": "Claim",
        "id": new_id("claim"),
        "status": "active",
        "type": {"text": "professional"},
        "patient": {"reference": patient_ref},
        "billablePeriod": {},
        "item": []
    }
    if encounter_ref:
        claim["encounter"] = [{"reference": encounter_ref}]
    if dt and len(dt) >= 8:
        d = f"{dt[0:4]}-{dt[4:6]}-{dt[6:8]}"
        claim["billablePeriod"]["start"] = d
        claim["billablePeriod"]["end"] = d
    if code or desc or amt:
        entry = {"sequence": 1, "productOrService": {"text": f"{code} {desc}".strip()}}
        if amt:
            try:
                entry["unitPrice"] = {"value": float(amt)}
            except Exception:
                pass
        claim["item"].append(entry)
    return claim

def detect_message_type(parsed: Dict[str, Any]) -> str:
    if not parsed.get("MSH"):
        return "UNKNOWN"
    ev = get_field(parsed["MSH"][0]["_fields"], 9)
    return f"{comp(ev,1)}^{comp(ev,2)}".upper()

def convert_oru(parsed: Dict[str, Any]) -> Dict[str, Any]:
    msh = parsed["MSH"][0]["_fields"]
    pid = parsed["PID"][0]["_fields"] if parsed.get("PID") else None
    pv1 = parsed["PV1"][0]["_fields"] if parsed.get("PV1") else None
    msg_header = build_message_header(msh)
    patient = build_patient_from_pid(pid) if pid else None
    patient_ref = f"Patient/{patient['id']}" if patient else None
    encounter = build_encounter_from_pv1(pv1, patient_ref) if pv1 and patient else None
    encounter_ref = f"Encounter/{encounter['id']}" if encounter else None
    observations = [build_observation_from_obx(o["_fields"], patient_ref, encounter_ref) for o in parsed.get("OBX", [])]
    obs_refs = [f"Observation/{o['id']}" for o in observations]
    if parsed.get("OBR"):
        dr = build_diagnostic_report_from_obr(parsed["OBR"][0]["_fields"], patient_ref, encounter_ref, obs_refs)
    else:
        dr = {"resourceType":"DiagnosticReport","id":new_id("dr"),"status":"final","code":{"text":"Diagnostic Report"},"subject":{"reference":patient_ref},"result":[{"reference":r} for r in obs_refs]}
        if encounter_ref:
            dr["encounter"] = {"reference": encounter_ref}
    entries = [{"resource": msg_header}]
    if patient: entries.append({"resource": patient})
    if encounter: entries.append({"resource": encounter})
    entries.append({"resource": dr})
    for o in observations:
        entries.append({"resource": o})
    return {"resourceType":"Bundle","type":"message","id":new_id("bundle"),"entry":entries}

def convert_adt(parsed: Dict[str, Any]) -> Dict[str, Any]:
    msh = parsed["MSH"][0]["_fields"]
    pid = parsed["PID"][0]["_fields"] if parsed.get("PID") else None
    pv1 = parsed["PV1"][0]["_fields"] if parsed.get("PV1") else None
    msg_header = build_message_header(msh)
    patient = build_patient_from_pid(pid) if pid else None
    entries = [{"resource": msg_header}]
    if patient: entries.append({"resource": patient})
    if pv1 and patient:
        enc = build_encounter_from_pv1(pv1, f"Patient/{patient['id']}")
        entries.append({"resource": enc})
    return {"resourceType":"Bundle","type":"message","id":new_id("bundle"),"entry":entries}

def convert_dft(parsed: Dict[str, Any]) -> Dict[str, Any]:
    msh = parsed["MSH"][0]["_fields"]
    pid = parsed["PID"][0]["_fields"] if parsed.get("PID") else None
    pv1 = parsed["PV1"][0]["_fields"] if parsed.get("PV1") else None
    msg_header = build_message_header(msh)
    patient = build_patient_from_pid(pid) if pid else None
    patient_ref = f"Patient/{patient['id']}" if patient else None
    encounter = build_encounter_from_pv1(pv1, patient_ref) if pv1 and patient else None
    encounter_ref = f"Encounter/{encounter['id']}" if encounter else None
    claims = [build_account_from_ft1(ft["_fields"], patient_ref, encounter_ref) for ft in parsed.get("FT1", [])]
    entries = [{"resource": msg_header}]
    if patient: entries.append({"resource": patient})
    if encounter: entries.append({"resource": encounter})
    for c in claims:
        entries.append({"resource": c})
    return {"resourceType":"Bundle","type":"message","id":new_id("bundle"),"entry":entries}

def convert_message_to_bundle(hl7_text: str):
    parsed = parse_hl7(hl7_text)
    msg_type = detect_message_type(parsed)
    if msg_type.startswith("ORU^"):
        return convert_oru(parsed), msg_type
    if msg_type.startswith("ADT^"):
        return convert_adt(parsed), msg_type
    if msg_type.startswith("DFT^"):
        return convert_dft(parsed), msg_type
    msh = parsed["MSH"][0]["_fields"]
    mh = build_message_header(msh)
    patient = build_patient_from_pid(parsed["PID"][0]["_fields"]) if parsed.get("PID") else None
    entries = [{"resource": mh}]
    if patient: entries.append({"resource": patient})
    return {"resourceType":"Bundle","type":"message","id":new_id("bundle"),"entry":entries}, msg_type

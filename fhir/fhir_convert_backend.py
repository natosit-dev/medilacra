
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

def get_msh_field(msh_fields: List[str], msh_idx: int) -> str:
    """
    Return true MSH-N from parsed MSH fields.

    MSH-1 is the field separator itself, so after splitting on "|" the first
    stored item is MSH-2. MSH therefore cannot use the generic field accessor.
    """
    adjusted = msh_idx - 2
    if adjusted < 0 or adjusted >= len(msh_fields):
        return ""
    return msh_fields[adjusted]

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
    ev = get_msh_field(msh_fields, 9)
    ev_code = comp(ev, 1)
    ev_trigger = comp(ev, 2)
    sending_app = get_msh_field(msh_fields, 3)
    sending_fac = get_msh_field(msh_fields, 4)
    receiving_app = get_msh_field(msh_fields, 5)
    receiving_fac = get_msh_field(msh_fields, 6)
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

FHIR_RESOURCE_ID_CHARS = set(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-."
)


def _is_fhir_resource_id(value: str) -> bool:
    return bool(value) and len(value) <= 64 and all(
        ch in FHIR_RESOURCE_ID_CHARS for ch in value
    )


def _relationship_codeable_concept(relationship_field: str) -> Optional[Dict[str, Any]]:
    """
    Map the current self-subscriber relationship into FHIR Coverage.relationship.

    Family/dependent relationships are intentionally deferred. Unknown values are
    retained only as display text rather than guessed into a relationship code.
    """
    source_code = comp(relationship_field, 1).strip().upper()
    source_text = comp(relationship_field, 2).strip()

    if source_code in {"SEL", "SELF"}:
        return {
            "coding": [
                {
                    "system": "http://terminology.hl7.org/CodeSystem/subscriber-relationship",
                    "code": "self",
                    "display": "Self",
                }
            ]
        }

    if source_text:
        return {"text": source_text}

    if source_code:
        return {"text": source_code}

    return None


def _distinct_nonempty(values: List[str]) -> List[str]:
    seen = []
    for value in values:
        normalized = (value or "").strip()
        if normalized and normalized not in seen:
            seen.append(normalized)
    return seen


def extract_coverage_context(parsed: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Coalesce GT1 + IN1 + IN2 into one normalized coverage context.

    IN1 is the minimum source requirement for this MVP. IN2 and GT1 provide
    employer identity and corroborating evidence. Deterministic precedence:
      employer id   IN2-3.1 -> GT1-29
      employer name IN2-3.2 -> IN1-11 -> GT1-16
    """
    if not parsed.get("IN1"):
        return None

    in1 = parsed["IN1"][0]["_fields"]
    gt1 = parsed["GT1"][0]["_fields"] if parsed.get("GT1") else None
    in2 = parsed["IN2"][0]["_fields"] if parsed.get("IN2") else None

    in2_employer = get_field(in2, 3) if in2 else ""
    in2_employer_id = comp(in2_employer, 1).strip()
    in2_employer_name = comp(in2_employer, 2).strip()

    gt1_employer_id = get_field(gt1, 29).strip() if gt1 else ""
    gt1_employer_name = get_field(gt1, 16).strip() if gt1 else ""
    in1_employer_name = get_field(in1, 11).strip()

    employer_id = in2_employer_id or gt1_employer_id
    employer_name = (
        in2_employer_name
        or in1_employer_name
        or gt1_employer_name
    )

    employer_ids = _distinct_nonempty([
        in2_employer_id,
        gt1_employer_id,
    ])
    employer_names = _distinct_nonempty([
        in2_employer_name,
        in1_employer_name,
        gt1_employer_name,
    ])

    conflicts = []
    if len(employer_ids) > 1:
        conflicts.append("employer_id")
    if len(employer_names) > 1:
        conflicts.append("employer_name")

    plan = get_field(in1, 2)
    relationship = get_field(in1, 17)

    return {
        "employer_id": employer_id,
        "employer_name": employer_name,
        "payer_id": get_field(in1, 3).strip(),
        "payer_name": get_field(in1, 4).strip(),
        "plan_id": comp(plan, 1).strip(),
        "plan_name": comp(plan, 2).strip(),
        "plan_type": get_field(in1, 15).strip(),
        "group_number": get_field(in1, 8).strip(),
        "member_id": get_field(in1, 49).strip(),
        "effective_start": get_field(in1, 12).strip(),
        "effective_end": get_field(in1, 13).strip(),
        "subscriber_name": get_field(in1, 16).strip(),
        "subscriber_relationship": relationship,
        "patient_is_subscriber": (
            comp(relationship, 1).strip().upper()
            in {"SEL", "SELF"}
        ),
        # Recognized but deliberately not projected in this MVP.
        "gt1_employment_status": (
            get_field(gt1, 20).strip()
            if gt1
            else ""
        ),
        "conflicts": conflicts,
    }


def build_organization(
    source_id: str,
    name: str,
    *,
    role: str,
) -> Optional[Dict[str, Any]]:
    """Build an employer or payer Organization while preserving source identity."""
    source_id = (source_id or "").strip()
    name = (name or "").strip()

    if not source_id and not name:
        return None

    organization: Dict[str, Any] = {
        "resourceType": "Organization",
        "id": new_id("org"),
    }

    if source_id:
        organization["identifier"] = [
            {
                "system": f"urn:medilacra:{role}",
                "value": source_id,
            }
        ]

    if name:
        organization["name"] = name

    return organization


def build_coverage(
    context: Dict[str, Any],
    *,
    patient_ref: str,
    employer_ref: Optional[str],
    payer_ref: str,
) -> Dict[str, Any]:
    """Build one FHIR R4 Coverage from one normalized v2 coverage context."""
    coverage: Dict[str, Any] = {
        "resourceType": "Coverage",
        "id": new_id("cov"),
        "status": "active",
        "beneficiary": {"reference": patient_ref},
        "payor": [{"reference": payer_ref}],
    }

    if context.get("patient_is_subscriber"):
        coverage["subscriber"] = {"reference": patient_ref}

    member_id = context.get("member_id")
    if member_id:
        # Deliberate local mapping decision for the current synthetic model.
        coverage["subscriberId"] = member_id

    relationship = _relationship_codeable_concept(
        context.get("subscriber_relationship", "")
    )
    if relationship:
        coverage["relationship"] = relationship

    if employer_ref:
        coverage["policyHolder"] = {
            "reference": employer_ref
        }

    effective_start = to_iso_date(
        context.get("effective_start", "")
    )
    effective_end = to_iso_date(
        context.get("effective_end", "")
    )
    if effective_start or effective_end:
        coverage["period"] = {}
        if effective_start:
            coverage["period"]["start"] = effective_start
        if effective_end:
            coverage["period"]["end"] = effective_end

    plan_type = context.get("plan_type")
    if plan_type:
        coverage["type"] = {"text": plan_type}

    classes = []

    group_number = context.get("group_number")
    if group_number:
        classes.append(
            {
                "type": {
                    "coding": [
                        {
                            "system": "http://terminology.hl7.org/CodeSystem/coverage-class",
                            "code": "group",
                        }
                    ]
                },
                "value": group_number,
            }
        )

    plan_id = context.get("plan_id")
    plan_name = context.get("plan_name")
    if plan_id:
        plan_class: Dict[str, Any] = {
            "type": {
                "coding": [
                    {
                        "system": "http://terminology.hl7.org/CodeSystem/coverage-class",
                        "code": "plan",
                    }
                ]
            },
            "value": plan_id,
        }
        if plan_name:
            plan_class["name"] = plan_name
        classes.append(plan_class)

    if classes:
        coverage["class"] = classes

    return coverage


def build_coverage_resources(
    parsed: Dict[str, Any],
    patient_ref: Optional[str],
) -> List[Dict[str, Any]]:
    """
    Materialize one coherent coverage graph for ADT/DFT.

    Coverage.payor is required, so no Coverage is emitted without both patient
    context and payer identity. Employer Organization is optional.
    """
    if not patient_ref:
        return []

    context = extract_coverage_context(parsed)
    if not context:
        return []

    if not (
        context.get("payer_id")
        or context.get("payer_name")
    ):
        return []

    employer = build_organization(
        context.get("employer_id", ""),
        context.get("employer_name", ""),
        role="employer",
    )
    payer = build_organization(
        context.get("payer_id", ""),
        context.get("payer_name", ""),
        role="payer",
    )

    if payer is None:
        return []

    employer_ref = (
        f"Organization/{employer['id']}"
        if employer is not None
        else None
    )
    payer_ref = f"Organization/{payer['id']}"

    coverage = build_coverage(
        context,
        patient_ref=patient_ref,
        employer_ref=employer_ref,
        payer_ref=payer_ref,
    )

    resources = []
    if employer is not None:
        resources.append(employer)
    resources.append(payer)
    resources.append(coverage)
    return resources


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
    ev = get_msh_field(parsed["MSH"][0]["_fields"], 9)
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
    patient_ref = f"Patient/{patient['id']}" if patient else None

    entries = [{"resource": msg_header}]
    if patient:
        entries.append({"resource": patient})
    if pv1 and patient_ref:
        enc = build_encounter_from_pv1(
            pv1,
            patient_ref,
        )
        entries.append({"resource": enc})

    for resource in build_coverage_resources(
        parsed,
        patient_ref,
    ):
        entries.append({"resource": resource})

    return {
        "resourceType": "Bundle",
        "type": "message",
        "id": new_id("bundle"),
        "entry": entries,
    }

def convert_dft(parsed: Dict[str, Any]) -> Dict[str, Any]:
    msh = parsed["MSH"][0]["_fields"]
    pid = parsed["PID"][0]["_fields"] if parsed.get("PID") else None
    pv1 = parsed["PV1"][0]["_fields"] if parsed.get("PV1") else None
    msg_header = build_message_header(msh)
    patient = build_patient_from_pid(pid) if pid else None
    patient_ref = f"Patient/{patient['id']}" if patient else None
    encounter = (
        build_encounter_from_pv1(
            pv1,
            patient_ref,
        )
        if pv1 and patient_ref
        else None
    )
    encounter_ref = (
        f"Encounter/{encounter['id']}"
        if encounter
        else None
    )

    claims = [
        build_account_from_ft1(
            ft["_fields"],
            patient_ref,
            encounter_ref,
        )
        for ft in parsed.get("FT1", [])
    ]

    entries = [{"resource": msg_header}]
    if patient:
        entries.append({"resource": patient})
    if encounter:
        entries.append({"resource": encounter})

    for resource in build_coverage_resources(
        parsed,
        patient_ref,
    ):
        entries.append({"resource": resource})

    for claim in claims:
        entries.append({"resource": claim})

    return {
        "resourceType": "Bundle",
        "type": "message",
        "id": new_id("bundle"),
        "entry": entries,
    }

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

import uuid
from datetime import datetime
from typing import List, Optional
from .models import Encounter, Observation, Transaction
from .utils import ts_hl7, hl7_name_from_full, hl7_name_from_display, hl7_escape
import textwrap

def seg_msh(message_type: str) -> str:
    now = datetime.now().strftime("%Y%m%d%H%M%S")
    structures = {"ADT^A01":"ADT_A01","ORU^R01":"ORU_R01","DFT^P03":"DFT_P03"}
    if "^" in message_type and message_type.count("^") == 1:
        message_type = f"{message_type}^{structures.get(message_type, '')}"
    control_id = str(uuid.uuid4())
    return f"MSH|^~\\&|FAKELAB|FAKEFACILITY|CMX|STAGE|{now}||{message_type}|{control_id}|P|2.5|||AL|NE||UNICODE UTF-8"

def seg_evn(enc: Encounter, event_type: str = "A01") -> str:
    evn_ts = ts_hl7(enc.admit_datetime)
    return f"EVN|{event_type}|{evn_ts}||||{evn_ts}"


def seg_pid(p) -> str:
    from .utils import one_line
    street = one_line(p.address)              # street only
    phone = one_line(p.phone)
    # City -> PID-11.3, State -> PID-11.4, Zip -> PID-11.5
    addr_comp = f"{street}^^{p.city}^{p.state}^{p.zip_code}"
    return (
        f"PID|1||{p.patient_id}||{hl7_name_from_display(p.patient_name)}||"
        f"{ts_hl7(p.date_of_birth)}|{p.sex}||{p.race}|{addr_comp}||{phone}||||||{p.ssn}"
    )

def seg_pv1(enc: Encounter) -> str:
    admit = ts_hl7(enc.admit_datetime); disch = ts_hl7(enc.discharge_datetime)
    attending_nm = hl7_name_from_full(enc.attending_provider_name)
    return f"PV1|1|{enc.patient_class}|{enc.assigned_patient_location}||||{enc.attending_provider_id}^{attending_nm}||||||||||||{enc.visit_number}|||||||||||||||||||||||||{admit}|{disch}"

def seg_orc(enc: Encounter) -> str:
    ordering_nm = hl7_name_from_full(enc.ordering_provider_name)
    return f"ORC|RE|{enc.placer_order_number}|{enc.filler_order_number}||CM|||||{enc.ordering_provider_id}^{ordering_nm}"

def seg_obr(enc: Encounter, obs: Optional[Observation]) -> str:
    cpt = obs.cpt_code if obs else ""; desc = obs.procedure_description if obs else ""
    usi = f"{cpt}^{desc}^CPT" if (cpt or desc) else ""
    when = ts_hl7(obs.completed_time if obs else enc.admit_datetime)
    ordering_nm = hl7_name_from_full(enc.ordering_provider_name)
    return f"OBR|1|{enc.placer_order_number}|{enc.filler_order_number}|{usi}|R|||{when}||||||||{enc.ordering_provider_id}^{ordering_nm}"

def seg_obx(obs: Observation) -> str:
    ident = f"{obs.cpt_code}^{obs.procedure_description}^CPT"
    sub_id = obs.observation_sub_id or "1"
    value = obs.observation_text or ""
    status = obs.result_status or "F"
    producer = "FAKEFACILITY^RAD_DEPT1"
    return f"OBX|1|TX|{ident}|{sub_id}|{hl7_escape(value)}||||||{status}|||{producer}"

def seg_obx_lines(obs: Observation, start_set_id: int = 1, wrap_width: int = 200) -> List[str]:
    ident = f"{obs.cpt_code}^{obs.procedure_description}^CPT"
    status = obs.result_status or "F"; producer = "FAKEFACILITY^RAD_DEPT1"
    norm = (obs.observation_text or "").replace("\r\n","\n").replace("\r","\n")
    raw_lines = norm.split("\n")
    lines = []
    for ln in raw_lines:
        ln = (ln or "").strip()
        if not ln: lines.append(""); continue
        if len(ln) > wrap_width:
            lines.extend(textwrap.wrap(ln, width=wrap_width, break_long_words=False, break_on_hyphens=False))
        else:
            lines.append(ln)
    segs = []; set_id = start_set_id; sub_id = 1
    for ln in lines:
        val = hl7_escape(ln)
        segs.append(f"OBX|{set_id}|TX|{ident}|{sub_id}|{val}||||||{status}|||{producer}")
        set_id += 1; sub_id += 1
    return segs

def seg_ft1(tx: Transaction, obs: Optional[Observation]) -> str:
    tx_dt = ts_hl7(tx.transaction_date); post = tx_dt
    cpt = obs.cpt_code if obs else ""; desc = (obs.procedure_description if obs else "CHARGE")
    qty = tx.transaction_quantity; unit = tx.unit_cost; amt = tx.transaction_amount
    plan = tx.insurance_plan_id; fee = tx.fee_schedule; dept = "RAD"; ptype = "OUTPATIENT"
    return f"FT1|1|{tx.transaction_id}| |{tx_dt}|{post}|CG|{cpt}|{desc}|{qty}|{unit}|{amt}|USD|{plan}|{fee}|{dept}|{ptype}| |{cpt}||"

# Add near your other segment builders
def seg_dg1(enc: Encounter, icd_code: str, desc: str = "", *,
            set_id: int = 1, diag_type: str = "F",
            coding_system: str = "ICD-10-CM",
            diag_dt: Optional[str] = None) -> str:
    """
    DG1 - Diagnosis
      DG1-1  Set ID
      DG1-2  (deprecated/unused in many feeds)
      DG1-3  Diagnosis Code (CE) -> <code>^<text>^<coding system>
      DG1-4  Diagnosis Description (optional; leave blank if DG1-3.2 used)
      DG1-5  Diagnosis Date/Time
      DG1-6  Diagnosis Type (W=Working, F=Final, A=Admitting, ...)
    """
    # When to timestamp the diagnosis: prefer observation completion time, else admit time
    if diag_dt is None:
        diag_dt = getattr(enc, "admit_datetime", None)
    dt_hl7 = ts_hl7(diag_dt) if diag_dt else ""

    # Put display text in CE.2; keep DG1-4 blank (common pattern)
    ce = f"{icd_code}^{hl7_escape(desc)}^{coding_system}" if icd_code else "^^"
    return f"DG1|{set_id}||{ce}||{dt_hl7}|{diag_type}"

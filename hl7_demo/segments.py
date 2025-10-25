# segments.py
# HL7 v2.5 segment builders used across MediLacra.
# Behavior is unchanged; only structured logging and explanatory comments were added.

import uuid
from datetime import datetime
from typing import List, Optional
import textwrap

# --- Logging (structured) ---
try:
    from utils.log_utils import get_logger
except Exception:
    from log_utils import get_logger  # type: ignore

logger = get_logger(name="MediLacra", context={"component": "segments"})

# --- Models & Utils (existing imports) ---
from .models import Encounter, Observation, Transaction
from .utils import ts_hl7, hl7_name_from_full, hl7_name_from_display, hl7_escape, get_next_control_id


def seg_msh(
    message_type: str,
    *,
    sending_app: str = "FAKELAB",
    sending_facility: str = "MEDILACRAHS",
    receiving_app: str = "MLHS",
    receiving_facility: str = "STAGE",
) -> str:
    """
    MSH - Message Header (v2.5)
      Accepts optional sender/receiver. Defaults preserve prior behavior.
    """
    try:
        logger.info("Building MSH", extra={"extra": {"input_message_type": message_type}})
        now = datetime.now().strftime("%Y%m%d%H%M%S")
        structures = {"ADT^A01": "ADT_A01", "ORU^R01": "ORU_R01", "DFT^P03": "DFT_P03"}
        if "^" in message_type and message_type.count("^") == 1:
            message_type = f"{message_type}^{structures.get(message_type, '')}"
        control_id = str(get_next_control_id())
        print (f"MessageID= {control_id}")

        msh = (
            f"MSH|^~\\&|{sending_app}|{sending_facility}|{receiving_app}|{receiving_facility}|"
            f"{now}||{message_type}|{control_id}|P|2.5|||AL|NE||UNICODE UTF-8"
        )
        logger.info("MSH built", extra={"extra": {"message_type": message_type, "control_id": control_id}})
        return msh
    except Exception as e:
        logger.error("Error building MSH", extra={"extra": {"error": str(e)}})
        raise



def seg_evn(enc: Encounter, event_type: str = "A01") -> str:
    """
    EVN - Event Type
      EVN-1 = Event Type Code (e.g., A01)
      EVN-2/6 = Recorded Date/Time (admit time for demo)
    """
    try:
        evn_ts = ts_hl7(enc.admit_datetime)
        evn = f"EVN|{event_type}|{evn_ts}||||{evn_ts}"
        logger.info("EVN built", extra={"extra": {"event_type": event_type, "timestamp": evn_ts}})
        return evn
    except Exception as e:
        logger.error("Error building EVN", extra={"extra": {"error": str(e)}})
        raise


def seg_pid(p) -> str:
    """
    PID - Patient Identification
      PID-3 = Patient Identifier (internal synthetic ID)
      PID-5 = Patient Name (HL7 formatted)
      PID-7 = DOB, PID-8 = Sex, PID-10 = Race, PID-11 = Address, PID-13 = Phone
      PID-19 = SSN (synthetic)
    """
    try:
        # Import within function to avoid circulars in some run contexts
        from .utils import one_line

        street = one_line(p.address)  # street only
        phone = one_line(p.phone)
        addr_comp = f"{street}^^{p.city}^{p.state}^{p.zip_code}"  # PID-11.3 city, 11.4 state, 11.5 zip

        pid = (
            f"PID|1||{p.patient_id}||{hl7_name_from_display(p.patient_name)}||"
            f"{ts_hl7(p.date_of_birth)}|{p.sex}||{p.race}|{addr_comp}||{phone}||||||{p.ssn}"
        )
        logger.info(
            "PID built",
            extra={"extra": {"patient_id": getattr(p, "patient_id", None), "zip": getattr(p, "zip_code", None)}},
        )
        return pid
    except Exception as e:
        logger.error("Error building PID", extra={"extra": {"error": str(e)}})
        raise


def seg_pv1(enc: Encounter) -> str:
    """
    PV1 - Patient Visit
      PV1-2  Patient Class (e.g., OUTPATIENT)
      PV1-3  Assigned Patient Location
      PV1-7  Attending Doctor (ID^Name)
      PV1-19 Visit Number
      PV1-44/45 Admit/Discharge Date/Time
    """
    try:
        admit = ts_hl7(enc.admit_datetime)
        disch = ts_hl7(enc.discharge_datetime)
        attending_nm = hl7_name_from_full(enc.attending_provider_name)
        pv1 = (
            f"PV1|1|{enc.patient_class}|{enc.assigned_patient_location}||||{enc.attending_provider_id}^{attending_nm}"
            f"||{enc.hospital_service}||||||||||{enc.visit_number}|||||||||||||||||||||||||{admit}|{disch}"
        )
        logger.info(
            "PV1 built",
            extra={"extra": {"visit_number": getattr(enc, "visit_number", None), "admit": admit, "discharge": disch}},
        )
        return pv1
    except Exception as e:
        logger.error("Error building PV1", extra={"extra": {"error": str(e)}})
        raise


def seg_orc(enc: Encounter) -> str:
    """
    ORC - Common Order
      ORC-1 = RE (Observation Result)
      ORC-2/3 = Placer/Filler Order Numbers
      ORC-12 = Ordering Provider (ID^Name)
    """
    try:
        ordering_nm = hl7_name_from_full(enc.ordering_provider_name)
        orc = f"ORC|RE|{enc.placer_order_number}|{enc.filler_order_number}||CM|||||{enc.ordering_provider_id}^{ordering_nm}"
        logger.info(
            "ORC built",
            extra={"extra": {"placer": getattr(enc, "placer_order_number", None), "filler": getattr(enc, "filler_order_number", None)}},
        )
        return orc
    except Exception as e:
        logger.error("Error building ORC", extra={"extra": {"error": str(e)}})
        raise


def seg_obr(enc: Encounter, obs: Optional[Observation]) -> str:
    """
    OBR - Observation Request
      OBR-4  Universal Service ID (CPT^Text^CPT when available)
      OBR-7  Observation Date/Time
      OBR-16 Ordering Provider (ID^Name)
    """
    try:
        cpt = obs.cpt_code if obs else ""
        desc = (getattr(obs, "cpt_description", "") or obs.procedure_description) if obs else ""
        usi = f"{cpt}^{desc}^CPT" if (cpt or desc) else ""
        when = ts_hl7(obs.completed_time if obs else enc.admit_datetime)
        ordering_nm = hl7_name_from_full(enc.ordering_provider_name)
        obr = f"OBR|1|{enc.placer_order_number}|{enc.filler_order_number}|{usi}|R|||{when}||||||||{enc.ordering_provider_id}^{ordering_nm}"
        logger.info(
            "OBR built",
            extra={"extra": {"placer": getattr(enc, "placer_order_number", None), "filler": getattr(enc, "filler_order_number", None), "when": when}},
        )
        return obr
    except Exception as e:
        logger.error("Error building OBR", extra={"extra": {"error": str(e)}})
        raise


def seg_obx(obs: Observation) -> str:
    """
    OBX - Observation Result (single text value)
      OBX-2 = TX (text)
      OBX-3 = Identifier (CPT^Text^CPT)
      OBX-5 = Value (escaped)
      OBX-11 = Result Status (default F)
      OBX-15 = Producer's ID (site/service)
    """
    try:
        ident = f"{obs.cpt_code}^{(getattr(obs,'cpt_description','') or obs.procedure_description)}^CPT"

        sub_id = obs.observation_sub_id or "1"
        value = obs.observation_text or ""
        status = obs.result_status or "F"
        producer = "MEDILACRAHS^DEPT1"
        obx = f"OBX|1|TX|{ident}|{sub_id}|{hl7_escape(value)}|||||||{status}|||{producer}"
        logger.info("OBX built (TX)", extra={"extra": {"cpt": getattr(obs, "cpt_code", None), "status": status}})
        return obx
    except Exception as e:
        logger.error("Error building OBX (TX)", extra={"extra": {"error": str(e)}})
        raise


def seg_obx_lines(obs: Observation, start_set_id: int = 1, wrap_width: int = 200) -> List[str]:
    """
    OBX - Multi-line text as sequential OBX|TX segments.
      Each wrapped or newline-split chunk becomes OBX with incremented set/sub IDs.
    """
    try:
        ident = f"{obs.cpt_code}^{(getattr(obs,'cpt_description','') or obs.procedure_description)}^CPT"
        status = obs.result_status or "F"
        producer = "MEDILACRAHS^DEPT1"

        norm = (obs.observation_text or "").replace("\r\n", "\n").replace("\r", "\n")
        raw_lines = norm.split("\n")

        # Wrap lines without breaking words/hyphens
        lines = []
        for ln in raw_lines:
            ln = (ln or "").strip()
            if not ln:
                lines.append("")
                continue
            if len(ln) > wrap_width:
                lines.extend(
                    textwrap.wrap(ln, width=wrap_width, break_long_words=False, break_on_hyphens=False)
                )
            else:
                lines.append(ln)

        segs: List[str] = []
        set_id = start_set_id
        sub_id = 1
        for ln in lines:
            val = hl7_escape(ln)
            segs.append(f"OBX|{set_id}|TX|{ident}|{sub_id}|{val}||||||{status}|||{producer}")
            set_id += 1
            sub_id += 1

        logger.info(
            "OBX lines built",
            extra={"extra": {"segments": len(segs), "start_set_id": start_set_id, "wrap_width": wrap_width}},
        )
        return segs
    except Exception as e:
        logger.error("Error building OBX lines", extra={"extra": {"error": str(e)}})
        raise


def seg_ft1(tx: Transaction, obs: Optional[Observation]) -> str:
    """
    FT1 - Financial Transaction
      FT1-4/5  Transaction/Posting dates
      FT1-7    Transaction Type (CG = charge)
      FT1-8/9  CPT/Description (from observation when present)
      FT1-10   Quantity
      FT1-11   Unit Price
      FT1-12   Total Amount
      FT1-19   Insurance Plan ID
      FT1-20   Fee Schedule
    """
    try:
        tx_dt = ts_hl7(tx.transaction_date)
        post = tx_dt
        cpt = obs.cpt_code if obs else ""
        desc = obs.procedure_description if obs else "CHARGE"
        qty = tx.transaction_quantity
        unit = tx.unit_cost
        amt = tx.transaction_amount
        plan = tx.insurance_plan_id
        fee = tx.fee_schedule
        dept = "RAD"
        ptype = "OUTPATIENT"
        ft1 = (
            f"FT1|1|{tx.transaction_id}| |{tx_dt}|{post}|CG|{cpt}|{desc}|{qty}|{unit}|{amt}|USD|{plan}|{fee}|{dept}|{ptype}| |{cpt}||"
        )
        logger.info(
            "FT1 built",
            extra={
                "extra": {
                    "transaction_id": getattr(tx, "transaction_id", None),
                    "amount": amt,
                    "cpt": cpt,
                    "quantity": qty,
                }
            },
        )
        return ft1
    except Exception as e:
        logger.error("Error building FT1", extra={"extra": {"error": str(e)}})
        raise


# Add near your other segment builders
def seg_dg1(
    enc: Encounter,
    icd_code: str,
    desc: str = "",
    *,
    set_id: int = 1,
    diag_type: str = "F",
    coding_system: str = "ICD-10-CM",
    diag_dt: Optional[str] = None,
) -> str:
    """
    DG1 - Diagnosis
      DG1-1  Set ID
      DG1-3  Diagnosis Code (CE) -> <code>^<text>^<coding system>
      DG1-5  Diagnosis Date/Time
      DG1-6  Diagnosis Type (W=Working, F=Final, A=Admitting, ...)
    """
    try:
        # When to timestamp the diagnosis: prefer observation completion time, else admit time
        if diag_dt is None:
            diag_dt = getattr(enc, "admit_datetime", None)
        dt_hl7 = ts_hl7(diag_dt) if diag_dt else ""

        # Put display text in CE.2; keep DG1-4 blank (common pattern)
        ce = f"{icd_code}^{hl7_escape(desc)}^{coding_system}" if icd_code else "^^"
        dg1 = f"DG1|{set_id}||{ce}||{dt_hl7}|{diag_type}"
        logger.info("DG1 built", extra={"extra": {"icd": icd_code, "diag_type": diag_type, "datetime": dt_hl7}})
        return dg1
    except Exception as e:
        logger.error("Error building DG1", extra={"extra": {"error": str(e)}})
        raise


# --- Gender Harmony & SPCU CWE OBX builders (keep semantics; add logging) ---

from typing import Optional, Tuple  # keep existing pattern
from .utils import ts_hl7, hl7_escape  # re-imports retained for compatibility

_PRODUCER = "MEDILACRAHS^DEPT1"  # keep consistent with seg_obx/seg_obx_lines


def _obx_cwe(
    *,
    set_id: int,
    obx3: Tuple[str, str, str],
    value: Tuple[str, str, str],
    sub_id: int = 1,
    status: str = "F",
    effective_dt: Optional[str] = None,  # "YYYY-MM-DD HH:MM:SS" or None
    method: Optional[Tuple[str, str, str]] = None,  # OBX-17 (e.g., source)
    performing_org: Optional[str] = None,  # OBX-23
) -> str:
    """
    Generic OBX builder for CWE values in v2.5.
      OBX-3: (code, text, coding_system)
      OBX-5: (code, text, coding_system)
      OBX-14: Effective Date/Time
      OBX-17: Method/Provenance (optional CWE)
      OBX-23: Performing Organization (text)
    """
    try:
        obx3_ce = f"{obx3[0]}^{hl7_escape(obx3[1])}^{obx3[2]}"
        val_ce = f"{value[0]}^{hl7_escape(value[1])}^{value[2]}"

        obx14 = ts_hl7(effective_dt) if effective_dt else ""  # OBX-14
        obx17 = f"{method[0]}^{hl7_escape(method[1])}^{method[2]}" if method else ""  # OBX-17
        obx23 = performing_org or ""  # OBX-23

        obx = (
            f"OBX|{set_id}|CWE|{obx3_ce}|{sub_id}|{val_ce}||||||{status}||R|{_PRODUCER}|"
            f"|{obx14}|{''}|{obx17}||||{obx23}"
        )
        logger.info("OBX built (CWE)", extra={"extra": {"obx3_code": obx3[0], "value_code": value[0], "set_id": set_id}})
        return obx
    except Exception as e:
        logger.error("Error building OBX (CWE)", extra={"extra": {"error": str(e)}})
        raise


def seg_obx_gender_identity(
    *,
    set_id: int,
    gi_code: str = "446151000124109",  # SNOMED CT Male (example default)
    gi_text: str = "Male",
    gi_system: str = "SCT",
    effective_dt: Optional[str] = None,
    method: Optional[Tuple[str, str, str]] = None,
    performing_org: Optional[str] = None,
) -> str:
    """OBX for LOINC 76691-5 (Gender identity)"""
    try:
        obx3 = ("76691-5", "Gender identity", "LN")
        value = (gi_code, gi_text, gi_system)
        return _obx_cwe(
            set_id=set_id,
            obx3=obx3,
            value=value,
            effective_dt=effective_dt,
            method=method,
            performing_org=performing_org,
        )
    except Exception as e:
        logger.error("Error building GI OBX", extra={"extra": {"error": str(e)}})
        raise


def seg_obx_pronouns(
    *,
    set_id: int,
    pronoun_code: str = "LA29520-6",  # they/them (example default)
    pronoun_text: str = "they/them/their/theirs/themselves",
    pronoun_system: str = "LN",  # LOINC answer list codes
    effective_dt: Optional[str] = None,
    method: Optional[Tuple[str, str, str]] = None,
    performing_org: Optional[str] = None,
) -> str:
    """OBX for LOINC 90778-2 (Personal pronouns - Reported)"""
    try:
        obx3 = ("90778-2", "Personal pronouns - Reported", "LN")
        value = (pronoun_code, pronoun_text, pronoun_system)
        return _obx_cwe(
            set_id=set_id,
            obx3=obx3,
            value=value,
            effective_dt=effective_dt,
            method=method,
            performing_org=performing_org,
        )
    except Exception as e:
        logger.error("Error building Pronouns OBX", extra={"extra": {"error": str(e)}})
        raise


def seg_obx_spcu(
    *,
    set_id: int,
    spcu_code: str = "F-T",  # example: "Apply female-typical settings"
    spcu_text: str = "Apply female-typical settings",
    spcu_system: str = "HL7",  # use your chosen THO/HL7 system id
    effective_dt: Optional[str] = None,
    method: Optional[Tuple[str, str, str]] = None,
    performing_org: Optional[str] = None,
) -> str:
    """OBX for SPCU (Sex Parameter for Clinical Use) in v2.5"""
    try:
        obx3 = ("SPCU", "Sex parameter for clinical use", "HL7")
        value = (spcu_code, spcu_text, spcu_system)
        return _obx_cwe(
            set_id=set_id,
            obx3=obx3,
            value=value,
            effective_dt=effective_dt,
            method=method,
            performing_org=performing_org,
        )
    except Exception as e:
        logger.error("Error building SPCU OBX", extra={"extra": {"error": str(e)}})
        raise

# segments.py
#
# HL7 v2.5 segment builders used across MediLacra.
#
# The goal of this module is to keep HL7 generation straightforward:
#   - MediLacra entities contain readable canonical values.
#   - This module translates those values into HL7 v2.5 fields.
#   - Fields are populated by explicit HL7 field number wherever possible.
#
# Using indexed field lists makes it much easier to see exactly where
# a value lands in the HL7 segment and avoids errors caused by manually
# counting pipe delimiters.

from datetime import datetime
from typing import List, Optional, Tuple
import textwrap

# --- Logging -------------------------------------------------------------

try:
    from utils.log_utils import get_logger
except Exception:
    from log_utils import get_logger  # type: ignore

logger = get_logger(
    name="MediLacra",
    context={"component": "segments"},
)


# --- Models & utilities --------------------------------------------------

from .models import Patient, Encounter, Observation, Transaction
from .utils import (
    ts_hl7,
    hl7_name_from_full,
    hl7_name_from_display,
    hl7_escape,
    get_next_control_id,
)


# =========================================================================
# Simple HL7 value mappings
# =========================================================================
#
# MediLacra stores human-readable values in its entity model.
# These small dictionaries translate those values into common HL7 v2
# codes when the message is rendered.


# PV1-2 Patient Class
PATIENT_CLASS_CODES = {
    "INPATIENT": "I",
    "OUTPATIENT": "O",
    "EMERGENCY": "E",
}


# PID-15 Primary Language
LANGUAGE_CODES = {
    "English": ("en", "English"),
    "Spanish": ("es", "Spanish"),
    "Portuguese": ("pt", "Portuguese"),
    "French": ("fr", "French"),
    "Chinese": ("zh", "Chinese"),
}


# PID-16 Marital Status
MARITAL_STATUS_CODES = {
    "Single": ("S", "Single"),
    "Married": ("M", "Married"),
    "Divorced": ("D", "Divorced"),
    "Widowed": ("W", "Widowed"),
}


# PID-22 Ethnic Group
ETHNICITY_CODES = {
    "Hispanic or Latino": ("H", "Hispanic or Latino"),
    "Not Hispanic or Latino": ("N", "Not Hispanic or Latino"),
}


# HL7 relationship values used in GT1 and IN1.
RELATIONSHIP_CODES = {
    "SELF": ("SEL", "Self"),
    "SPOUSE": ("SPO", "Spouse"),
    "CHILD": ("CHD", "Child"),
    "PARENT": ("PAR", "Parent"),
    "GUARDIAN": ("GRD", "Guardian"),
    "OTHER": ("OTH", "Other"),
}


# PV1-14 Admit Source.
#
# These correspond to the standard suggested values where possible.
# "Self Referral" does not have a direct value in the standard table,
# so MediLacra uses a local demo value of "SR".
ADMIT_SOURCE_CODES = {
    "Physician Referral": "1",
    "Clinic Referral": "2",
    "Transfer": "4",
    "Emergency Department": "7",
    "Self Referral": "SR",
}


# PV1-36 Discharge Disposition.
DISCHARGE_DISPOSITION_CODES = {
    "Home": "01",
    "Home with Services": "06",
    "Skilled Nursing Facility": "03",
    "Transfer to Another Facility": "02",
}


# =========================================================================
# Small formatting helpers
# =========================================================================


def _ce(
    code: str,
    text: str,
    coding_system: str,
) -> str:
    """
    Build a simple HL7 CE-style value.

    Example:
        M^Married^HL70002
    """
    if not code and not text:
        return ""

    return (
        f"{hl7_escape(str(code))}^"
        f"{hl7_escape(str(text))}^"
        f"{coding_system}"
    )


def _relationship_ce(value: str) -> str:
    """
    Convert a readable MediLacra relationship into an HL7 CE value.

    Example:
        SELF -> SEL^Self^HL70063
    """
    code, description = RELATIONSHIP_CODES.get(
        (value or "").upper(),
        ("OTH", "Other"),
    )

    return _ce(
        code,
        description,
        "HL70063",
    )


def _provider_xcn(
    provider_id: str,
    provider_name: str,
) -> str:
    """
    Build the basic portion of an XCN provider value.

    MediLacra currently stores:
        provider ID
        display name

    Example:
        P123456^SMITH^JANE
    """
    if not provider_id and not provider_name:
        return ""

    formatted_name = (
        hl7_name_from_full(provider_name)
        if provider_name
        else ""
    )

    if provider_id and formatted_name:
        return f"{provider_id}^{formatted_name}"

    if provider_id:
        return provider_id

    return f"^{formatted_name}"


# =========================================================================
# MSH - Message Header
# =========================================================================


def seg_msh(
    message_type: str,
    *,
    sending_app: str = "FAKELAB",
    sending_facility: str = "MEDILACRAHS",
    receiving_app: str = "MLHS",
    receiving_facility: str = "STAGE",
) -> str:
    """
    Build an HL7 v2.5 MSH segment.

    MSH-3  Sending Application
    MSH-4  Sending Facility
    MSH-5  Receiving Application
    MSH-6  Receiving Facility
    MSH-7  Message Date/Time
    MSH-9  Message Type / Trigger Event / Structure
    MSH-10 Message Control ID
    MSH-11 Processing ID
    MSH-12 Version
    """
    try:
        logger.info(
            "Building MSH",
            extra={
                "extra": {
                    "input_message_type": message_type,
                }
            },
        )

        now = datetime.now().strftime("%Y%m%d%H%M%S")

        structures = {
            "ADT^A01": "ADT_A01",
            "ORU^R01": "ORU_R01",
            "DFT^P03": "DFT_P03",
            "ORM^O01": "ORM_O01",
        }

        # If the caller supplies only message type + trigger event,
        # append the standard message structure when known.
        if "^" in message_type and message_type.count("^") == 1:
            structure = structures.get(message_type)

            if structure:
                message_type = (
                    f"{message_type}^{structure}"
                )

        control_id = str(
            get_next_control_id()
        )

        msh = (
            f"MSH|^~\\&|"
            f"{sending_app}|"
            f"{sending_facility}|"
            f"{receiving_app}|"
            f"{receiving_facility}|"
            f"{now}||"
            f"{message_type}|"
            f"{control_id}|"
            f"P|2.5|||AL|NE||UNICODE UTF-8"
        )

        logger.info(
            "MSH built",
            extra={
                "extra": {
                    "message_type": message_type,
                    "control_id": control_id,
                }
            },
        )

        return msh

    except Exception as e:
        logger.error(
            "Error building MSH",
            extra={
                "extra": {
                    "error": str(e),
                }
            },
        )
        raise


# =========================================================================
# EVN - Event Type
# =========================================================================


def seg_evn(
    enc: Encounter,
    event_type: str = "A01",
) -> str:
    """
    Build an EVN segment.

    EVN-1 Event Type Code
    EVN-2 Recorded Date/Time
    EVN-6 Event Occurred Date/Time
    """
    try:
        evn_ts = ts_hl7(
            enc.admit_datetime
        )

        fields = [""] * 7

        fields[1] = event_type
        fields[2] = evn_ts
        fields[6] = evn_ts

        evn = (
            "EVN|"
            + "|".join(fields[1:])
        )

        logger.info(
            "EVN built",
            extra={
                "extra": {
                    "event_type": event_type,
                    "timestamp": evn_ts,
                }
            },
        )

        return evn

    except Exception as e:
        logger.error(
            "Error building EVN",
            extra={
                "extra": {
                    "error": str(e),
                }
            },
        )
        raise


# =========================================================================
# PID - Patient Identification
# =========================================================================


def seg_pid(p: Patient) -> str:
    """
    Build a PID segment from the canonical Patient entity.

    Currently populated:

    PID-1   Set ID
    PID-3   Patient Identifier
    PID-5   Patient Name
    PID-7   Date of Birth
    PID-8   Administrative Sex
    PID-10  Race
    PID-11  Address
    PID-13  Phone / Email
    PID-15  Primary Language
    PID-16  Marital Status
    PID-19  SSN
    PID-22  Ethnic Group

    The patient's synthetic email is emitted as a second PID-13
    repetition using the XTN datatype.
    """
    try:
        from .utils import one_line

        # Allocate through PID-22.
        # Index 0 is intentionally unused so the index equals
        # the HL7 field number.
        fields = [""] * 23

        # PID-1 Set ID
        fields[1] = "1"

        # PID-3 Patient Identifier List
        fields[3] = str(
            p.patient_id
        )

        # PID-5 Patient Name
        fields[5] = (
            hl7_name_from_display(
                p.patient_name
            )
        )

        # PID-7 Date/Time of Birth
        fields[7] = ts_hl7(
            p.date_of_birth
        )

        # PID-8 Administrative Sex
        fields[8] = str(
            p.sex
        )

        # PID-10 Race
        fields[10] = hl7_escape(
            str(p.race)
        )

        # PID-11 Patient Address
        street = one_line(
            p.address
        )

        fields[11] = (
            f"{hl7_escape(street)}^^"
            f"{hl7_escape(str(p.city))}^"
            f"{hl7_escape(str(p.state))}^"
            f"{hl7_escape(str(p.zip_code))}"
        )

        # PID-13 Phone Number - Home
        #
        # XTN repetition 1 = phone.
        # XTN repetition 2 = email.
        #
        # The first XTN component is retained for the phone because
        # MediLacra's generated phone value may contain formatting.
        phone = one_line(
            p.phone
        )

        phone_xtn = (
            f"{hl7_escape(phone)}^PRN^PH"
        )

        email = getattr(
            p,
            "email",
            "",
        )

        if email:
            # XTN:
            #   component 1 blank
            #   component 2 NET
            #   component 3 Internet
            #   component 4 email
            email_xtn = (
                f"^NET^Internet^"
                f"{hl7_escape(email)}"
            )

            fields[13] = (
                f"{phone_xtn}~{email_xtn}"
            )

        else:
            fields[13] = phone_xtn

        # PID-15 Primary Language
        language = LANGUAGE_CODES.get(
            getattr(
                p,
                "language",
                "",
            )
        )

        if language:
            fields[15] = _ce(
                language[0],
                language[1],
                "ISO639",
            )

        # PID-16 Marital Status
        marital_status = (
            MARITAL_STATUS_CODES.get(
                getattr(
                    p,
                    "marital_status",
                    "",
                )
            )
        )

        if marital_status:
            fields[16] = _ce(
                marital_status[0],
                marital_status[1],
                "HL70002",
            )

        # PID-19 SSN Number - Patient
        fields[19] = str(
            getattr(
                p,
                "ssn",
                "",
            )
        )

        # PID-22 Ethnic Group
        ethnicity = ETHNICITY_CODES.get(
            getattr(
                p,
                "ethnicity",
                "",
            )
        )

        if ethnicity:
            fields[22] = _ce(
                ethnicity[0],
                ethnicity[1],
                "HL70189",
            )

        pid = (
            "PID|"
            + "|".join(fields[1:])
        )

        logger.info(
            "PID built",
            extra={
                "extra": {
                    "patient_id": getattr(
                        p,
                        "patient_id",
                        None,
                    ),
                    "zip": getattr(
                        p,
                        "zip_code",
                        None,
                    ),
                    "language": getattr(
                        p,
                        "language",
                        None,
                    ),
                    "email": getattr(
                        p,
                        "email",
                        None,
                    ),
                }
            },
        )

        return pid

    except Exception as e:
        logger.error(
            "Error building PID",
            extra={
                "extra": {
                    "error": str(e),
                }
            },
        )
        raise


# =========================================================================
# PV1 - Patient Visit
# =========================================================================


def seg_pv1(enc: Encounter) -> str:
    """
    Build a PV1 segment from the canonical Encounter entity.

    Currently populated:

    PV1-1   Set ID
    PV1-2   Patient Class
    PV1-3   Assigned Patient Location
    PV1-7   Attending Doctor
    PV1-8   Referring Doctor
    PV1-10  Hospital Service
    PV1-14  Admit Source
    PV1-19  Visit Number
    PV1-36  Discharge Disposition
    PV1-44  Admit Date/Time
    PV1-45  Discharge Date/Time
    PV1-52  Other Healthcare Provider

    MediLacra currently uses PV1-52 for its mid-level provider.
    """
    try:
        # PV1 contains 52 fields in v2.5.
        fields = [""] * 53

        # PV1-1 Set ID
        fields[1] = "1"

        # PV1-2 Patient Class
        fields[2] = (
            PATIENT_CLASS_CODES.get(
                (
                    enc.patient_class
                    or ""
                ).upper(),
                enc.patient_class,
            )
        )

        # PV1-3 Assigned Patient Location
        fields[3] = str(
            enc.assigned_patient_location
        )

        # PV1-7 Attending Doctor
        fields[7] = _provider_xcn(
            enc.attending_provider_id,
            enc.attending_provider_name,
        )

        # PV1-8 Referring Doctor
        fields[8] = _provider_xcn(
            getattr(
                enc,
                "referring_provider_id",
                "",
            ),
            getattr(
                enc,
                "referring_provider_name",
                "",
            ),
        )

        # PV1-10 Hospital Service
        fields[10] = str(
            enc.hospital_service
        )

        # PV1-14 Admit Source
        admit_source = getattr(
            enc,
            "admit_source",
            "",
        )

        fields[14] = (
            ADMIT_SOURCE_CODES.get(
                admit_source,
                admit_source,
            )
        )

        # PV1-19 Visit Number
        fields[19] = str(
            enc.visit_number
        )

        # PV1-36 Discharge Disposition
        discharge_disposition = getattr(
            enc,
            "discharge_disposition",
            "",
        )

        fields[36] = (
            DISCHARGE_DISPOSITION_CODES.get(
                discharge_disposition,
                discharge_disposition,
            )
        )

        # PV1-44 Admit Date/Time
        fields[44] = ts_hl7(
            enc.admit_datetime
        )

        # PV1-45 Discharge Date/Time
        fields[45] = ts_hl7(
            enc.discharge_datetime
        )

        # PV1-52 Other Healthcare Provider
        mid_level_id = getattr(
            enc,
            "mid_level_provider_id",
            "",
        )

        mid_level_name = getattr(
            enc,
            "mid_level_provider_name",
            "",
        )

        if (
            mid_level_id
            or mid_level_name
        ):
            fields[52] = _provider_xcn(
                mid_level_id,
                mid_level_name,
            )

        pv1 = (
            "PV1|"
            + "|".join(fields[1:])
        )

        logger.info(
            "PV1 built",
            extra={
                "extra": {
                    "visit_number": getattr(
                        enc,
                        "visit_number",
                        None,
                    ),
                    "patient_class": fields[2],
                    "admit_source": fields[14],
                    "discharge_disposition": fields[36],
                    "admit": fields[44],
                    "discharge": fields[45],
                }
            },
        )

        return pv1

    except Exception as e:
        logger.error(
            "Error building PV1",
            extra={
                "extra": {
                    "error": str(e),
                }
            },
        )
        raise


# =========================================================================
# GT1 - Guarantor
# =========================================================================


def seg_gt1(
    tx: Transaction,
    *,
    set_id: int = 1,
) -> str:
    """
    Build a basic GT1 Guarantor segment.

    Currently populated:

    GT1-1   Set ID
    GT1-3   Guarantor Name
    GT1-11  Guarantor Relationship

    The MediLacra Transaction currently contains only guarantor name
    and relationship, so the segment intentionally remains simple.
    """
    try:
        fields = [""] * 12

        # GT1-1 Set ID
        fields[1] = str(
            set_id
        )

        # GT1-3 Guarantor Name
        guarantor_name = getattr(
            tx,
            "guarantor_name",
            "",
        )

        if guarantor_name:
            fields[3] = (
                hl7_name_from_display(
                    guarantor_name
                )
            )

        # GT1-11 Guarantor Relationship
        fields[11] = _relationship_ce(
            getattr(
                tx,
                "guarantor_relationship",
                "",
            )
        )

        gt1 = (
            "GT1|"
            + "|".join(fields[1:])
        )

        logger.info(
            "GT1 built",
            extra={
                "extra": {
                    "guarantor_name": (
                        guarantor_name
                    ),
                    "relationship": getattr(
                        tx,
                        "guarantor_relationship",
                        None,
                    ),
                }
            },
        )

        return gt1

    except Exception as e:
        logger.error(
            "Error building GT1",
            extra={
                "extra": {
                    "error": str(e),
                }
            },
        )
        raise


# =========================================================================
# IN1 - Insurance
# =========================================================================


def seg_in1(
    tx: Transaction,
    *,
    set_id: int = 1,
) -> str:
    """
    Build a basic IN1 Insurance segment.

    Currently populated:

    IN1-1   Set ID
    IN1-2   Insurance Plan ID
    IN1-8   Group Number
    IN1-14  Authorization Information
    IN1-15  Plan Type
    IN1-17  Insured's Relationship to Patient
    IN1-49  Insured's ID Number

    MediLacra currently stores insurance plan information directly on
    the Transaction rather than using a separate Coverage entity.
    """
    try:
        # Allocate through IN1-49.
        fields = [""] * 50

        # IN1-1 Set ID
        fields[1] = str(
            set_id
        )

        # IN1-2 Insurance Plan ID
        #
        # Keep the human-readable plan name alongside the synthetic
        # plan identifier.
        fields[2] = _ce(
            getattr(
                tx,
                "insurance_plan_id",
                "",
            ),
            getattr(
                tx,
                "insurance_plan_name",
                "",
            ),
            "L",
        )

        # IN1-8 Group Number
        fields[8] = str(
            getattr(
                tx,
                "group_number",
                "",
            )
        )

        # IN1-14 Authorization Information
        #
        # AUI components:
        #   Authorization Number ^ Date ^ Source
        #
        # MediLacra currently only models the authorization number.
        fields[14] = str(
            getattr(
                tx,
                "authorization_number",
                "",
            )
        )

        # IN1-15 Plan Type
        fields[15] = str(
            getattr(
                tx,
                "plan_type",
                "",
            )
        )

        # IN1-17 Insured's Relationship to Patient
        fields[17] = _relationship_ce(
            getattr(
                tx,
                "subscriber_relationship",
                "",
            )
        )

        # IN1-49 Insured's ID Number
        #
        # member_id is currently MediLacra's canonical identifier
        # for the insured/member.
        fields[49] = str(
            getattr(
                tx,
                "member_id",
                "",
            )
        )

        in1 = (
            "IN1|"
            + "|".join(fields[1:])
        )

        logger.info(
            "IN1 built",
            extra={
                "extra": {
                    "insurance_plan_id": getattr(
                        tx,
                        "insurance_plan_id",
                        None,
                    ),
                    "insurance_plan_name": getattr(
                        tx,
                        "insurance_plan_name",
                        None,
                    ),
                    "group_number": getattr(
                        tx,
                        "group_number",
                        None,
                    ),
                    "plan_type": getattr(
                        tx,
                        "plan_type",
                        None,
                    ),
                }
            },
        )

        return in1

    except Exception as e:
        logger.error(
            "Error building IN1",
            extra={
                "extra": {
                    "error": str(e),
                }
            },
        )
        raise


# =========================================================================
# ORC - Common Order
# =========================================================================


def seg_orc(enc: Encounter) -> str:
    """
    Build an ORC Common Order segment.

    ORC-1  Order Control
    ORC-2  Placer Order Number
    ORC-3  Filler Order Number
    ORC-5  Order Status
    ORC-12 Ordering Provider
    """
    try:
        fields = [""] * 13

        # ORC-1 Order Control
        fields[1] = "RE"

        # ORC-2 / ORC-3 Order Numbers
        fields[2] = str(
            enc.placer_order_number
        )

        fields[3] = str(
            enc.filler_order_number
        )

        # ORC-5 Order Status
        fields[5] = "CM"

        # ORC-12 Ordering Provider
        fields[12] = _provider_xcn(
            enc.ordering_provider_id,
            enc.ordering_provider_name,
        )

        orc = (
            "ORC|"
            + "|".join(fields[1:])
        )

        logger.info(
            "ORC built",
            extra={
                "extra": {
                    "placer": getattr(
                        enc,
                        "placer_order_number",
                        None,
                    ),
                    "filler": getattr(
                        enc,
                        "filler_order_number",
                        None,
                    ),
                }
            },
        )

        return orc

    except Exception as e:
        logger.error(
            "Error building ORC",
            extra={
                "extra": {
                    "error": str(e),
                }
            },
        )
        raise


# =========================================================================
# OBR - Observation Request
# =========================================================================


def seg_obr(
    enc: Encounter,
    obs: Optional[Observation],
) -> str:
    """
    Build an OBR Observation Request segment.

    OBR-1  Set ID
    OBR-2  Placer Order Number
    OBR-3  Filler Order Number
    OBR-4  Universal Service ID
    OBR-7  Observation Date/Time
    OBR-16 Ordering Provider
    """
    try:
        fields = [""] * 17

        # OBR-1 Set ID
        fields[1] = "1"

        # OBR-2 / OBR-3 Order Numbers
        fields[2] = str(
            enc.placer_order_number
        )

        fields[3] = str(
            enc.filler_order_number
        )

        # OBR-4 Universal Service ID
        cpt = (
            obs.cpt_code
            if obs
            else ""
        )

        description = ""

        if obs:
            description = (
                getattr(
                    obs,
                    "cpt_description",
                    "",
                )
                or obs.procedure_description
            )

        if cpt or description:
            fields[4] = _ce(
                cpt,
                description,
                "CPT",
            )

        # OBR-7 Observation Date/Time
        observation_time = (
            obs.completed_time
            if obs
            else enc.admit_datetime
        )

        fields[7] = ts_hl7(
            observation_time
        )

        # OBR-16 Ordering Provider
        fields[16] = _provider_xcn(
            enc.ordering_provider_id,
            enc.ordering_provider_name,
        )

        obr = (
            "OBR|"
            + "|".join(fields[1:])
        )

        logger.info(
            "OBR built",
            extra={
                "extra": {
                    "placer": getattr(
                        enc,
                        "placer_order_number",
                        None,
                    ),
                    "filler": getattr(
                        enc,
                        "filler_order_number",
                        None,
                    ),
                    "when": fields[7],
                    "cpt": cpt,
                }
            },
        )

        return obr

    except Exception as e:
        logger.error(
            "Error building OBR",
            extra={
                "extra": {
                    "error": str(e),
                }
            },
        )
        raise


# =========================================================================
# OBX - Observation Result
# =========================================================================


def seg_obx(obs: Observation) -> str:
    """
    Build one text OBX result.

    OBX-1  Set ID
    OBX-2  Value Type
    OBX-3  Observation Identifier
    OBX-4  Observation Sub-ID
    OBX-5  Observation Value
    OBX-11 Observation Result Status
    OBX-14 Date/Time of Observation
    OBX-15 Producer's ID
    """
    try:
        fields = [""] * 16

        fields[1] = "1"
        fields[2] = "TX"

        description = (
            getattr(
                obs,
                "cpt_description",
                "",
            )
            or obs.procedure_description
        )

        fields[3] = _ce(
            obs.cpt_code,
            description,
            "CPT",
        )

        fields[4] = (
            obs.observation_sub_id
            or "1"
        )

        fields[5] = hl7_escape(
            obs.observation_text
            or ""
        )

        fields[11] = (
            obs.result_status
            or "F"
        )

        if getattr(
            obs,
            "completed_time",
            "",
        ):
            fields[14] = ts_hl7(
                obs.completed_time
            )

        fields[15] = (
            "MEDILACRAHS^DEPT1"
        )

        obx = (
            "OBX|"
            + "|".join(fields[1:])
        )

        logger.info(
            "OBX built (TX)",
            extra={
                "extra": {
                    "cpt": getattr(
                        obs,
                        "cpt_code",
                        None,
                    ),
                    "status": fields[11],
                }
            },
        )

        return obx

    except Exception as e:
        logger.error(
            "Error building OBX (TX)",
            extra={
                "extra": {
                    "error": str(e),
                }
            },
        )
        raise


def seg_obx_lines(
    obs: Observation,
    start_set_id: int = 1,
    wrap_width: int = 200,
) -> List[str]:
    """
    Split a report into sequential text OBX segments.

    Each source line or wrapped line becomes its own OBX.

    OBX-1 increments for every segment.
    OBX-4 increments as the observation sub-ID.
    """
    try:
        description = (
            getattr(
                obs,
                "cpt_description",
                "",
            )
            or obs.procedure_description
        )

        identifier = _ce(
            obs.cpt_code,
            description,
            "CPT",
        )

        status = (
            obs.result_status
            or "F"
        )

        producer = (
            "MEDILACRAHS^DEPT1"
        )

        normalized = (
            obs.observation_text
            or ""
        ).replace(
            "\r\n",
            "\n",
        ).replace(
            "\r",
            "\n",
        )

        raw_lines = normalized.split(
            "\n"
        )

        lines: List[str] = []

        # Preserve meaningful line boundaries while wrapping very
        # long report lines to a manageable size.
        for line in raw_lines:
            line = (
                line
                or ""
            ).strip()

            if not line:
                lines.append("")
                continue

            if len(line) > wrap_width:
                lines.extend(
                    textwrap.wrap(
                        line,
                        width=wrap_width,
                        break_long_words=False,
                        break_on_hyphens=False,
                    )
                )

            else:
                lines.append(line)

        segments: List[str] = []

        set_id = start_set_id
        sub_id = 1

        for line in lines:
            fields = [""] * 16

            fields[1] = str(
                set_id
            )

            fields[2] = "TX"
            fields[3] = identifier
            fields[4] = str(
                sub_id
            )

            fields[5] = hl7_escape(
                line
            )

            fields[11] = status

            if getattr(
                obs,
                "completed_time",
                "",
            ):
                fields[14] = ts_hl7(
                    obs.completed_time
                )

            fields[15] = producer

            segment = (
                "OBX|"
                + "|".join(fields[1:])
            )

            segments.append(
                segment
            )

            set_id += 1
            sub_id += 1

        logger.info(
            "OBX lines built",
            extra={
                "extra": {
                    "segments": len(
                        segments
                    ),
                    "start_set_id": (
                        start_set_id
                    ),
                    "wrap_width": (
                        wrap_width
                    ),
                }
            },
        )

        return segments

    except Exception as e:
        logger.error(
            "Error building OBX lines",
            extra={
                "extra": {
                    "error": str(e),
                }
            },
        )
        raise


# =========================================================================
# FT1 - Financial Transaction
# =========================================================================


def seg_ft1(
    tx: Transaction,
    obs: Optional[Observation],
) -> str:
    """
    Build an FT1 Financial Transaction segment.

    Currently populated:

    FT1-1  Set ID
    FT1-2  Transaction ID
    FT1-4  Transaction Date
    FT1-5  Transaction Posting Date
    FT1-6  Transaction Type
    FT1-7  Transaction Code
    FT1-8  Transaction Description
    FT1-10 Transaction Quantity
    FT1-11 Transaction Amount - Extended
    FT1-12 Transaction Amount - Unit
    FT1-14 Insurance Plan ID
    FT1-17 Fee Schedule
    FT1-19 Diagnosis Code
    FT1-20 Performed By
    FT1-22 Unit Cost
    FT1-25 Procedure Code
    """
    try:
        fields = [""] * 26

        transaction_date = ts_hl7(
            tx.transaction_date
        )

        cpt = (
            obs.cpt_code
            if obs
            else ""
        )

        description = (
            obs.procedure_description
            if obs
            else "CHARGE"
        )

        # FT1-1 Set ID
        fields[1] = "1"

        # FT1-2 Transaction ID
        fields[2] = str(
            tx.transaction_id
        )

        # FT1-4 Transaction Date
        fields[4] = (
            transaction_date
        )

        # FT1-5 Transaction Posting Date
        fields[5] = (
            transaction_date
        )

        # FT1-6 Transaction Type
        fields[6] = "CG"

        # FT1-7 Transaction Code
        if cpt or description:
            fields[7] = _ce(
                cpt,
                description,
                "CPT",
            )

        # FT1-8 Transaction Description
        fields[8] = hl7_escape(
            description
        )

        # FT1-10 Transaction Quantity
        fields[10] = str(
            tx.transaction_quantity
        )

        # FT1-11 Transaction Amount - Extended
        #
        # CP contains a monetary amount. For the current demo we
        # represent the MO portion as quantity&currency.
        fields[11] = (
            f"{tx.transaction_amount}&USD"
        )

        # FT1-12 Transaction Amount - Unit
        fields[12] = (
            f"{tx.unit_cost}&USD"
        )

        # FT1-14 Insurance Plan ID
        fields[14] = _ce(
            getattr(
                tx,
                "insurance_plan_id",
                "",
            ),
            getattr(
                tx,
                "insurance_plan_name",
                "",
            ),
            "L",
        )

        # FT1-17 Fee Schedule
        fields[17] = str(
            tx.fee_schedule
        )

        if obs:
            # FT1-19 Diagnosis Code
            if getattr(
                obs,
                "icd_code",
                "",
            ):
                fields[19] = _ce(
                    obs.icd_code,
                    getattr(
                        obs,
                        "icd_description",
                        "",
                    ),
                    "ICD-10-CM",
                )

            # FT1-20 Performed By
            if (
                getattr(
                    obs,
                    "performing_provider_id",
                    "",
                )
                or getattr(
                    obs,
                    "performing_provider_name",
                    "",
                )
            ):
                fields[20] = (
                    _provider_xcn(
                        getattr(
                            obs,
                            "performing_provider_id",
                            "",
                        ),
                        getattr(
                            obs,
                            "performing_provider_name",
                            "",
                        ),
                    )
                )

        # FT1-22 Unit Cost
        fields[22] = (
            f"{tx.unit_cost}&USD"
        )

        # FT1-25 Procedure Code
        if cpt:
            fields[25] = _ce(
                cpt,
                description,
                "CPT",
            )

        ft1 = (
            "FT1|"
            + "|".join(fields[1:])
        )

        logger.info(
            "FT1 built",
            extra={
                "extra": {
                    "transaction_id": getattr(
                        tx,
                        "transaction_id",
                        None,
                    ),
                    "amount": getattr(
                        tx,
                        "transaction_amount",
                        None,
                    ),
                    "cpt": cpt,
                    "quantity": getattr(
                        tx,
                        "transaction_quantity",
                        None,
                    ),
                }
            },
        )

        return ft1

    except Exception as e:
        logger.error(
            "Error building FT1",
            extra={
                "extra": {
                    "error": str(e),
                }
            },
        )
        raise


# =========================================================================
# DG1 - Diagnosis
# =========================================================================


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
    Build a DG1 Diagnosis segment.

    DG1-1 Set ID
    DG1-3 Diagnosis Code
    DG1-5 Diagnosis Date/Time
    DG1-6 Diagnosis Type
    """
    try:
        fields = [""] * 7

        # DG1-1 Set ID
        fields[1] = str(
            set_id
        )

        # DG1-3 Diagnosis Code
        if icd_code:
            fields[3] = _ce(
                icd_code,
                desc,
                coding_system,
            )

        # DG1-5 Diagnosis Date/Time
        if diag_dt is None:
            diag_dt = getattr(
                enc,
                "admit_datetime",
                None,
            )

        if diag_dt:
            fields[5] = ts_hl7(
                diag_dt
            )

        # DG1-6 Diagnosis Type
        fields[6] = diag_type

        dg1 = (
            "DG1|"
            + "|".join(fields[1:])
        )

        logger.info(
            "DG1 built",
            extra={
                "extra": {
                    "icd": icd_code,
                    "diag_type": diag_type,
                    "datetime": fields[5],
                }
            },
        )

        return dg1

    except Exception as e:
        logger.error(
            "Error building DG1",
            extra={
                "extra": {
                    "error": str(e),
                }
            },
        )
        raise


# =========================================================================
# Gender Harmony / SPCU OBX helpers
# =========================================================================


_PRODUCER = (
    "MEDILACRAHS^DEPT1"
)


def _obx_cwe(
    *,
    set_id: int,
    obx3: Tuple[str, str, str],
    value: Tuple[str, str, str],
    sub_id: int = 1,
    status: str = "F",
    effective_dt: Optional[str] = None,
    method: Optional[
        Tuple[str, str, str]
    ] = None,
    performing_org: Optional[str] = None,
) -> str:
    """
    Build a generic CWE-valued OBX.

    OBX-1  Set ID
    OBX-2  Value Type
    OBX-3  Observation Identifier
    OBX-4  Observation Sub-ID
    OBX-5  Observation Value
    OBX-11 Result Status
    OBX-14 Date/Time of Observation
    OBX-15 Producer's ID
    OBX-17 Observation Method
    OBX-23 Performing Organization Name
    """
    try:
        fields = [""] * 24

        # OBX-1
        fields[1] = str(
            set_id
        )

        # OBX-2
        fields[2] = "CWE"

        # OBX-3
        fields[3] = _ce(
            obx3[0],
            obx3[1],
            obx3[2],
        )

        # OBX-4
        fields[4] = str(
            sub_id
        )

        # OBX-5
        fields[5] = _ce(
            value[0],
            value[1],
            value[2],
        )

        # OBX-11
        fields[11] = status

        # OBX-14
        if effective_dt:
            fields[14] = ts_hl7(
                effective_dt
            )

        # OBX-15
        fields[15] = _PRODUCER

        # OBX-17
        if method:
            fields[17] = _ce(
                method[0],
                method[1],
                method[2],
            )

        # OBX-23
        if performing_org:
            fields[23] = str(
                performing_org
            )

        obx = (
            "OBX|"
            + "|".join(fields[1:])
        )

        logger.info(
            "OBX built (CWE)",
            extra={
                "extra": {
                    "obx3_code": obx3[0],
                    "value_code": value[0],
                    "set_id": set_id,
                }
            },
        )

        return obx

    except Exception as e:
        logger.error(
            "Error building OBX (CWE)",
            extra={
                "extra": {
                    "error": str(e),
                }
            },
        )
        raise


def seg_obx_gender_identity(
    *,
    set_id: int,
    gi_code: str = (
        "446151000124109"
    ),
    gi_text: str = "Male",
    gi_system: str = "SCT",
    effective_dt: Optional[str] = None,
    method: Optional[
        Tuple[str, str, str]
    ] = None,
    performing_org: Optional[str] = None,
) -> str:
    """
    Build the existing Gender Identity OBX.

    Observation:
        LOINC 76691-5
    """
    try:
        return _obx_cwe(
            set_id=set_id,
            obx3=(
                "76691-5",
                "Gender identity",
                "LN",
            ),
            value=(
                gi_code,
                gi_text,
                gi_system,
            ),
            effective_dt=effective_dt,
            method=method,
            performing_org=performing_org,
        )

    except Exception as e:
        logger.error(
            "Error building GI OBX",
            extra={
                "extra": {
                    "error": str(e),
                }
            },
        )
        raise


def seg_obx_pronouns(
    *,
    set_id: int,
    pronoun_code: str = (
        "LA29520-6"
    ),
    pronoun_text: str = (
        "they/them/their/theirs/"
        "themselves"
    ),
    pronoun_system: str = "LN",
    effective_dt: Optional[str] = None,
    method: Optional[
        Tuple[str, str, str]
    ] = None,
    performing_org: Optional[str] = None,
) -> str:
    """
    Build the existing Personal Pronouns OBX.

    Observation:
        LOINC 90778-2
    """
    try:
        return _obx_cwe(
            set_id=set_id,
            obx3=(
                "90778-2",
                "Personal pronouns - Reported",
                "LN",
            ),
            value=(
                pronoun_code,
                pronoun_text,
                pronoun_system,
            ),
            effective_dt=effective_dt,
            method=method,
            performing_org=performing_org,
        )

    except Exception as e:
        logger.error(
            "Error building Pronouns OBX",
            extra={
                "extra": {
                    "error": str(e),
                }
            },
        )
        raise


def seg_obx_spcu(
    *,
    set_id: int,
    spcu_code: str = "F-T",
    spcu_text: str = (
        "Apply female-typical settings"
    ),
    spcu_system: str = "HL7",
    effective_dt: Optional[str] = None,
    method: Optional[
        Tuple[str, str, str]
    ] = None,
    performing_org: Optional[str] = None,
) -> str:
    """
    Build the existing Sex Parameter for Clinical Use OBX.
    """
    try:
        return _obx_cwe(
            set_id=set_id,
            obx3=(
                "SPCU",
                "Sex parameter for clinical use",
                "HL7",
            ),
            value=(
                spcu_code,
                spcu_text,
                spcu_system,
            ),
            effective_dt=effective_dt,
            method=method,
            performing_org=performing_org,
        )

    except Exception as e:
        logger.error(
            "Error building SPCU OBX",
            extra={
                "extra": {
                    "error": str(e),
                }
            },
        )
        raise
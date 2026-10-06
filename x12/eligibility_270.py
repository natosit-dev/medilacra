from __future__ import annotations

from dataclasses import dataclass

from identity.models import IdentityQuery
from payer.models import EligibilityInquiry

from .models import EligibilityExchange, X12Party
from .parser import first_segment, transaction_segments


IMPLEMENTATION_REFERENCE = "005010X279A1"


@dataclass(frozen=True)
class Parsed270:
    inquiry: EligibilityInquiry
    payer: X12Party
    requester: X12Party
    trace_id: str
    originating_company_id: str
    reference_id: str
    request_control_number: str
    service_type: str


def _to_d8(value: str) -> str:
    compact = str(value).strip().replace("-", "")
    if len(compact) != 8 or not compact.isdigit():
        raise ValueError(f"Expected YYYYMMDD or YYYY-MM-DD date, got {value!r}")
    return compact


def _to_iso_date(value: str) -> str:
    compact = _to_d8(value)
    return f"{compact[:4]}-{compact[4:6]}-{compact[6:8]}"


def _split_clinical_name(value: str) -> tuple[str, str]:
    """
    Split current MediLacra HL7-style patient_name into first/last components.

    The current clinical model stores names as LAST^FIRST.
    """
    parts = (value or "").split("^")
    last_name = parts[0].strip() if parts else ""
    first_name = parts[1].strip() if len(parts) > 1 else ""

    if not first_name or not last_name:
        raise ValueError(
            "Clinical patient_name must contain LAST^FIRST for the X12 MVP"
        )

    return first_name, last_name


def _finish_transaction(
    segments: list[str],
    control_number: str,
) -> str:
    count = len(segments) + 1
    return "~".join(
        segments + [f"SE*{count}*{control_number}"]
    ) + "~"


def build_270_transaction(
    *,
    payer: X12Party,
    requester: X12Party,
    subscriber: IdentityQuery,
    service_date: str,
    exchange: EligibilityExchange,
    service_type: str = "30",
) -> str:
    """
    Build the first subscriber-is-patient 270 transaction set.

    This is an exchange projection only. It contains no payer decision logic.
    """
    if not subscriber.member_id:
        raise ValueError("270 MVP requires subscriber member_id")
    if not subscriber.first_name or not subscriber.last_name:
        raise ValueError("270 MVP requires subscriber first and last name")
    if not subscriber.date_of_birth:
        raise ValueError("270 MVP requires subscriber date_of_birth")

    service_date_d8 = _to_d8(service_date)
    birth_date_d8 = _to_d8(subscriber.date_of_birth)

    segments = [
        (
            f"ST*270*{exchange.request_control_number}*"
            f"{IMPLEMENTATION_REFERENCE}"
        ),
        (
            f"BHT*0022*13*{exchange.reference_id}*"
            f"{exchange.transaction_date}*{exchange.request_time}"
        ),
        "HL*1**20*1",
        (
            f"NM1*PR*2*{payer.name}*****"
            f"{payer.identifier_qualifier}*{payer.identifier}"
        ),
        "HL*2*1*21*1",
        (
            f"NM1*1P*2*{requester.name}*****"
            f"{requester.identifier_qualifier}*{requester.identifier}"
        ),
        "HL*3*2*22*0",
        (
            f"TRN*1*{exchange.trace_id}*"
            f"{exchange.originating_company_id}"
        ),
        (
            f"NM1*IL*1*{subscriber.last_name}*"
            f"{subscriber.first_name}****MI*{subscriber.member_id}"
        ),
        f"DMG*D8*{birth_date_d8}*{subscriber.administrative_sex or ''}",
        f"DTP*291*D8*{service_date_d8}",
        f"EQ*{service_type}",
    ]

    return _finish_transaction(
        segments,
        exchange.request_control_number,
    )


def build_270_from_clinical(
    patient,
    coverage_profile,
    *,
    requester: X12Party,
    service_date: str,
    exchange: EligibilityExchange,
    service_type: str = "30",
) -> str:
    """
    Project current clinical Patient + CoverageProfile knowledge into a 270.

    Duck typing is deliberate: the X12 adapter does not import clinical model
    classes and does not become part of payer operational state.
    """
    first_name, last_name = _split_clinical_name(patient.patient_name)

    payer = X12Party(
        identifier=coverage_profile.payer_id,
        name=coverage_profile.payer_name,
        identifier_qualifier="PI",
    )

    subscriber = IdentityQuery(
        member_id=coverage_profile.member_id,
        first_name=first_name,
        last_name=last_name,
        date_of_birth=_to_iso_date(patient.date_of_birth),
        administrative_sex=patient.sex,
    )

    return build_270_transaction(
        payer=payer,
        requester=requester,
        subscriber=subscriber,
        service_date=service_date,
        exchange=exchange,
        service_type=service_type,
    )


def _first_nm1_by_entity(segments, entity_code: str):
    return next(
        (
            segment
            for segment in segments
            if segment.tag == "NM1"
            and segment.element(1) == entity_code
        ),
        None,
    )


def _first_dtp_by_qualifier(segments, qualifier: str):
    return next(
        (
            segment
            for segment in segments
            if segment.tag == "DTP"
            and segment.element(1) == qualifier
        ),
        None,
    )


def parse_270_to_inquiry(text: str) -> Parsed270:
    """
    Parse the supported subscriber-is-patient 270 into payer semantics.

    Only the first MVP scenario shape is supported. Unsupported or missing
    required elements fail loudly rather than being guessed.
    """
    segments = transaction_segments(text)
    st = first_segment(segments, "ST")

    if st is None or st.element(1) != "270":
        raise ValueError("Expected X12 270 transaction set")

    bht = first_segment(segments, "BHT")
    payer_nm1 = _first_nm1_by_entity(segments, "PR")
    requester_nm1 = _first_nm1_by_entity(segments, "1P")
    subscriber_nm1 = _first_nm1_by_entity(segments, "IL")
    trn = first_segment(segments, "TRN")
    dmg = first_segment(segments, "DMG")
    dtp = _first_dtp_by_qualifier(segments, "291")
    eq = first_segment(segments, "EQ")

    required = {
        "BHT": bht,
        "payer NM1": payer_nm1,
        "requester NM1": requester_nm1,
        "subscriber NM1": subscriber_nm1,
        "TRN": trn,
        "DMG": dmg,
        "DTP*291": dtp,
        "EQ": eq,
    }
    missing = [name for name, segment in required.items() if segment is None]
    if missing:
        raise ValueError(
            "270 MVP missing required segments: " + ", ".join(missing)
        )

    assert bht is not None
    assert payer_nm1 is not None
    assert requester_nm1 is not None
    assert subscriber_nm1 is not None
    assert trn is not None
    assert dmg is not None
    assert dtp is not None
    assert eq is not None

    if dmg.element(1) != "D8" or dtp.element(2) != "D8":
        raise ValueError("270 MVP supports D8 demographic and plan dates only")

    inquiry = EligibilityInquiry(
        payer_id=payer_nm1.element(9),
        requester_id=requester_nm1.element(9),
        member_id=subscriber_nm1.element(9),
        first_name=subscriber_nm1.element(4),
        last_name=subscriber_nm1.element(3),
        date_of_birth=_to_iso_date(dmg.element(2)),
        administrative_sex=dmg.element(3) or None,
        service_date=_to_iso_date(dtp.element(3)),
    )

    return Parsed270(
        inquiry=inquiry,
        payer=X12Party(
            identifier=payer_nm1.element(9),
            name=payer_nm1.element(3),
            identifier_qualifier=payer_nm1.element(8),
        ),
        requester=X12Party(
            identifier=requester_nm1.element(9),
            name=requester_nm1.element(3),
            identifier_qualifier=requester_nm1.element(8),
        ),
        trace_id=trn.element(2),
        originating_company_id=trn.element(3),
        reference_id=bht.element(3),
        request_control_number=st.element(2),
        service_type=eq.element(1),
    )

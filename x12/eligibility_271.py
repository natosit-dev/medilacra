from __future__ import annotations

from dataclasses import dataclass

from payer.models import (
    BenefitPlan,
    EligibilityOutcome,
    EligibilityResponse,
    MemberRecord,
)

from .eligibility_270 import Parsed270, _to_d8, _to_iso_date
from .models import X12Party
from .parser import first_segment, segments_by_tag, transaction_segments


IMPLEMENTATION_REFERENCE = "005010X279A1"

# Public X12 interpretation for a generic EQ*30 request requires plan-level
# active status plus status for these service types. No financial benefit
# details are modeled here.
GENERIC_ACTIVE_SERVICE_TYPES = (
    "1",
    "33",
    "35",
    "47",
    "86",
    "88",
    "98",
    "AL",
    "MH",
    "UC",
)


@dataclass(frozen=True)
class Parsed271:
    trace_id: str
    subscriber_member_id: str
    subscriber_first_name: str
    subscriber_last_name: str
    subscriber_date_of_birth: str
    subscriber_sex: str
    coverage_start: str | None
    coverage_end: str | None
    plan_name: str | None
    group_number: str | None
    active_service_types: tuple[str, ...]


def _finish_transaction(
    segments: list[str],
    control_number: str,
) -> str:
    count = len(segments) + 1
    return "~".join(
        segments + [f"SE*{count}*{control_number}"]
    ) + "~"


def build_271_transaction(
    response: EligibilityResponse,
    *,
    member: MemberRecord,
    plan: BenefitPlan,
    payer: X12Party,
    request: Parsed270,
    response_control_number: str,
    transaction_date: str,
    transaction_time: str,
) -> str:
    """
    Build the active-coverage 271 for the first two MediLacra scenarios.

    Identity comes from payer-held MemberRecord. Clinical Patient and
    CoverageProfile are intentionally unavailable to this function.
    """
    if response.outcome != EligibilityOutcome.ACTIVE:
        raise NotImplementedError(
            "First X12 MVP only projects ACTIVE EligibilityResponse"
        )

    if response.member_record_id != member.member_record_id:
        raise ValueError("EligibilityResponse member does not match MemberRecord")

    if response.plan_id != plan.plan_id:
        raise ValueError("EligibilityResponse plan does not match BenefitPlan")

    segments = [
        (
            f"ST*271*{response_control_number}*"
            f"{IMPLEMENTATION_REFERENCE}"
        ),
        (
            f"BHT*0022*11*{request.reference_id}*"
            f"{transaction_date}*{transaction_time}"
        ),
        "HL*1**20*1",
        (
            f"NM1*PR*2*{payer.name}*****"
            f"{payer.identifier_qualifier}*{payer.identifier}"
        ),
        "HL*2*1*21*1",
        (
            f"NM1*1P*2*{request.requester.name}*****"
            f"{request.requester.identifier_qualifier}*"
            f"{request.requester.identifier}"
        ),
        "HL*3*2*22*0",
        (
            f"TRN*2*{request.trace_id}*"
            f"{request.originating_company_id}"
        ),
        (
            f"NM1*IL*1*{member.last_name}*{member.first_name}****"
            f"MI*{member.member_id}"
        ),
        (
            f"DMG*D8*{_to_d8(member.date_of_birth)}*"
            f"{member.administrative_sex}"
        ),
    ]

    if response.coverage_start:
        segments.append(
            f"DTP*346*D8*{_to_d8(response.coverage_start)}"
        )

    if response.coverage_end:
        segments.append(
            f"DTP*347*D8*{_to_d8(response.coverage_end)}"
        )

    segments.append(
        f"EB*1**30**{plan.plan_name}"
    )

    # A plan-level ACTIVE response cannot establish individual covered services.
    # Emit service-type EB assertions only when the payer plan explicitly owns them.
    if plan.active_service_types:
        segments.append("EB*1**" + ">".join(plan.active_service_types))

    if response.group_number:
        segments.append(
            f"REF*6P*{response.group_number}"
        )

    return _finish_transaction(
        segments,
        response_control_number,
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


def parse_271(text: str) -> Parsed271:
    """Parse the active-coverage subset emitted by build_271_transaction()."""
    segments = transaction_segments(text)
    st = first_segment(segments, "ST")

    if st is None or st.element(1) != "271":
        raise ValueError("Expected X12 271 transaction set")

    subscriber = _first_nm1_by_entity(segments, "IL")
    trn = first_segment(segments, "TRN")
    dmg = first_segment(segments, "DMG")

    if subscriber is None or trn is None or dmg is None:
        raise ValueError("271 MVP missing subscriber, trace, or demographics")

    begin = _first_dtp_by_qualifier(segments, "346")
    end = _first_dtp_by_qualifier(segments, "347")
    eb_segments = segments_by_tag(segments, "EB")
    ref_segments = segments_by_tag(segments, "REF")

    plan_eb = next(
        (
            segment
            for segment in eb_segments
            if segment.element(1) == "1"
            and segment.element(3) == "30"
        ),
        None,
    )

    active_service_types = []
    for segment in eb_segments:
        if segment.element(1) != "1":
            continue
        service_field = segment.element(3)
        if not service_field or service_field == "30":
            continue
        active_service_types.extend(
            item for item in service_field.split(">") if item
        )

    group = next(
        (
            segment.element(2)
            for segment in ref_segments
            if segment.element(1) == "6P"
        ),
        None,
    )

    return Parsed271(
        trace_id=trn.element(2),
        subscriber_member_id=subscriber.element(9),
        subscriber_first_name=subscriber.element(4),
        subscriber_last_name=subscriber.element(3),
        subscriber_date_of_birth=_to_iso_date(dmg.element(2)),
        subscriber_sex=dmg.element(3),
        coverage_start=(
            _to_iso_date(begin.element(3))
            if begin is not None
            else None
        ),
        coverage_end=(
            _to_iso_date(end.element(3))
            if end is not None
            else None
        ),
        plan_name=(
            plan_eb.element(5)
            if plan_eb is not None
            else None
        ),
        group_number=group,
        active_service_types=tuple(active_service_types),
    )

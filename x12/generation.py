from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime

from eligibility.generation import (
    EligibilityExchangeIdentity,
    build_eligibility_inquiry_from_clinical,
)
from identity.models import IdentityQuery
from payer.models import (
    BenefitPlan,
    EligibilityInquiry,
    EligibilityResponse,
    MemberRecord,
)
from payer.system import PayerSystem

from .eligibility_270 import (
    Parsed270,
    build_270_transaction,
    parse_270_to_inquiry,
)
from .eligibility_271 import build_271_transaction
from .envelope import EnvelopeConfig, wrap_interchange
from .models import EligibilityExchange, X12Party


@dataclass(frozen=True)
class X12ControlSet:
    exchange_sequence: int
    trace_id: str
    reference_id: str
    request_control: str
    response_control: str


@dataclass
class X12RunContext:
    """
    Run-scoped X12 control allocator.

    X12 control fields are capped at 9 digits in this MVP. We use the run's
    HHMM timestamp prefix plus a five-digit monotonic message sequence.
    Human-readable trace/reference IDs retain the full run timestamp plus a
    five-digit exchange sequence.
    """

    run_at: datetime
    exchange_sequence: int = 0
    control_sequence: int = 0

    @property
    def run_stamp(self) -> str:
        return self.run_at.strftime("%Y%m%d%H%M%S")

    @property
    def file_stamp(self) -> str:
        return self.run_at.strftime("%Y%m%d_%H%M%S")

    @property
    def control_prefix(self) -> str:
        return self.run_at.strftime("%H%M")

    def _next_control(self) -> str:
        self.control_sequence += 1
        if self.control_sequence > 99999:
            raise ValueError(
                "X12RunContext exhausted five-digit control sequence"
            )
        return (
            f"{self.control_prefix}"
            f"{self.control_sequence:05d}"
        )

    def next_exchange(self) -> X12ControlSet:
        self.exchange_sequence += 1
        if self.exchange_sequence > 99999:
            raise ValueError(
                "X12RunContext exhausted five-digit exchange sequence"
            )

        exchange_suffix = f"{self.exchange_sequence:05d}"

        return X12ControlSet(
            exchange_sequence=self.exchange_sequence,
            trace_id=(
                f"TRACE-270-{self.run_stamp}-{exchange_suffix}"
            ),
            reference_id=(
                f"ELIG-REQ-{self.run_stamp}-{exchange_suffix}"
            ),
            request_control=self._next_control(),
            response_control=self._next_control(),
        )


@dataclass(frozen=True)
class X12EligibilityArtifacts:
    encounter_id: str
    payer_id: str
    member_id: str
    service_date: str
    trace_id: str
    request_transaction_control: str
    response_transaction_control: str
    request_interchange_control: str
    response_interchange_control: str
    response: EligibilityResponse
    parsed_270: Parsed270
    x270: str
    x271: str


DEFAULT_REQUESTER = X12Party(
    identifier="MEDILACRA01",
    name="MEDILACRA CLINIC",
    identifier_qualifier="SV",
)


def _service_date_from_encounter(encounter) -> str:
    raw = str(encounter.admit_datetime).strip()
    if len(raw) < 10:
        raise ValueError(
            "Encounter admit_datetime must contain a date"
        )
    return raw[:10]


def _subscriber_from_inquiry(
    inquiry: EligibilityInquiry,
) -> IdentityQuery:
    return IdentityQuery(
        member_id=inquiry.member_id,
        first_name=inquiry.first_name,
        last_name=inquiry.last_name,
        date_of_birth=inquiry.date_of_birth,
        administrative_sex=inquiry.administrative_sex,
    )


def _render_x12_eligibility(
    *,
    inquiry: EligibilityInquiry,
    response: EligibilityResponse,
    exchange_identity: EligibilityExchangeIdentity,
    encounter_id: str,
    coverage_profile,
    payer_member: MemberRecord,
    payer_plan: BenefitPlan,
    controls: X12ControlSet,
    run_at: datetime,
    requester: X12Party,
) -> X12EligibilityArtifacts:
    exchange = EligibilityExchange(
        trace_id=exchange_identity.trace_id,
        originating_company_id="MEDILACRA-CLINIC",
        reference_id=exchange_identity.reference_id,
        request_control_number=controls.request_control,
        response_control_number=controls.response_control,
        transaction_date=run_at.strftime("%Y%m%d"),
        request_time=run_at.strftime("%H%M%S"),
        response_time=run_at.strftime("%H%M%S"),
    )

    payer_party = X12Party(
        identifier=str(coverage_profile.payer_id),
        name=str(coverage_profile.payer_name).upper(),
        identifier_qualifier="PI",
    )

    x270_transaction = build_270_transaction(
        payer=payer_party,
        requester=requester,
        subscriber=_subscriber_from_inquiry(inquiry),
        service_date=inquiry.service_date,
        exchange=exchange,
        service_type=inquiry.service_type,
    )

    x270 = wrap_interchange(
        x270_transaction,
        config=EnvelopeConfig(
            sender_id="MEDILACRA",
            receiver_id=coverage_profile.payer_id,
            interchange_control_number=controls.request_control,
            group_control_number=controls.request_control,
            interchange_date=run_at.strftime("%y%m%d"),
            interchange_time=run_at.strftime("%H%M"),
            group_date=run_at.strftime("%Y%m%d"),
            group_time=run_at.strftime("%H%M%S"),
        ),
    )

    # Parsing remains inside the X12 adapter only to provide the request
    # transport/correlation context expected by the 271 renderer. The payer
    # decision has already been made from the shared semantic inquiry.
    parsed_270 = parse_270_to_inquiry(x270)

    x271_transaction = build_271_transaction(
        response,
        member=payer_member,
        plan=payer_plan,
        payer=payer_party,
        request=parsed_270,
        response_control_number=controls.response_control,
        transaction_date=run_at.strftime("%Y%m%d"),
        transaction_time=run_at.strftime("%H%M%S"),
    )

    x271 = wrap_interchange(
        x271_transaction,
        config=EnvelopeConfig(
            sender_id=coverage_profile.payer_id,
            receiver_id="MEDILACRA",
            interchange_control_number=controls.response_control,
            group_control_number=controls.response_control,
            interchange_date=run_at.strftime("%y%m%d"),
            interchange_time=run_at.strftime("%H%M"),
            group_date=run_at.strftime("%Y%m%d"),
            group_time=run_at.strftime("%H%M%S"),
        ),
    )

    return X12EligibilityArtifacts(
        encounter_id=str(encounter_id),
        payer_id=str(coverage_profile.payer_id),
        member_id=str(coverage_profile.member_id),
        service_date=str(inquiry.service_date),
        trace_id=exchange_identity.trace_id,
        request_transaction_control=controls.request_control,
        response_transaction_control=controls.response_control,
        request_interchange_control=controls.request_control,
        response_interchange_control=controls.response_control,
        response=response,
        parsed_270=parsed_270,
        x270=x270,
        x271=x271,
    )


def generate_x12_eligibility_artifacts(
    *,
    inquiry: EligibilityInquiry,
    response: EligibilityResponse,
    exchange_identity: EligibilityExchangeIdentity,
    encounter_id: str,
    coverage_profile,
    payer_member: MemberRecord,
    payer_plan: BenefitPlan,
    run_context: X12RunContext,
    requester: X12Party = DEFAULT_REQUESTER,
) -> X12EligibilityArtifacts:
    """
    Project an already-materialized semantic eligibility exchange into X12.

    No payer decision is made here.
    """
    controls = run_context.next_exchange()
    return _render_x12_eligibility(
        inquiry=inquiry,
        response=response,
        exchange_identity=exchange_identity,
        encounter_id=encounter_id,
        coverage_profile=coverage_profile,
        payer_member=payer_member,
        payer_plan=payer_plan,
        controls=controls,
        run_at=run_context.run_at,
        requester=requester,
    )


def generate_eligibility_exchange(
    *,
    patient,
    coverage_profile,
    encounter,
    payer_system: PayerSystem,
    payer_member: MemberRecord,
    payer_plan: BenefitPlan,
    run_context: X12RunContext,
    requester: X12Party = DEFAULT_REQUESTER,
) -> X12EligibilityArtifacts:
    """
    Backward-compatible convenience wrapper used by the single-exchange UI.

    New scaled generation builds the semantic inquiry/response before calling
    generate_x12_eligibility_artifacts().
    """
    controls = run_context.next_exchange()
    inquiry = build_eligibility_inquiry_from_clinical(
        patient,
        coverage_profile,
        encounter,
        requester_id=requester.identifier,
    )
    response = payer_system.evaluate_eligibility(inquiry)

    suffix = f"{controls.exchange_sequence:05d}"
    exchange_id = f"{run_context.run_stamp}-{suffix}"
    exchange_identity = EligibilityExchangeIdentity(
        exchange_sequence=controls.exchange_sequence,
        exchange_id=exchange_id,
        trace_id=f"TRACE-270-{exchange_id}",
        reference_id=f"ELIG-REQ-{exchange_id}",
    )

    return _render_x12_eligibility(
        inquiry=inquiry,
        response=response,
        exchange_identity=exchange_identity,
        encounter_id=str(encounter.encounter_id),
        coverage_profile=coverage_profile,
        payer_member=payer_member,
        payer_plan=payer_plan,
        controls=controls,
        run_at=run_context.run_at,
        requester=requester,
    )


def write_x12_artifacts(
    artifacts: X12EligibilityArtifacts,
    *,
    out_dir: str,
    run_ts: str,
    per_encounter: bool,
    safe_encounter: str,
) -> dict[str, str]:
    """
    Write one eligibility pair.

    Bulk mode appends complete ISA..IEA interchanges to one 270 file and one
    271 file. Per-encounter mode writes one pair of files per encounter.
    """
    os.makedirs(out_dir, exist_ok=True)

    if per_encounter:
        paths = {
            "X12_270": os.path.join(
                out_dir,
                f"X12_270_{safe_encounter}_{run_ts}.x12",
            ),
            "X12_271": os.path.join(
                out_dir,
                f"X12_271_{safe_encounter}_{run_ts}.x12",
            ),
        }
        payloads = {
            "X12_270": artifacts.x270,
            "X12_271": artifacts.x271,
        }

        for name, path in paths.items():
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(payloads[name])

        return paths

    paths = {
        "X12_270": os.path.join(
            out_dir,
            f"X12_270_{run_ts}.x12",
        ),
        "X12_271": os.path.join(
            out_dir,
            f"X12_271_{run_ts}.x12",
        ),
    }
    payloads = {
        "X12_270": artifacts.x270,
        "X12_271": artifacts.x271,
    }

    for name, path in paths.items():
        mode = "a" if os.path.exists(path) else "w"
        with open(path, mode, encoding="utf-8") as handle:
            if mode == "a":
                handle.write("\n\n")
            handle.write(payloads[name])

    return paths

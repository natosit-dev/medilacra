from __future__ import annotations

from datetime import date

from identity.matcher import match_identity
from identity.models import IdentityCandidate, IdentityQuery, MatchOutcome, MatchResult

from .models import (
    BenefitPlan,
    EligibilityInquiry,
    EligibilityOutcome,
    EligibilityResponse,
    EnrollmentRecord,
    EnrollmentStatus,
    MemberRecord,
)


class PayerSystem:
    """
    In-memory synthetic payer engine.

    It owns payer-local member, enrollment, and plan state. It deliberately has
    no dependency on clinical Patient/CoverageProfile models or GroundTruthLink.
    """

    def __init__(
        self,
        payer_id: str,
        *,
        members: list[MemberRecord] | None = None,
        enrollments: list[EnrollmentRecord] | None = None,
        plans: list[BenefitPlan] | None = None,
    ) -> None:
        self.payer_id = payer_id
        self.members = {
            record.member_record_id: record for record in (members or [])
        }
        self.enrollments = {
            record.enrollment_id: record for record in (enrollments or [])
        }
        self.plans = {
            record.plan_id: record for record in (plans or [])
        }

    def add_member(self, record: MemberRecord) -> None:
        self._require_payer(record.payer_id)
        self.members[record.member_record_id] = record

    def add_enrollment(self, record: EnrollmentRecord) -> None:
        self._require_payer(record.payer_id)
        self.enrollments[record.enrollment_id] = record

    def add_plan(self, record: BenefitPlan) -> None:
        self._require_payer(record.payer_id)
        self.plans[record.plan_id] = record

    def _require_payer(self, payer_id: str) -> None:
        if payer_id != self.payer_id:
            raise ValueError(
                f"Record payer_id {payer_id!r} does not belong to "
                f"PayerSystem {self.payer_id!r}"
            )

    def _identity_candidates(self) -> tuple[IdentityCandidate, ...]:
        return tuple(
            IdentityCandidate(
                candidate_id=record.member_record_id,
                member_id=record.member_id,
                first_name=record.first_name,
                last_name=record.last_name,
                date_of_birth=record.date_of_birth,
                administrative_sex=record.administrative_sex,
            )
            for record in self.members.values()
            if record.payer_id == self.payer_id
        )

    def resolve_member(self, query: IdentityQuery) -> MatchResult:
        return match_identity(query, self._identity_candidates())

    @staticmethod
    def _parse_date(value: str) -> date:
        return date.fromisoformat(value)

    def _response_from_match(
        self,
        match: MatchResult,
        outcome: EligibilityOutcome,
        *,
        errors: tuple[str, ...] = (),
    ) -> EligibilityResponse:
        return EligibilityResponse(
            outcome=outcome,
            matched_fields=match.matched_fields,
            conflicting_fields=match.conflicting_fields,
            errors=errors,
        )

    def evaluate_eligibility(
        self,
        inquiry: EligibilityInquiry,
    ) -> EligibilityResponse:
        if inquiry.payer_id != self.payer_id:
            return EligibilityResponse(
                outcome=EligibilityOutcome.CANNOT_DETERMINE,
                errors=("payer_mismatch",),
            )

        try:
            service_date = self._parse_date(inquiry.service_date)
        except ValueError:
            return EligibilityResponse(
                outcome=EligibilityOutcome.CANNOT_DETERMINE,
                errors=("invalid_service_date",),
            )

        match = self.resolve_member(
            IdentityQuery(
                member_id=inquiry.member_id,
                first_name=inquiry.first_name,
                last_name=inquiry.last_name,
                date_of_birth=inquiry.date_of_birth,
                administrative_sex=inquiry.administrative_sex,
            )
        )

        if match.outcome == MatchOutcome.NOT_FOUND:
            return self._response_from_match(
                match,
                EligibilityOutcome.NOT_FOUND,
            )

        if match.outcome == MatchOutcome.AMBIGUOUS:
            return self._response_from_match(
                match,
                EligibilityOutcome.AMBIGUOUS,
            )

        member_record_id = match.matched_candidate_id
        if member_record_id is None:
            return self._response_from_match(
                match,
                EligibilityOutcome.CANNOT_DETERMINE,
                errors=("match_without_single_candidate",),
            )

        member_enrollments = sorted(
            (
                record
                for record in self.enrollments.values()
                if record.member_record_id == member_record_id
                and record.payer_id == self.payer_id
            ),
            key=lambda record: (
                record.effective_start,
                record.effective_end,
                record.enrollment_id,
            ),
        )

        if not member_enrollments:
            return EligibilityResponse(
                outcome=EligibilityOutcome.CANNOT_DETERMINE,
                member_record_id=member_record_id,
                matched_fields=match.matched_fields,
                conflicting_fields=match.conflicting_fields,
                errors=("no_enrollment",),
            )

        dated = []
        for enrollment in member_enrollments:
            try:
                start = self._parse_date(enrollment.effective_start)
                end = self._parse_date(enrollment.effective_end)
            except ValueError:
                continue
            dated.append((enrollment, start, end))

        if not dated:
            return EligibilityResponse(
                outcome=EligibilityOutcome.CANNOT_DETERMINE,
                member_record_id=member_record_id,
                matched_fields=match.matched_fields,
                conflicting_fields=match.conflicting_fields,
                errors=("invalid_enrollment_period",),
            )

        active = next(
            (
                enrollment
                for enrollment, start, end in dated
                if enrollment.status == EnrollmentStatus.ACTIVE
                and start <= service_date <= end
            ),
            None,
        )

        if active is not None:
            return EligibilityResponse(
                outcome=EligibilityOutcome.ACTIVE,
                member_record_id=member_record_id,
                enrollment_status=active.status,
                plan_id=active.plan_id,
                group_number=active.group_number,
                coverage_start=active.effective_start,
                coverage_end=active.effective_end,
                matched_fields=match.matched_fields,
                conflicting_fields=match.conflicting_fields,
            )

        # Preserve one payer-held enrollment as context for an inactive answer.
        enrollment = dated[0][0]
        return EligibilityResponse(
            outcome=EligibilityOutcome.INACTIVE,
            member_record_id=member_record_id,
            enrollment_status=enrollment.status,
            plan_id=enrollment.plan_id,
            group_number=enrollment.group_number,
            coverage_start=enrollment.effective_start,
            coverage_end=enrollment.effective_end,
            matched_fields=match.matched_fields,
            conflicting_fields=match.conflicting_fields,
        )

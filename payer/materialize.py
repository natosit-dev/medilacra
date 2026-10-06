from __future__ import annotations

import hashlib

from reality.models import CoverageTruth, GroundTruthLink, PersonTruth

from .models import BenefitPlan, EnrollmentRecord, EnrollmentStatus, MemberRecord


def _stable_id(prefix: str, *parts: str) -> str:
    material = "|".join(parts).encode("utf-8")
    digest = hashlib.sha256(material).hexdigest()[:16].upper()
    return f"{prefix}-{digest}"


def materialize_payer_state(
    person_truth: PersonTruth,
    coverage_truth: CoverageTruth,
    *,
    plan_name: str,
    plan_type: str,
    clinical_patient_id: str | None = None,
    clinical_coverage_profile_id: str | None = None,
) -> tuple[MemberRecord, EnrollmentRecord, BenefitPlan, GroundTruthLink]:
    """
    Materialize independent payer-local state from hidden simulation truth.

    The returned payer records contain copied primitive values only. They do not
    reference clinical Patient/CoverageProfile objects or GroundTruthLink.
    """
    if coverage_truth.truth_person_id != person_truth.truth_person_id:
        raise ValueError(
            "CoverageTruth.truth_person_id must match PersonTruth.truth_person_id"
        )

    member_record = MemberRecord(
        member_record_id=_stable_id(
            "PM",
            coverage_truth.payer_id,
            person_truth.truth_person_id,
            coverage_truth.member_id,
        ),
        payer_id=coverage_truth.payer_id,
        member_id=coverage_truth.member_id,
        first_name=person_truth.first_name,
        last_name=person_truth.last_name,
        date_of_birth=person_truth.date_of_birth,
        administrative_sex=person_truth.administrative_sex,
    )

    enrollment = EnrollmentRecord(
        enrollment_id=_stable_id(
            "PE",
            coverage_truth.payer_id,
            coverage_truth.truth_coverage_id,
            coverage_truth.member_id,
        ),
        member_record_id=member_record.member_record_id,
        payer_id=coverage_truth.payer_id,
        plan_id=coverage_truth.plan_id,
        group_number=coverage_truth.group_number,
        effective_start=coverage_truth.effective_start,
        effective_end=coverage_truth.effective_end,
        status=EnrollmentStatus.ACTIVE,
    )

    plan = BenefitPlan(
        plan_id=coverage_truth.plan_id,
        payer_id=coverage_truth.payer_id,
        plan_name=plan_name,
        plan_type=plan_type,
    )

    oracle_link = GroundTruthLink(
        truth_person_id=person_truth.truth_person_id,
        truth_coverage_id=coverage_truth.truth_coverage_id,
        clinical_patient_id=clinical_patient_id,
        clinical_coverage_profile_id=clinical_coverage_profile_id,
        payer_member_record_id=member_record.member_record_id,
        payer_enrollment_id=enrollment.enrollment_id,
    )

    return member_record, enrollment, plan, oracle_link

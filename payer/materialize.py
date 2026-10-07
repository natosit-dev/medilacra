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


def _split_clinical_patient_name(value: str) -> tuple[str, str]:
    """Return first_name, last_name from current MediLacra Patient naming."""
    raw = (value or "").strip()

    if "^" in raw:
        last_name, first_name = [
            part.strip()
            for part in raw.split("^", 1)
        ]
    elif "," in raw:
        last_name, first_name = [
            part.strip()
            for part in raw.split(",", 1)
        ]
    else:
        raise ValueError(
            "Patient.patient_name must contain LAST, FIRST or LAST^FIRST"
        )

    if not first_name or not last_name:
        raise ValueError(
            "Patient.patient_name must contain both last and first name"
        )

    return first_name, last_name


def materialize_payer_from_clinical(
    patient,
    coverage_profile,
) -> tuple[MemberRecord, EnrollmentRecord, BenefitPlan]:
    """
    Materialize normal payer-local state from generated clinical-side state.

    This helper keeps hidden truth/oracle mechanics out of run_pipeline().
    The returned payer records contain copied primitive values and no clinical
    object references.
    """
    first_name, last_name = _split_clinical_patient_name(
        patient.patient_name
    )

    person_truth = PersonTruth(
        truth_person_id=f"TRUTH-{patient.patient_id}",
        first_name=first_name,
        last_name=last_name,
        date_of_birth=str(patient.date_of_birth),
        administrative_sex=str(patient.sex),
        address=str(getattr(patient, "address", "") or ""),
        phone=str(getattr(patient, "phone", "") or ""),
    )

    coverage_truth = CoverageTruth(
        truth_coverage_id=(
            f"TRUTH-{coverage_profile.coverage_profile_id}"
        ),
        truth_person_id=person_truth.truth_person_id,
        payer_id=str(coverage_profile.payer_id),
        employer_id=str(coverage_profile.employer_id),
        plan_id=str(coverage_profile.plan_id),
        group_number=str(coverage_profile.group_number),
        member_id=str(coverage_profile.member_id),
        effective_start=str(coverage_profile.effective_start),
        effective_end=str(coverage_profile.effective_end),
    )

    member, enrollment, plan, _oracle_link = materialize_payer_state(
        person_truth,
        coverage_truth,
        plan_name=str(coverage_profile.plan_name),
        plan_type=str(coverage_profile.plan_type),
        clinical_patient_id=str(patient.patient_id),
        clinical_coverage_profile_id=str(
            coverage_profile.coverage_profile_id
        ),
    )

    return member, enrollment, plan

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PersonTruth:
    """
    Hidden synthetic-world person identity.

    This is oracle/generation state, not a clinical Patient or payer member.
    Operational institutional engines must not receive this object.
    """

    truth_person_id: str
    first_name: str
    last_name: str
    date_of_birth: str
    administrative_sex: str
    address: str = ""
    phone: str = ""


@dataclass(frozen=True)
class CoverageTruth:
    """
    Hidden synthetic-world coverage fact.

    Clinical CoverageProfile and payer EnrollmentRecord are independent
    institutional materializations of this truth.
    """

    truth_coverage_id: str
    truth_person_id: str
    payer_id: str
    employer_id: str
    plan_id: str
    group_number: str
    member_id: str
    effective_start: str
    effective_end: str


@dataclass(frozen=True)
class GroundTruthLink:
    """
    Oracle-only correspondence across institutional records.

    This object exists for generation and validation. It must never be passed
    into payer matching or eligibility evaluation.
    """

    truth_person_id: str
    truth_coverage_id: str | None = None
    clinical_patient_id: str | None = None
    clinical_coverage_profile_id: str | None = None
    payer_member_record_id: str | None = None
    payer_enrollment_id: str | None = None

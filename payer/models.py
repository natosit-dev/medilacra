from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class EnrollmentStatus(str, Enum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"


class EligibilityOutcome(str, Enum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    NOT_FOUND = "NOT_FOUND"
    AMBIGUOUS = "AMBIGUOUS"
    CANNOT_DETERMINE = "CANNOT_DETERMINE"


@dataclass(frozen=True)
class MemberRecord:
    member_record_id: str
    payer_id: str
    member_id: str
    first_name: str
    last_name: str
    date_of_birth: str
    administrative_sex: str


@dataclass(frozen=True)
class EnrollmentRecord:
    enrollment_id: str
    member_record_id: str
    payer_id: str
    plan_id: str
    group_number: str
    effective_start: str
    effective_end: str
    status: EnrollmentStatus = EnrollmentStatus.ACTIVE


@dataclass(frozen=True)
class BenefitPlan:
    plan_id: str
    payer_id: str
    plan_name: str
    plan_type: str


@dataclass(frozen=True)
class EligibilityInquiry:
    payer_id: str
    service_date: str
    requester_id: str | None = None
    member_id: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    date_of_birth: str | None = None
    administrative_sex: str | None = None


@dataclass(frozen=True)
class EligibilityResponse:
    outcome: EligibilityOutcome
    member_record_id: str | None = None
    enrollment_status: EnrollmentStatus | None = None
    plan_id: str | None = None
    group_number: str | None = None
    coverage_start: str | None = None
    coverage_end: str | None = None
    matched_fields: tuple[str, ...] = ()
    conflicting_fields: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()

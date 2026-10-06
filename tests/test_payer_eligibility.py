from dataclasses import replace

from payer.materialize import materialize_payer_state
from payer.models import (
    EligibilityInquiry,
    EligibilityOutcome,
    EnrollmentStatus,
)
from payer.system import PayerSystem
from reality.models import CoverageTruth, PersonTruth


def _payer_fixture():
    person = PersonTruth(
        truth_person_id="PERSON-001",
        first_name="Devin",
        last_name="Kelley",
        date_of_birth="1949-01-16",
        administrative_sex="M",
    )
    coverage = CoverageTruth(
        truth_coverage_id="COVERAGE-001",
        truth_person_id=person.truth_person_id,
        payer_id="KAISER",
        employer_id="CVS",
        plan_id="STANDARD_PPO",
        group_number="GRP-CVS-398915",
        member_id="MEM-01374522",
        effective_start="2026-01-01",
        effective_end="2026-12-31",
    )
    member, enrollment, plan, oracle_link = materialize_payer_state(
        person,
        coverage,
        plan_name="Standard PPO",
        plan_type="PPO",
    )
    return person, coverage, member, enrollment, plan, oracle_link


def _inquiry(**overrides):
    values = {
        "payer_id": "KAISER",
        "service_date": "2026-10-04",
        "member_id": "MEM-01374522",
        "first_name": "Devin",
        "last_name": "Kelley",
        "date_of_birth": "1949-01-16",
        "administrative_sex": "M",
    }
    values.update(overrides)
    return EligibilityInquiry(**values)


def test_active_member_returns_active_eligibility():
    _, _, member, enrollment, plan, _ = _payer_fixture()
    system = PayerSystem(
        "KAISER",
        members=[member],
        enrollments=[enrollment],
        plans=[plan],
    )

    response = system.evaluate_eligibility(_inquiry())

    assert response.outcome == EligibilityOutcome.ACTIVE
    assert response.member_record_id == member.member_record_id
    assert response.enrollment_status == EnrollmentStatus.ACTIVE
    assert response.plan_id == "STANDARD_PPO"
    assert response.group_number == "GRP-CVS-398915"
    assert response.coverage_start == "2026-01-01"
    assert response.coverage_end == "2026-12-31"
    assert response.conflicting_fields == ()


def test_out_of_period_service_date_returns_inactive():
    _, _, member, enrollment, plan, _ = _payer_fixture()
    system = PayerSystem(
        "KAISER",
        members=[member],
        enrollments=[enrollment],
        plans=[plan],
    )

    response = system.evaluate_eligibility(
        _inquiry(service_date="2027-01-01")
    )

    assert response.outcome == EligibilityOutcome.INACTIVE
    assert response.member_record_id == member.member_record_id
    assert response.plan_id == "STANDARD_PPO"


def test_inactive_enrollment_returns_inactive():
    _, _, member, enrollment, plan, _ = _payer_fixture()
    inactive = replace(enrollment, status=EnrollmentStatus.INACTIVE)
    system = PayerSystem(
        "KAISER",
        members=[member],
        enrollments=[inactive],
        plans=[plan],
    )

    response = system.evaluate_eligibility(_inquiry())

    assert response.outcome == EligibilityOutcome.INACTIVE
    assert response.enrollment_status == EnrollmentStatus.INACTIVE


def test_matched_member_without_enrollment_cannot_determine():
    _, _, member, _, plan, _ = _payer_fixture()
    system = PayerSystem(
        "KAISER",
        members=[member],
        plans=[plan],
    )

    response = system.evaluate_eligibility(_inquiry())

    assert response.outcome == EligibilityOutcome.CANNOT_DETERMINE
    assert response.member_record_id == member.member_record_id
    assert response.errors == ("no_enrollment",)


def test_unknown_member_propagates_not_found():
    _, _, member, enrollment, plan, _ = _payer_fixture()
    system = PayerSystem(
        "KAISER",
        members=[member],
        enrollments=[enrollment],
        plans=[plan],
    )

    response = system.evaluate_eligibility(
        _inquiry(member_id="MEM-UNKNOWN")
    )

    assert response.outcome == EligibilityOutcome.NOT_FOUND


def test_ambiguous_member_propagates_ambiguous():
    _, _, member, enrollment, plan, _ = _payer_fixture()
    duplicate = replace(
        member,
        member_record_id="PM-DUPLICATE",
    )
    system = PayerSystem(
        "KAISER",
        members=[member, duplicate],
        enrollments=[enrollment],
        plans=[plan],
    )

    response = system.evaluate_eligibility(_inquiry())

    assert response.outcome == EligibilityOutcome.AMBIGUOUS
    assert response.member_record_id is None


def test_demographic_conflict_is_preserved_in_active_response():
    _, _, member, enrollment, plan, _ = _payer_fixture()
    payer_version = replace(member, last_name="Kelly")
    system = PayerSystem(
        "KAISER",
        members=[payer_version],
        enrollments=[enrollment],
        plans=[plan],
    )

    response = system.evaluate_eligibility(_inquiry())

    assert response.outcome == EligibilityOutcome.ACTIVE
    assert "last_name" in response.conflicting_fields


def test_wrong_payer_cannot_query_another_payer_state():
    _, _, member, enrollment, plan, _ = _payer_fixture()
    system = PayerSystem(
        "KAISER",
        members=[member],
        enrollments=[enrollment],
        plans=[plan],
    )

    response = system.evaluate_eligibility(
        _inquiry(payer_id="AETNA")
    )

    assert response.outcome == EligibilityOutcome.CANNOT_DETERMINE
    assert response.member_record_id is None
    assert response.errors == ("payer_mismatch",)


def test_invalid_service_date_cannot_determine():
    _, _, member, enrollment, plan, _ = _payer_fixture()
    system = PayerSystem(
        "KAISER",
        members=[member],
        enrollments=[enrollment],
        plans=[plan],
    )

    response = system.evaluate_eligibility(
        _inquiry(service_date="not-a-date")
    )

    assert response.outcome == EligibilityOutcome.CANNOT_DETERMINE
    assert response.errors == ("invalid_service_date",)

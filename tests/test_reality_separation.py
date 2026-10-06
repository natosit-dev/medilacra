from dataclasses import fields

from hl7_demo.models import Patient
from payer.materialize import materialize_payer_state
from payer.models import EnrollmentRecord, MemberRecord
from payer.system import PayerSystem
from reality.models import CoverageTruth, PersonTruth


def _truth():
    person = PersonTruth(
        truth_person_id="PERSON-001",
        first_name="Devin",
        last_name="Kelley",
        date_of_birth="1949-01-16",
        administrative_sex="M",
        address="224 Stevens Mall",
        phone="869-923-4470",
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
    return person, coverage


def _clinical_patient():
    return Patient(
        patient_id="RAD1054994",
        patient_name="KELLEY^DEVIN",
        date_of_birth="19490116",
        sex="M",
        gender="",
        race="Asian",
        ethnicity="Hispanic or Latino",
        marital_status="M",
        language="en",
        employer="CVS Health Corporation",
        ssn="331-20-5428",
        address="224 Stevens Mall",
        phone="869-923-4470",
        email="devin.kelley@fakermail.com",
        zip_code="53002",
        city="Allenton",
        state="WI",
    )


def test_payer_primitives_do_not_contain_clinical_foreign_keys():
    member_fields = {field.name for field in fields(MemberRecord)}
    enrollment_fields = {field.name for field in fields(EnrollmentRecord)}

    assert "patient_id" not in member_fields
    assert "clinical_patient_id" not in member_fields
    assert "coverage_profile_id" not in member_fields

    assert "patient_id" not in enrollment_fields
    assert "clinical_patient_id" not in enrollment_fields
    assert "coverage_profile_id" not in enrollment_fields


def test_payer_system_operational_module_has_no_clinical_or_oracle_objects():
    import payer.system as payer_system_module

    assert not hasattr(payer_system_module, "Patient")
    assert not hasattr(payer_system_module, "CoverageProfile")
    assert not hasattr(payer_system_module, "GroundTruthLink")


def test_materialization_creates_independent_payer_state_and_oracle_link():
    person, coverage = _truth()
    clinical_patient = _clinical_patient()

    member, enrollment, plan, oracle_link = materialize_payer_state(
        person,
        coverage,
        plan_name="Standard PPO",
        plan_type="PPO",
        clinical_patient_id=clinical_patient.patient_id,
        clinical_coverage_profile_id="COV-CLINICAL-001",
    )

    assert member.member_id == "MEM-01374522"
    assert member.last_name == "Kelley"
    assert enrollment.member_record_id == member.member_record_id
    assert enrollment.plan_id == "STANDARD_PPO"
    assert plan.payer_id == "KAISER"

    assert oracle_link.clinical_patient_id == "RAD1054994"
    assert oracle_link.payer_member_record_id == member.member_record_id

    # Clinical state can diverge after payer materialization without mutating
    # payer-held state.
    clinical_patient.patient_name = "KELLY^DEVIN"
    clinical_patient.employer = "Different Employer"

    assert member.last_name == "Kelley"
    assert member.member_id == "MEM-01374522"
    assert enrollment.group_number == "GRP-CVS-398915"


def test_materializer_rejects_truth_objects_for_different_people():
    person, coverage = _truth()
    wrong_coverage = CoverageTruth(
        truth_coverage_id=coverage.truth_coverage_id,
        truth_person_id="PERSON-OTHER",
        payer_id=coverage.payer_id,
        employer_id=coverage.employer_id,
        plan_id=coverage.plan_id,
        group_number=coverage.group_number,
        member_id=coverage.member_id,
        effective_start=coverage.effective_start,
        effective_end=coverage.effective_end,
    )

    try:
        materialize_payer_state(
            person,
            wrong_coverage,
            plan_name="Standard PPO",
            plan_type="PPO",
        )
    except ValueError as exc:
        assert "truth_person_id" in str(exc)
    else:
        raise AssertionError("Expected mismatched truth identities to fail")


def test_payer_system_accepts_only_its_own_payer_records():
    person, coverage = _truth()
    member, enrollment, plan, _ = materialize_payer_state(
        person,
        coverage,
        plan_name="Standard PPO",
        plan_type="PPO",
    )

    system = PayerSystem("KAISER")
    system.add_member(member)
    system.add_enrollment(enrollment)
    system.add_plan(plan)

    assert list(system.members) == [member.member_record_id]

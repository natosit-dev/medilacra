from datetime import datetime
from types import SimpleNamespace

from hl7_demo.models import CoverageProfile, Patient
from payer.materialize import materialize_payer_from_clinical
from payer.models import EligibilityOutcome
from payer.system import PayerSystem
from x12.eligibility_270 import (
    _normalize_clinical_name,
    parse_270_to_inquiry,
)
from x12.generation import (
    X12RunContext,
    generate_eligibility_exchange,
    write_x12_artifacts,
)


def _patient(name="KELLEY, DEVIN"):
    return Patient(
        patient_id="RAD1054994",
        patient_name=name,
        date_of_birth="1949-01-16",
        sex="M",
        gender="Man",
        race="Other",
        ethnicity="Not Hispanic or Latino",
        marital_status="Single",
        language="English",
        employer="CVS Health Corporation",
        ssn="000-00-0000",
        address="100 Synthetic Way",
        phone="555-0100",
        email="devin.kelley@example.invalid",
        zip_code="01852",
        city="Lowell",
        state="MA",
    )


def _coverage(patient_id="RAD1054994"):
    return CoverageProfile(
        coverage_profile_id="COV-SCALED-001",
        patient_id=patient_id,
        employer_id="CVS",
        employer_name="CVS Health Corporation",
        payer_id="KAISER",
        payer_name="Kaiser Permanente",
        plan_id="STANDARD_PPO",
        plan_name="Standard PPO",
        plan_type="PPO",
        worker_profile="DEFAULT_FULL_TIME_EMPLOYEE",
        subscriber_relationship="SELF",
        member_id="MEM-01374522",
        group_number="GRP-CVS-398915",
        policy_number="POL-27411793",
        effective_start="2026-01-01",
        effective_end="2026-12-31",
        employer_provenance="researched",
        payer_provenance="researched",
        employer_payer_provenance="synthetic",
        plan_provenance="synthetic",
        assignment_seed="42",
    )


def _encounter():
    return SimpleNamespace(
        encounter_id="ENC-X12-SCALED-001",
        admit_datetime="2026-10-03 13:45:00",
    )


def test_clinical_name_transform_normalizes_comma_to_caret():
    assert _normalize_clinical_name("KELLEY, DEVIN") == "KELLEY^DEVIN"
    assert _normalize_clinical_name("KELLEY^DEVIN") == "KELLEY^DEVIN"


def test_run_context_uses_timestamp_prefix_plus_incrementing_controls_at_scale():
    context = X12RunContext(
        datetime(2026, 10, 7, 11, 45, 12)
    )

    controls = []
    traces = []
    for _ in range(1000):
        item = context.next_exchange()
        controls.extend(
            [item.request_control, item.response_control]
        )
        traces.append(item.trace_id)

    assert len(controls) == 2000
    assert len(set(controls)) == 2000
    assert controls[0] == "114500001"
    assert controls[1] == "114500002"
    assert controls[-1] == "114502000"
    assert all(value.startswith("1145") for value in controls)

    assert traces[0] == "TRACE-270-20261007114512-00001"
    assert traces[-1] == "TRACE-270-20261007114512-01000"
    assert len(set(traces)) == 1000


def test_general_payer_materialization_copies_generated_clinical_state():
    patient = _patient()
    coverage = _coverage()

    member, enrollment, plan = materialize_payer_from_clinical(
        patient,
        coverage,
    )

    assert member.payer_id == coverage.payer_id
    assert member.member_id == coverage.member_id
    assert member.first_name == "DEVIN"
    assert member.last_name == "KELLEY"
    assert member.date_of_birth == patient.date_of_birth

    assert enrollment.member_record_id == member.member_record_id
    assert enrollment.payer_id == coverage.payer_id
    assert enrollment.plan_id == coverage.plan_id
    assert enrollment.group_number == coverage.group_number
    assert enrollment.effective_start == coverage.effective_start
    assert enrollment.effective_end == coverage.effective_end

    assert plan.payer_id == coverage.payer_id
    assert plan.plan_id == coverage.plan_id
    assert plan.plan_name == coverage.plan_name


def test_general_exchange_uses_encounter_date_and_generated_comma_name():
    patient = _patient()
    coverage = _coverage()
    encounter = _encounter()

    member, enrollment, plan = materialize_payer_from_clinical(
        patient,
        coverage,
    )
    payer = PayerSystem(
        coverage.payer_id,
        members=[member],
        enrollments=[enrollment],
        plans=[plan],
    )
    context = X12RunContext(
        datetime(2026, 10, 7, 11, 45, 12)
    )

    artifacts = generate_eligibility_exchange(
        patient=patient,
        coverage_profile=coverage,
        encounter=encounter,
        payer_system=payer,
        payer_member=member,
        payer_plan=plan,
        run_context=context,
    )

    parsed = parse_270_to_inquiry(artifacts.x270)

    assert parsed.inquiry.first_name == "DEVIN"
    assert parsed.inquiry.last_name == "KELLEY"
    assert parsed.inquiry.service_date == "2026-10-03"
    assert artifacts.service_date == "2026-10-03"
    assert artifacts.response.outcome == EligibilityOutcome.ACTIVE
    assert artifacts.request_transaction_control == "114500001"
    assert artifacts.response_transaction_control == "114500002"


def test_x12_writer_uses_datetime_stamp_in_bulk_and_per_encounter_files(tmp_path):
    patient = _patient()
    coverage = _coverage()
    encounter = _encounter()
    member, enrollment, plan = materialize_payer_from_clinical(
        patient,
        coverage,
    )
    payer = PayerSystem(
        coverage.payer_id,
        members=[member],
        enrollments=[enrollment],
        plans=[plan],
    )
    context = X12RunContext(
        datetime(2026, 10, 7, 11, 45, 12)
    )
    artifacts = generate_eligibility_exchange(
        patient=patient,
        coverage_profile=coverage,
        encounter=encounter,
        payer_system=payer,
        payer_member=member,
        payer_plan=plan,
        run_context=context,
    )

    bulk_paths = write_x12_artifacts(
        artifacts,
        out_dir=str(tmp_path),
        run_ts="20261007_114512",
        per_encounter=False,
        safe_encounter="ENC_X12",
    )

    assert bulk_paths["X12_270"].endswith(
        "X12_270_20261007_114512.x12"
    )
    assert bulk_paths["X12_271"].endswith(
        "X12_271_20261007_114512.x12"
    )

    per_dir = tmp_path / "per"
    per_paths = write_x12_artifacts(
        artifacts,
        out_dir=str(per_dir),
        run_ts="20261007_114512",
        per_encounter=True,
        safe_encounter="ENC_X12",
    )

    assert per_paths["X12_270"].endswith(
        "X12_270_ENC_X12_20261007_114512.x12"
    )
    assert per_paths["X12_271"].endswith(
        "X12_271_ENC_X12_20261007_114512.x12"
    )

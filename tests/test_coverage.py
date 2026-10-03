import random

from hl7_demo.coverage import (
    assign_coverage_profile,
    load_coverage_config,
)
from hl7_demo.generators import gen_transaction
from hl7_demo.models import Patient
from hl7_demo.segments import seg_in1, seg_in2


def _patient(patient_id: str = "PAT-COVERAGE-001") -> Patient:
    return Patient(
        patient_id=patient_id,
        patient_name="TESTER, JANE",
        date_of_birth="1985-01-01",
        sex="F",
        gender="Woman",
        race="Other",
        ethnicity="Not Hispanic or Latino",
        marital_status="Single",
        language="English",
        employer="LEGACY EMPLOYER",
        ssn="000-00-0000",
        address="1 Test St",
        phone="555-0100",
        email="jane.tester@example.invalid",
        zip_code="01852",
        city="Lowell",
        state="MA",
    )


def test_coverage_config_has_mvp_fixture_counts():
    config = load_coverage_config()

    assert len(config["employers"]) == 10
    assert len(config["payers"]) == 5
    assert len(config["plans"]) == 2

    assert "STARBUCKS" in config["employers"]
    assert "BERKSHIRE_HATHAWAY" not in config["employers"]

    assert set(config["plans"]) == {
        "STANDARD_PPO",
        "STANDARD_HMO",
    }

    for payer in config["payers"].values():
        refs = payer["actual_plan_references"]
        assert refs["status"] == "documented_for_future_use"
        assert len(refs["plans"]) == 2


def test_assignment_is_deterministic_and_updates_patient():
    first_patient = _patient()
    second_patient = _patient()

    first = assign_coverage_profile(
        first_patient,
        seed=42,
    )
    second = assign_coverage_profile(
        second_patient,
        seed=42,
    )

    assert first == second
    assert first_patient.coverage_profile == first
    assert first_patient.employer == first.employer_name

    assert first.employer_provenance == "researched"
    assert first.payer_provenance == "researched"
    assert first.employer_payer_provenance == "synthetic"
    assert first.plan_provenance == "synthetic"

    assert first.member_id.startswith("MEM-")
    assert first.group_number.startswith(
        f"GRP-{first.employer_id}-"
    )
    assert first.policy_number.startswith("POL-")
    assert first.effective_start == "2026-01-01"
    assert first.effective_end == "2026-12-31"


def test_assignment_is_isolated_from_global_random_state():
    patient_a = _patient("PAT-RNG-001")
    patient_b = _patient("PAT-RNG-001")

    random.seed(1)
    for _ in range(100):
        random.random()

    first = assign_coverage_profile(
        patient_a,
        seed=8675309,
    )

    random.seed(999999)
    for _ in range(1000):
        random.random()

    second = assign_coverage_profile(
        patient_b,
        seed=8675309,
    )

    assert first == second


def test_transaction_consumes_coverage_profile():
    patient = _patient("PAT-TX-001")
    coverage = assign_coverage_profile(
        patient,
        seed=7,
    )

    tx = gen_transaction(
        "ENC-TX-001",
        coverage_profile=coverage,
    )

    assert tx.insurance_plan_id == coverage.plan_id
    assert tx.insurance_plan_name == coverage.plan_name
    assert tx.member_id == coverage.member_id
    assert tx.group_number == coverage.group_number
    assert tx.plan_type == coverage.plan_type
    assert (
        tx.subscriber_relationship
        == coverage.subscriber_relationship
    )


def test_hl7_coverage_projection_uses_in1_and_in2_without_in1_14():
    patient = _patient("PAT-HL7-001")
    coverage = assign_coverage_profile(
        patient,
        seed=11,
    )
    tx = gen_transaction(
        "ENC-HL7-001",
        coverage_profile=coverage,
    )

    in1 = seg_in1(
        tx,
        patient=patient,
        coverage_profile=coverage,
    )
    fields = in1.split("|")

    assert fields[2].startswith(
        f"{coverage.plan_id}^{coverage.plan_name}^"
    )
    assert fields[3] == coverage.payer_id
    assert fields[4] == coverage.payer_name
    assert fields[8] == coverage.group_number
    assert fields[11] == coverage.employer_name
    assert fields[12] == "20260101"
    assert fields[13] == "20261231"
    assert fields[14] == ""
    assert fields[15] == coverage.plan_type
    assert fields[16] == "TESTER^JANE"
    assert fields[17].startswith("SEL^Self^")
    assert fields[49] == coverage.member_id

    in2 = seg_in2(coverage)
    in2_fields = in2.split("|")

    assert in2_fields[3] == (
        f"{coverage.employer_id}^"
        f"{coverage.employer_name}"
    )

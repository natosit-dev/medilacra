import pytest

import hl7_demo.messages as messages
from hl7_demo.coverage import assign_coverage_profile
from hl7_demo.generators import gen_transaction
from hl7_demo.models import Encounter, Patient
from hl7_demo.segments import seg_gt1


ENCOUNTER_DATE = "2026-10-03 14:00:00"


def _patient(
    *,
    patient_id: str,
    date_of_birth: str,
) -> Patient:
    patient = Patient(
        patient_id=patient_id,
        patient_name="RIVERA, JAMIE",
        date_of_birth=date_of_birth,
        sex="F",
        gender="Woman",
        race="Other",
        ethnicity="Not Hispanic or Latino",
        marital_status="Single",
        language="English",
        employer="LEGACY EMPLOYER",
        ssn="000-00-0000",
        address="MEDILACRA TEST ADDRESS 0001",
        phone="555-0100",
        email="jamie.rivera@example.invalid",
        zip_code="01852",
        city="Lowell",
        state="MA",
    )

    assign_coverage_profile(
        patient,
        seed=42,
    )

    return patient


def _encounter(patient_id: str) -> Encounter:
    return Encounter(
        encounter_id="ENC-GT1-001",
        patient_id=patient_id,
        visit_number="VN-GT1-001",
        account_number="ACC-GT1-001",
        patient_class="OUTPATIENT",
        assigned_patient_location="RAD^ROOM1^MEDILACRAHS",
        admit_datetime=ENCOUNTER_DATE,
        discharge_datetime="2026-10-03 15:00:00",
        hospital_service="RAD",
        admit_source="Physician Referral",
        discharge_disposition="Home",
        ordering_provider_id="ORD001",
        ordering_provider_name="LEE, MORGAN",
        attending_provider_id="ATT001",
        attending_provider_name="PATEL, ALEX",
        attending_provider_taxonomy="2085R0202X",
        attending_provider_specialty="Diagnostic Radiology",
        mid_level_provider_id="",
        mid_level_provider_name="",
        referring_provider_id="REF001",
        referring_provider_name="LEE, MORGAN",
        placer_order_number="PLACER-GT1-001",
        filler_order_number="FILLER-GT1-001",
        place_of_service_code="22",
        place_of_service_description="On Campus-Outpatient Hospital",
    )


def _transaction(patient: Patient):
    return gen_transaction(
        "ENC-GT1-001",
        coverage_profile=patient.coverage_profile,
    )


def _stub_adt_enrichment(monkeypatch):
    monkeypatch.setattr(
        messages,
        "get_poverty_pct_by_zcta",
        lambda zip_code: 0.0,
    )
    monkeypatch.setattr(
        messages,
        "get_air_quality_by_zip",
        lambda zip_code: None,
    )
    monkeypatch.setattr(
        messages,
        "predict_vitals",
        lambda age, poverty, aqi: {},
    )
    monkeypatch.setattr(
        messages,
        "build_obx_vitals",
        lambda values, start_set_id=1: [],
    )


def _build_minimal_adt(
    monkeypatch,
    patient: Patient,
    encounter: Encounter,
    transaction,
) -> str:
    _stub_adt_enrichment(monkeypatch)

    return messages.build_adt(
        patient,
        encounter,
        tx=transaction,
        add_air_obx=False,
        add_poverty_obx=False,
        add_places_obesity_obx=False,
        add_unemployment_obx=False,
        add_gi_obx=False,
        add_pronouns_obx=False,
        add_spcu_obx=False,
    )


@pytest.mark.parametrize(
    ("date_of_birth", "expected_age", "expected_gt1"),
    [
        ("2007-10-03", 19, True),
        ("2008-10-03", 18, False),
        ("2009-10-03", 17, False),
    ],
)
def test_gt1_age_boundary(
    monkeypatch,
    date_of_birth,
    expected_age,
    expected_gt1,
):
    patient = _patient(
        patient_id=f"PAT-AGE-{expected_age}",
        date_of_birth=date_of_birth,
    )
    encounter = _encounter(
        patient.patient_id
    )
    transaction = _transaction(
        patient
    )

    assert (
        messages._patient_age_at_encounter(
            patient,
            encounter,
        )
        == expected_age
    )

    adt = _build_minimal_adt(
        monkeypatch,
        patient,
        encounter,
        transaction,
    )

    segment_names = [
        segment.split("|", 1)[0]
        for segment in adt.split("\r")
    ]

    assert ("GT1" in segment_names) is expected_gt1


def test_age_calculation_uses_birthday_not_year_only():
    patient = _patient(
        patient_id="PAT-BIRTHDAY-EDGE",
        date_of_birth="2007-10-04",
    )
    encounter = _encounter(
        patient.patient_id
    )

    # One day before the 19th birthday.
    assert (
        messages._patient_age_at_encounter(
            patient,
            encounter,
        )
        == 18
    )
    assert not messages._should_emit_gt1(
        patient,
        encounter,
    )


def test_unparseable_dob_suppresses_gt1(monkeypatch):
    patient = _patient(
        patient_id="PAT-BAD-DOB",
        date_of_birth="NOT-A-DATE",
    )
    encounter = _encounter(
        patient.patient_id
    )
    transaction = _transaction(
        patient
    )

    assert (
        messages._patient_age_at_encounter(
            patient,
            encounter,
        )
        is None
    )

    adt = _build_minimal_adt(
        monkeypatch,
        patient,
        encounter,
        transaction,
    )

    assert "\rGT1|" not in f"\r{adt}"


def test_coverage_aware_gt1_uses_patient_and_matching_employer():
    patient = _patient(
        patient_id="PAT-GT1-EMPLOYER",
        date_of_birth="1983-06-14",
    )
    coverage = patient.coverage_profile
    transaction = _transaction(
        patient
    )

    gt1 = seg_gt1(
        transaction,
        patient=patient,
        coverage_profile=coverage,
        set_id=1,
    )
    fields = gt1.split("|")

    assert fields[1] == "1"
    assert fields[3] == "RIVERA^JAMIE"
    assert fields[11].startswith(
        "SEL^Self^"
    )

    assert fields[16] == coverage.employer_name

    # Intentionally deferred.
    assert fields[17] == ""
    assert fields[18] == ""
    assert fields[19] == ""

    assert fields[20] == "1"
    assert fields[29] == coverage.employer_id


def test_adult_adt_gt1_in1_in2_share_employer_reality(
    monkeypatch,
):
    patient = _patient(
        patient_id="PAT-ADT-EMPLOYER",
        date_of_birth="1983-06-14",
    )
    encounter = _encounter(
        patient.patient_id
    )
    transaction = _transaction(
        patient
    )
    coverage = patient.coverage_profile

    adt = _build_minimal_adt(
        monkeypatch,
        patient,
        encounter,
        transaction,
    )

    segments = {
        segment.split("|", 1)[0]: segment
        for segment in adt.split("\r")
        if segment.startswith(
            ("GT1|", "IN1|", "IN2|")
        )
    }

    assert set(segments) == {
        "GT1",
        "IN1",
        "IN2",
    }

    gt1_fields = segments["GT1"].split("|")
    in1_fields = segments["IN1"].split("|")
    in2_fields = segments["IN2"].split("|")

    assert patient.employer == coverage.employer_name
    assert gt1_fields[16] == coverage.employer_name
    assert gt1_fields[29] == coverage.employer_id
    assert in1_fields[11] == coverage.employer_name
    assert in2_fields[3] == (
        f"{coverage.employer_id}^"
        f"{coverage.employer_name}"
    )


@pytest.mark.parametrize(
    "date_of_birth",
    [
        "2008-10-03",
        "2009-10-03",
    ],
)
def test_minor_or_age_18_keeps_in1_in2_but_has_no_gt1(
    monkeypatch,
    date_of_birth,
):
    patient = _patient(
        patient_id=f"PAT-MINOR-{date_of_birth}",
        date_of_birth=date_of_birth,
    )
    encounter = _encounter(
        patient.patient_id
    )
    transaction = _transaction(
        patient
    )

    adt = _build_minimal_adt(
        monkeypatch,
        patient,
        encounter,
        transaction,
    )

    segment_names = [
        segment.split("|", 1)[0]
        for segment in adt.split("\r")
    ]

    assert "GT1" not in segment_names
    assert "IN1" in segment_names
    assert "IN2" in segment_names


@pytest.mark.parametrize(
    ("date_of_birth", "expect_gt1"),
    [
        ("2007-10-03", True),
        ("2008-10-03", False),
        ("2009-10-03", False),
    ],
)
def test_dft_uses_same_gt1_age_gate(
    date_of_birth,
    expect_gt1,
):
    patient = _patient(
        patient_id=f"PAT-DFT-{date_of_birth}",
        date_of_birth=date_of_birth,
    )
    encounter = _encounter(
        patient.patient_id
    )
    transaction = _transaction(
        patient
    )

    dft = messages.build_dft(
        patient,
        encounter,
        [transaction],
        [],
    )

    segment_names = [
        segment.split("|", 1)[0]
        for segment in dft.split("\r")
    ]

    assert ("GT1" in segment_names) is expect_gt1
    assert "IN1" in segment_names
    assert "IN2" in segment_names

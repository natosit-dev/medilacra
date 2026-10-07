from __future__ import annotations

import json
from types import SimpleNamespace

import pandas as pd

import hl7_demo.pipeline as pipeline
from hl7_demo.models import CoverageProfile, Patient
from utils import db


def _patient():
    return Patient(
        patient_id="PAT-FHIR-PIPELINE-001",
        patient_name="PIPELINE, FHIR",
        date_of_birth="1987-04-05",
        sex="F",
        gender="Woman",
        race="Other",
        ethnicity="Not Hispanic or Latino",
        marital_status="Single",
        language="English",
        employer="Synthetic Employer",
        ssn="000-00-0000",
        address="200 Integration Rd",
        phone="555-0199",
        email="fhir.pipeline@example.invalid",
        zip_code="01852",
        city="Lowell",
        state="MA",
    )


def _coverage(patient_id):
    return CoverageProfile(
        coverage_profile_id="COV-FHIR-PIPE-001",
        patient_id=patient_id,
        employer_id="EMP-FHIR",
        employer_name="Synthetic Employer",
        payer_id="AETNA",
        payer_name="Aetna",
        plan_id="STANDARD_PPO",
        plan_name="Standard PPO",
        plan_type="PPO",
        worker_profile="DEFAULT_FULL_TIME_EMPLOYEE",
        subscriber_relationship="SELF",
        member_id="MEM-FHIR-001",
        group_number="GRP-FHIR-001",
        policy_number="POL-FHIR-001",
        effective_start="2026-01-01",
        effective_end="2026-12-31",
        employer_provenance="synthetic",
        payer_provenance="researched",
        employer_payer_provenance="synthetic",
        plan_provenance="synthetic",
        assignment_seed="4242",
    )


def _message(message_type):
    return (
        "MSH|^~\\&|TEST|MEDILACRA|TEST|STAGE|"
        "20261007182900||"
        f"{message_type}|CTRL-{message_type}|P|2.5"
    )


def _encounter(patient_id, encounter_id):
    return SimpleNamespace(
        encounter_id=encounter_id,
        patient_id=patient_id,
        visit_number="VN0000000001",
        account_number="ACC-FHIR-001",
        patient_class="OUTPATIENT",
        assigned_patient_location="RAD_DEPT1",
        admit_datetime="2026-10-03 13:45:00",
        discharge_datetime="2026-10-03 14:45:00",
        hospital_service="RAD",
        admit_source="1",
        discharge_disposition="01",
        ordering_provider_id="R000001",
        ordering_provider_name="ORDERING, TEST",
        attending_provider_id="P000001",
        attending_provider_name="ATTENDING, TEST",
        attending_provider_taxonomy="2085R0202X",
        attending_provider_specialty="Diagnostic Radiology",
        mid_level_provider_id="",
        mid_level_provider_name="",
        referring_provider_id="",
        referring_provider_name="",
        placer_order_number="PLACER-FHIR-001",
        filler_order_number="FILLER-FHIR-001",
        place_of_service_code="22",
        place_of_service_description="Outpatient Hospital",
    )


def _transaction(encounter_id):
    return SimpleNamespace(
        transaction_id="TX-FHIR-PIPE-001",
        encounter_id=encounter_id,
        transaction_date="2026-10-03 14:00:00",
        transaction_amount=100.0,
        unit_cost=100.0,
        transaction_quantity=1,
        fee_schedule="DEFAULT",
        insurance_plan_id="STANDARD_PPO",
        insurance_plan_name="Standard PPO",
        member_id="MEM-FHIR-001",
        group_number="GRP-FHIR-001",
        plan_type="PPO",
        subscriber_relationship="SELF",
        authorization_number="",
        billing_provider_id="BILL-1",
        billing_provider_name="BILLING, TEST",
        billing_provider_npi="1111111111",
        guarantor_name="FHIR, PIPELINE",
        guarantor_relationship="SELF",
    )


def _observation(encounter):
    return SimpleNamespace(
        encounter_id=encounter.encounter_id,
        observation_id="OBS-FHIR-PIPE-001",
        cpt_code="70000",
        cpt_description="Synthetic imaging",
        procedure_description="Synthetic imaging",
        icd_code="Z00.00",
        icd_description="General exam",
        diagnosis_type="F",
        diagnosis_rank=1,
        placer_order_number=encounter.placer_order_number,
        filler_order_number=encounter.filler_order_number,
        observation_text="Synthetic result",
        observation_sub_id="1",
        result_status="F",
        completed_time="2026-10-03 14:15:00",
        performing_provider_id="PERF-1",
        performing_provider_name="PERFORMING, TEST",
    )


def test_run_pipeline_can_generate_fhir_eligibility_without_x12(
    tmp_path,
    monkeypatch,
):
    patient = _patient()
    coverage = _coverage(patient.patient_id)
    encounter = _encounter(
        patient.patient_id,
        "ENC-FHIR-PIPE-001",
    )
    transaction = _transaction(encounter.encounter_id)
    observation = _observation(encounter)

    monkeypatch.setattr(pipeline, "gen_patient", lambda: patient)
    monkeypatch.setattr(
        pipeline,
        "assign_coverage_profile",
        lambda p, seed=None: coverage,
    )
    monkeypatch.setattr(
        pipeline,
        "gen_encounter",
        lambda patient_id, profile=None: encounter,
    )
    monkeypatch.setattr(
        pipeline,
        "gen_transaction",
        lambda encounter_id, coverage_profile=None: transaction,
    )
    monkeypatch.setattr(
        pipeline,
        "gen_observation",
        lambda enc, report_row: observation,
    )
    monkeypatch.setattr(
        pipeline,
        "load_reports",
        lambda _glob: pd.DataFrame([{"stub": "row"}]),
    )
    monkeypatch.setattr(
        pipeline,
        "build_adt",
        lambda *_args, **_kwargs: _message("ADT^A01"),
    )
    monkeypatch.setattr(
        pipeline,
        "build_oru",
        lambda *_args, **_kwargs: _message("ORU^R01"),
    )
    monkeypatch.setattr(
        pipeline,
        "build_dft",
        lambda *_args, **_kwargs: _message("DFT^P03"),
    )

    out_dir = tmp_path / "out"
    db_path = tmp_path / "fhir.duckdb"

    counts = pipeline.run_pipeline(
        n_patients=1,
        report_glob="unused/*.csv",
        seed=4242,
        per_encounter=True,
        bulk=False,
        out_dir=str(out_dir),
        miles=75,
        include_labs=False,
        include_sdoh=False,
        include_x12=False,
        include_fhir_eligibility=True,
        persist="duckdb",
        duckdb_path=str(db_path),
    )

    assert "X12_270" not in counts
    assert "X12_271" not in counts
    assert counts["FHIR_ELIGIBILITY_REQUEST"] == 1
    assert counts["FHIR_ELIGIBILITY_RESPONSE"] == 1
    assert list(out_dir.glob("*.x12")) == []

    request_files = list(
        out_dir.glob(
            "FHIR_R4_4.0.1_CoverageEligibilityRequest_*.json"
        )
    )
    response_files = list(
        out_dir.glob(
            "FHIR_R4_4.0.1_CoverageEligibilityResponse_*.json"
        )
    )

    assert len(request_files) == 1
    assert len(response_files) == 1
    assert "ENC-FHIR-PIPE-001" in request_files[0].name

    request_bundle = json.loads(
        request_files[0].read_text(encoding="utf-8")
    )
    response_bundle = json.loads(
        response_files[0].read_text(encoding="utf-8")
    )

    assert request_bundle["type"] == "collection"
    assert response_bundle["type"] == "collection"

    with db.reader(db_path=str(db_path)) as con:
        payer_members = con.execute(
            "SELECT COUNT(*) FROM payer_members"
        ).fetchone()[0]
        payer_enrollments = con.execute(
            "SELECT COUNT(*) FROM payer_enrollments"
        ).fetchone()[0]
        raw_messages = con.execute(
            "SELECT COUNT(*) FROM messages"
        ).fetchone()[0]

    assert payer_members == 1
    assert payer_enrollments == 1

    # FHIR artifacts remain filesystem-only; only the three HL7 messages
    # are persisted in messages.raw_hl7.
    assert raw_messages == 3


def test_run_pipeline_generates_matching_x12_and_fhir_counts(
    tmp_path,
    monkeypatch,
):
    patient = _patient()
    coverage = _coverage(patient.patient_id)
    encounter = _encounter(
        patient.patient_id,
        "ENC-BOTH-001",
    )

    monkeypatch.setattr(pipeline, "gen_patient", lambda: patient)
    monkeypatch.setattr(
        pipeline,
        "assign_coverage_profile",
        lambda p, seed=None: coverage,
    )
    monkeypatch.setattr(
        pipeline,
        "gen_encounter",
        lambda patient_id, profile=None: encounter,
    )
    monkeypatch.setattr(
        pipeline,
        "gen_transaction",
        lambda encounter_id, coverage_profile=None: _transaction(
            encounter_id
        ),
    )
    monkeypatch.setattr(
        pipeline,
        "gen_observation",
        lambda enc, report_row: _observation(enc),
    )
    monkeypatch.setattr(
        pipeline,
        "load_reports",
        lambda _glob: pd.DataFrame([{"stub": "row"}]),
    )
    monkeypatch.setattr(
        pipeline,
        "build_adt",
        lambda *_args, **_kwargs: _message("ADT^A01"),
    )
    monkeypatch.setattr(
        pipeline,
        "build_oru",
        lambda *_args, **_kwargs: _message("ORU^R01"),
    )
    monkeypatch.setattr(
        pipeline,
        "build_dft",
        lambda *_args, **_kwargs: _message("DFT^P03"),
    )

    counts = pipeline.run_pipeline(
        n_patients=1,
        report_glob="unused/*.csv",
        seed=4242,
        per_encounter=True,
        bulk=False,
        out_dir=str(tmp_path / "out"),
        miles=75,
        include_labs=False,
        include_sdoh=False,
        include_x12=True,
        include_fhir_eligibility=True,
        persist="none",
    )

    assert counts["X12_270"] == counts["FHIR_ELIGIBILITY_REQUEST"] == 1
    assert counts["X12_271"] == counts["FHIR_ELIGIBILITY_RESPONSE"] == 1

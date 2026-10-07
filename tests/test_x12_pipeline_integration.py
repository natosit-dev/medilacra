from types import SimpleNamespace

import pandas as pd

import hl7_demo.pipeline as pipeline
from hl7_demo.models import Patient
from utils import db


def _patient() -> Patient:
    return Patient(
        patient_id="PAT-X12-PIPELINE-001",
        patient_name="PIPELINE, TEST",
        date_of_birth="1987-04-05",
        sex="F",
        gender="Woman",
        race="Other",
        ethnicity="Not Hispanic or Latino",
        marital_status="Single",
        language="English",
        employer="LEGACY EMPLOYER",
        ssn="000-00-0000",
        address="200 Integration Rd",
        phone="555-0199",
        email="test.pipeline@example.invalid",
        zip_code="01852",
        city="Lowell",
        state="MA",
    )


def _encounter(patient_id: str):
    return SimpleNamespace(
        encounter_id="ENC-X12-PIPELINE-001",
        patient_id=patient_id,
        visit_number="VN0000000001",
        account_number="ACC-X12-001",
        patient_class="OUTPATIENT",
        assigned_patient_location="RAD_DEPT1",
        admit_datetime="2026-10-01 10:00:00",
        discharge_datetime="2026-10-01 11:00:00",
        hospital_service="RAD",
        ordering_provider_id="R000001",
        ordering_provider_name="ORDERING, TEST",
        attending_provider_id="P000001",
        attending_provider_name="ATTENDING, TEST",
        placer_order_number="PLACER-X12-001",
        filler_order_number="FILLER-X12-001",
    )


def _transaction(encounter_id: str):
    return SimpleNamespace(
        transaction_id="TX-X12-001",
        encounter_id=encounter_id,
        transaction_date="2026-10-01 10:15:00",
        transaction_amount=100.0,
        unit_cost=100.0,
        transaction_quantity=1,
        fee_schedule="DEFAULT",
        insurance_plan_id="STANDARD_PPO",
        billing_provider_id="BILL-1",
        billing_provider_name="BILLING, TEST",
    )


def _observation(encounter):
    return SimpleNamespace(
        encounter_id=encounter.encounter_id,
        observation_id="OBS-X12-001",
        cpt_code="70000",
        icd_code="Z00.00",
        procedure_description="Synthetic X12 pipeline test",
        observation_text="Synthetic result",
        observation_sub_id="1",
        result_status="F",
        completed_time="2026-10-01 10:30:00",
        placer_order_number=encounter.placer_order_number,
        filler_order_number=encounter.filler_order_number,
    )


def _message(message_type: str) -> str:
    return (
        "MSH|^~\\&|TEST|MEDILACRA|TEST|STAGE|"
        "20261001120000||"
        f"{message_type}|CTRL-{message_type}|P|2.5"
    )


def test_run_pipeline_generates_x12_and_persists_payer_primitives(
    tmp_path,
    monkeypatch,
):
    patient = _patient()
    encounter = _encounter(patient.patient_id)
    observation = _observation(encounter)

    monkeypatch.setattr(
        pipeline,
        "gen_patient",
        lambda: patient,
    )
    monkeypatch.setattr(
        pipeline,
        "gen_encounter",
        lambda patient_id, **kwargs: encounter,
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
        lambda enc, report_row: observation,
    )
    monkeypatch.setattr(
        pipeline,
        "load_reports",
        lambda report_glob: pd.DataFrame([{"stub": "row"}]),
    )
    monkeypatch.setattr(
        pipeline,
        "build_adt",
        lambda *args, **kwargs: _message("ADT^A01"),
    )
    monkeypatch.setattr(
        pipeline,
        "build_oru",
        lambda *args, **kwargs: _message("ORU^R01"),
    )
    monkeypatch.setattr(
        pipeline,
        "build_dft",
        lambda *args, **kwargs: _message("DFT^P03"),
    )

    db_path = tmp_path / "x12.duckdb"
    out_dir = tmp_path / "out"

    counts = pipeline.run_pipeline(
        n_patients=1,
        report_glob="unused/*.csv",
        seed=4242,
        per_encounter=True,
        bulk=False,
        out_dir=str(out_dir),
        miles=0,
        include_labs=False,
        include_x12=True,
        persist="duckdb",
        duckdb_path=str(db_path),
    )

    assert counts["ADT"] == 1
    assert counts["ORU"] == 1
    assert counts["DFT"] == 1
    assert counts["X12_270"] == 1
    assert counts["X12_271"] == 1

    x12_files = sorted(out_dir.glob("*.x12"))
    assert len(x12_files) == 2

    x270 = next(
        path.read_text(encoding="utf-8")
        for path in x12_files
        if "X12_270_" in path.name
    )
    x271 = next(
        path.read_text(encoding="utf-8")
        for path in x12_files
        if "X12_271_" in path.name
    )

    assert "ST*270*" in x270
    assert "DTP*291*D8*20261001~" in x270
    assert "NM1*IL*1*PIPELINE*TEST" in x270

    assert "ST*271*" in x271
    assert "NM1*IL*1*PIPELINE*TEST" in x271

    with db.reader(db_path=str(db_path)) as con:
        counts_by_table = {
            table: con.execute(
                f"SELECT COUNT(*) FROM {table}"
            ).fetchone()[0]
            for table in (
                "patients",
                "coverage_profiles",
                "payer_members",
                "payer_enrollments",
                "payer_plans",
                "messages",
            )
        }

        stored_types = {
            row[0]
            for row in con.execute(
                "SELECT DISTINCT message_type FROM messages"
            ).fetchall()
        }

        linkage = con.execute(
            """
            SELECT
              c.payer_id,
              c.member_id,
              pm.payer_id,
              pm.member_id,
              pe.member_record_id,
              pm.member_record_id
            FROM coverage_profiles c
            JOIN payer_members pm
              ON c.payer_id = pm.payer_id
             AND c.member_id = pm.member_id
            JOIN payer_enrollments pe
              ON pe.member_record_id = pm.member_record_id
            """
        ).fetchone()

    assert counts_by_table["patients"] == 1
    assert counts_by_table["coverage_profiles"] == 1
    assert counts_by_table["payer_members"] == 1
    assert counts_by_table["payer_enrollments"] == 1
    assert counts_by_table["payer_plans"] == 1

    # X12 is filesystem output only this round; raw_hl7 remains HL7-only.
    assert counts_by_table["messages"] == 3
    assert stored_types == {"ADT^A01", "ORU^R01", "DFT^P03"} or stored_types == {
        "ADT",
        "ORU",
        "DFT",
    }

    assert linkage is not None
    assert linkage[0] == linkage[2]
    assert linkage[1] == linkage[3]
    assert linkage[4] == linkage[5]


def test_run_pipeline_without_x12_preserves_existing_count_shape(
    tmp_path,
    monkeypatch,
):
    patient = _patient()
    encounter = _encounter(patient.patient_id)
    observation = _observation(encounter)

    monkeypatch.setattr(pipeline, "gen_patient", lambda: patient)
    monkeypatch.setattr(
        pipeline,
        "gen_encounter",
        lambda patient_id, **kwargs: encounter,
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
        lambda enc, report_row: observation,
    )
    monkeypatch.setattr(
        pipeline,
        "load_reports",
        lambda report_glob: pd.DataFrame([{"stub": "row"}]),
    )
    monkeypatch.setattr(
        pipeline,
        "build_adt",
        lambda *args, **kwargs: _message("ADT^A01"),
    )
    monkeypatch.setattr(
        pipeline,
        "build_oru",
        lambda *args, **kwargs: _message("ORU^R01"),
    )
    monkeypatch.setattr(
        pipeline,
        "build_dft",
        lambda *args, **kwargs: _message("DFT^P03"),
    )

    counts = pipeline.run_pipeline(
        n_patients=1,
        report_glob="unused/*.csv",
        seed=4242,
        per_encounter=True,
        bulk=False,
        out_dir=str(tmp_path / "out"),
        miles=0,
        include_labs=False,
        include_x12=False,
        persist="none",
    )

    assert "X12_270" not in counts
    assert "X12_271" not in counts
    assert list((tmp_path / "out").glob("*.x12")) == []

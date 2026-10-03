from types import SimpleNamespace

import pandas as pd

import hl7_demo.pipeline as main_pipeline
import pipeline_duckdb as legacy_pipeline
from hl7_demo.generators import gen_transaction as real_gen_transaction
from hl7_demo.models import Patient
from utils import db


def _patient(patient_id: str) -> Patient:
    return Patient(
        patient_id=patient_id,
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
        encounter_id="ENC-COVERAGE-001",
        patient_id=patient_id,
        visit_number="VN0000000001",
        account_number="ACC-COVERAGE-001",
        patient_class="OUTPATIENT",
        assigned_patient_location="RAD_DEPT1",
        admit_datetime="2026-10-01 10:00:00",
        discharge_datetime="2026-10-01 11:00:00",
        hospital_service="RAD",
        ordering_provider_id="R000001",
        ordering_provider_name="ORDERING, TEST",
        attending_provider_id="P000001",
        attending_provider_name="ATTENDING, TEST",
        placer_order_number="PLACER-COVERAGE-001",
        filler_order_number="FILLER-COVERAGE-001",
    )


def _observation(encounter):
    return SimpleNamespace(
        encounter_id=encounter.encounter_id,
        observation_id="OBS-COVERAGE-001",
        cpt_code="70000",
        icd_code="Z00.00",
        procedure_description="Synthetic coverage integration test",
        observation_text="Synthetic result",
        observation_sub_id="1",
        result_status="F",
        completed_time="2026-10-01 10:30:00",
        placer_order_number=encounter.placer_order_number,
        filler_order_number=encounter.filler_order_number,
    )


def _reports():
    return pd.DataFrame([{"stub": "row"}])


def _message(message_type: str) -> str:
    return (
        "MSH|^~\\&|TEST|MEDILACRA|TEST|STAGE|"
        "20261003120000||"
        f"{message_type}|CTRL-{message_type}|P|2.5"
    )


def _patch_generation_path(monkeypatch, module, patient_id: str):
    patient = _patient(patient_id)
    encounter = _encounter(patient_id)
    observation = _observation(encounter)

    captured = {}

    monkeypatch.setattr(
        module,
        "gen_patient",
        lambda: patient,
    )
    monkeypatch.setattr(
        module,
        "gen_encounter",
        lambda patient_id, **kwargs: encounter,
    )
    monkeypatch.setattr(
        module,
        "gen_observation",
        lambda enc, report_row: observation,
    )
    monkeypatch.setattr(
        module,
        "load_reports",
        lambda report_glob: _reports(),
    )

    def _transaction(encounter_id, coverage_profile=None):
        assert coverage_profile is not None
        captured["coverage"] = coverage_profile
        return real_gen_transaction(
            encounter_id,
            coverage_profile=coverage_profile,
        )

    monkeypatch.setattr(
        module,
        "gen_transaction",
        _transaction,
    )

    def _adt(p, enc, tx=None, **kwargs):
        assert tx is not None
        assert p.coverage_profile is captured["coverage"]
        assert tx.insurance_plan_id == captured["coverage"].plan_id
        return _message("ADT^A01")

    def _oru(p, enc, observations):
        assert p.coverage_profile is captured["coverage"]
        return _message("ORU^R01")

    def _dft(p, enc, transactions, observations):
        assert p.coverage_profile is captured["coverage"]
        assert (
            transactions[0].insurance_plan_id
            == captured["coverage"].plan_id
        )
        return _message("DFT^P03")

    monkeypatch.setattr(module, "build_adt", _adt)
    monkeypatch.setattr(module, "build_oru", _oru)
    monkeypatch.setattr(module, "build_dft", _dft)

    return captured


def _assert_persisted_coverage_matches_transaction(db_path, patient_id):
    with db.reader(db_path=str(db_path)) as con:
        coverage_row = con.execute(
            """
            SELECT
              coverage_profile_id,
              employer_id,
              payer_id,
              plan_id,
              member_id
            FROM coverage_profiles
            WHERE patient_id = ?
            """,
            [patient_id],
        ).fetchone()

        transaction_row = con.execute(
            """
            SELECT insurance_plan_id
            FROM transactions
            WHERE encounter_id = ?
            """,
            ["ENC-COVERAGE-001"],
        ).fetchone()

    assert coverage_row is not None
    assert transaction_row is not None

    assert coverage_row[0].startswith("COV-")
    assert coverage_row[1]
    assert coverage_row[2]
    assert coverage_row[3] in {
        "STANDARD_PPO",
        "STANDARD_HMO",
    }
    assert coverage_row[4].startswith("MEM-")

    assert transaction_row[0] == coverage_row[3]

    return coverage_row


def test_main_pipeline_materializes_one_coverage_reality(
    tmp_path,
    monkeypatch,
):
    patient_id = "PAT-MAIN-PIPELINE"
    db_path = tmp_path / "main.duckdb"
    out_dir = tmp_path / "main-out"

    captured = _patch_generation_path(
        monkeypatch,
        main_pipeline,
        patient_id,
    )

    counts = main_pipeline.run_pipeline(
        n_patients=1,
        report_glob="unused/*.csv",
        seed=4242,
        per_encounter=True,
        bulk=False,
        out_dir=str(out_dir),
        miles=0,
        include_labs=False,
        persist="duckdb",
        duckdb_path=str(db_path),
    )

    assert counts["ADT"] == 1
    assert counts["ORU"] == 1
    assert counts["DFT"] == 1

    row = _assert_persisted_coverage_matches_transaction(
        db_path,
        patient_id,
    )

    assert row[0] == captured["coverage"].coverage_profile_id
    assert row[1] == captured["coverage"].employer_id
    assert row[2] == captured["coverage"].payer_id
    assert row[3] == captured["coverage"].plan_id
    assert row[4] == captured["coverage"].member_id

    assert len(list(out_dir.glob("*.hl7"))) == 3


def test_legacy_duckdb_pipeline_uses_same_coverage_primitive(
    tmp_path,
    monkeypatch,
):
    patient_id = "PAT-LEGACY-PIPELINE"
    db_path = tmp_path / "legacy.duckdb"
    out_dir = tmp_path / "legacy-out"

    captured = _patch_generation_path(
        monkeypatch,
        legacy_pipeline,
        patient_id,
    )

    counts = legacy_pipeline.run_and_persist(
        n_patients=1,
        report_glob="unused/*.csv",
        seed=4242,
        per_encounter=True,
        bulk=False,
        out_dir=str(out_dir),
        miles=0,
        db_path=str(db_path),
    )

    assert counts == {
        "ADT": 1,
        "ORU": 1,
        "DFT": 1,
    }

    row = _assert_persisted_coverage_matches_transaction(
        db_path,
        patient_id,
    )

    assert row[0] == captured["coverage"].coverage_profile_id
    assert row[1] == captured["coverage"].employer_id
    assert row[2] == captured["coverage"].payer_id
    assert row[3] == captured["coverage"].plan_id
    assert row[4] == captured["coverage"].member_id

    assert len(list(out_dir.glob("*.hl7"))) == 3

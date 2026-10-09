"""Real run_pipeline boundary for new Claims/ePA output (no network calls)."""
from __future__ import annotations

import json

import pandas as pd

import hl7_demo.pipeline as pipeline
from tests.test_fhir_pipeline_integration import (
    _patient, _coverage, _encounter, _transaction, _observation, _message,
)
from utils import db


def test_pipeline_generates_claims_epa_without_eligibility_representations(tmp_path, monkeypatch):
    patient = _patient()
    coverage = _coverage(patient.patient_id)
    encounter = _encounter(patient.patient_id, "ENC-CPE-PIPE-001")
    transaction = _transaction(encounter.encounter_id)
    observation = _observation(encounter)

    monkeypatch.setattr(pipeline, "gen_patient", lambda: patient)
    monkeypatch.setattr(pipeline, "assign_coverage_profile", lambda p, seed=None: coverage)
    monkeypatch.setattr(pipeline, "gen_encounter", lambda patient_id, profile=None: encounter)
    monkeypatch.setattr(
        pipeline, "gen_transaction",
        lambda encounter_id, coverage_profile=None: transaction,
    )
    monkeypatch.setattr(pipeline, "gen_observation", lambda enc, report_row: observation)
    monkeypatch.setattr(
        pipeline, "load_reports",
        lambda glob: pd.DataFrame([{"stub": "row"}]),
    )
    monkeypatch.setattr(pipeline, "build_adt", lambda *args, **kwargs: _message("ADT^A01"))
    monkeypatch.setattr(pipeline, "build_oru", lambda *args, **kwargs: _message("ORU^R01"))
    monkeypatch.setattr(pipeline, "build_dft", lambda *args, **kwargs: _message("DFT^P03"))

    out = tmp_path / "out"
    db_path = tmp_path / "claims_epa.duckdb"
    counts = pipeline.run_pipeline(
        n_patients=1, report_glob="unused/*.csv", seed=4242,
        per_encounter=True, bulk=False, out_dir=str(out),
        miles=0, include_labs=False, include_sdoh=False,
        include_x12=False, include_fhir_eligibility=False,
        include_claims_epa=True, persist="duckdb",
        duckdb_path=str(db_path),
    )
    assert counts["ADT"] == counts["ORU"] == counts["DFT"] == 1
    for name in ("X12_837P", "X12_835", "X12_278_REQUEST", "X12_278_RESPONSE",
                 "FHIR_CLAIM_REQUEST", "FHIR_CLAIM_RESPONSE",
                 "FHIR_EPA_REQUEST", "FHIR_EPA_RESPONSE"):
        assert counts[name] == 1, (name, counts)
    assert "X12_270" not in counts
    assert "FHIR_ELIGIBILITY_REQUEST" not in counts
    folders = list(out.glob("CLAIMS_EPA_*"))
    assert len(folders) == 1
    assert len(list(folders[0].glob("*.x12"))) == 4
    assert len(list(folders[0].glob("*.fhir.json"))) == 4
    assert "ST*837*" in (folders[0] / "837P.x12").read_text()
    assert "ST*278*" in (folders[0] / "278_request.x12").read_text()
    assert (folders[0] / "manifest.json").exists()
    fhir_claim = json.loads((folders[0] / "claim_request.fhir.json").read_text())
    assert fhir_claim["entry"][0]["resource"]["use"] == "claim"
    assert fhir_claim["entry"][0]["resource"]["patient"]["reference"].startswith("Patient/")
    fhir_pa = json.loads((folders[0] / "epa_request.fhir.json").read_text())
    assert fhir_pa["entry"][0]["resource"]["use"] == "preauthorization"

    # Ensure raw X12/FHIR is not falsely inserted into HL7 messages.raw_hl7.
    with db.reader(db_path=str(db_path)) as connection:
        logged = connection.execute("SELECT DISTINCT message_type FROM messages").fetchall()
        assert {row[0] for row in logged} == {"ADT", "ORU", "DFT"}
        case_row = connection.execute(
            "SELECT case_id, status FROM simulation_cases"
        ).fetchone()
        assert case_row and case_row[1] == "completed"
        record_owners = dict(connection.execute(
            "SELECT record_name, record_owner FROM semantic_records "
            "WHERE case_id = ?", [case_row[0]]
        ).fetchall())
        assert record_owners["claim_decision"] == "payer"
        assert record_owners["authorization_request"] == "clinical"
        assert connection.execute(
            "SELECT COUNT(*) FROM artifact_index WHERE case_id = ?", [case_row[0]]
        ).fetchone()[0] == 10

    # Replay from storage only: no Faker, original CSV, payer model or source objects.
    from reality.replay import replay_claims_case
    replayed = replay_claims_case(str(db_path), case_row[0])
    assert replayed.x837p == (folders[0] / "837P.x12").read_text()
    assert replayed.x835 == (folders[0] / "835.x12").read_text()
    assert replayed.x278_request == (folders[0] / "278_request.x12").read_text()
    assert replayed.authorization_request == fhir_pa



def test_main_ui_and_pipeline_cli_expose_the_option():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    main = (root / "medi_lacra_app.py").read_text()
    persist = (root / "pages" / "2_Generate_and_Persist.py").read_text()
    p = (root / "hl7_demo" / "pipeline.py").read_text()
    assert "Include Claims + ePA (X12 and FHIR R4)" in main
    assert "Include Claims + ePA (X12 and FHIR R4)" in persist
    assert "include_claims_epa=include_claims_epa" in main
    assert "include_claims_epa=bool(include_claims_epa)" in persist
    assert "--include-claims-epa" in p

"""DuckDB core-reality persistence contract. No network or PHI fixtures."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import pytest

from reality.persistence import (
    encode_snapshot, finish_case, load_case, persist_case, register_artifact,
    snapshot_hash,
)
from storage_duckdb_entities import (
    init_db, upsert_patient, upsert_encounter, upsert_observation,
    upsert_transaction,
)
from utils.db import reader


@dataclass
class TinyPatient:
    patient_id: str
    address: str
    employer: str


def test_core_snapshot_is_exact_replayable_and_institution_owned(tmp_path):
    db_path = str(tmp_path / "case.duckdb")
    init_db(db_path)
    records = {
        "patient": TinyPatient("SYN-01", "21 SAMPLE ROAD", "EXAMPLE EMPLOYER"),
        "payer_record": {"member_id": "M-01", "address": "99 PAYER LANE"},
        "decision": {"status": "denied", "allowed_cents": 0},
    }
    owners = {"patient": "clinical", "payer_record": "payer", "decision": "payer"}
    sha = persist_case(
        db_path=db_path, run_id="run-1", case_id="case-1",
        source_records=records, owner_by_record=owners,
        seed=43, started_at=datetime(2026, 10, 8, 16),
    )
    assert len(sha) == 64
    assert load_case(db_path, "case-1") == {
        "patient": {"patient_id": "SYN-01", "address": "21 SAMPLE ROAD",
                    "employer": "EXAMPLE EMPLOYER"},
        "payer_record": {"member_id": "M-01", "address": "99 PAYER LANE"},
        "decision": {"status": "denied", "allowed_cents": 0},
    }
    assert persist_case(db_path=db_path, run_id="run-1", case_id="case-1",
                        source_records=records, owner_by_record=owners) == sha
    with pytest.raises(ValueError, match="Immutable case collision"):
        persist_case(
            db_path=db_path, run_id="run-1", case_id="case-1",
            source_records={**records, "decision": {"status": "approved"}},
            owner_by_record=owners,
        )
    with reader(db_path=db_path) as con:
        assert con.execute(
            "SELECT COUNT(*) FROM simulation_cases"
        ).fetchone()[0] == 1
        assert con.execute(
            "SELECT record_owner FROM semantic_records "
            "WHERE case_id='case-1' AND record_name='decision'"
        ).fetchone()[0] == "payer"
    register_artifact(db_path, "case-1", "X12_835", "/tmp/test.x12",
                      "ST*835*0001~")
    finish_case(db_path, "case-1")
    with reader(db_path=db_path) as con:
        assert con.execute(
            "SELECT status FROM simulation_cases WHERE case_id='case-1'"
        ).fetchone()[0] == "completed"
        assert con.execute(
            "SELECT payload_sha256 FROM artifact_index WHERE case_id='case-1'"
        ).fetchone()[0] == snapshot_hash("ST*835*0001~")


def test_core_snapshot_fails_on_unowned_or_unserializable_facts(tmp_path):
    db_path = str(tmp_path / "validation.duckdb")
    init_db(db_path)
    with pytest.raises(ValueError, match="owner"):
        persist_case(db_path=db_path, run_id="r", case_id="x",
                     source_records={"patient": {"id": "1"}}, owner_by_record={})
    with pytest.raises(TypeError, match="Unsupported"):
        encode_snapshot({"data": object()})
    with pytest.raises(KeyError):
        load_case(db_path, "missing")


def test_all_31_previously_dropped_scalar_fields_round_trip(tmp_path):
    db_path = str(tmp_path / "fields.duckdb")
    init_db(db_path)

    examples = {
        "patients": (
            upsert_patient, "patient_id", {"patient_id": "PAT-1"},
            {"gender": "Non-binary", "ethnicity": "Synthetic", "marital_status": "S",
             "language": "es", "employer": "TEST EMPLOYER", "email": "test@example.invalid"}
        ),
        "encounters": (
            upsert_encounter, "encounter_id", {"encounter_id": "ENC-1", "patient_id": "PAT-1"},
            {"admit_source": "transfer", "discharge_disposition": "home",
             "attending_provider_taxonomy": "207R00000X",
             "attending_provider_specialty": "Internal Medicine",
             "mid_level_provider_id": "NURSE-1", "mid_level_provider_name": "PATEL, TEST",
             "referring_provider_id": "REF-1", "referring_provider_name": "CHEN, TEST",
             "place_of_service_code": "22",
             "place_of_service_description": "Outpatient hospital"}
        ),
        "observations": (
            upsert_observation, "observation_id",
            {"encounter_id": "ENC-1", "observation_id": "OBS-1"},
            {"cpt_description": "Simple test", "icd_description": "Other test",
             "diagnosis_type": "admitting", "diagnosis_rank": 2,
             "performing_provider_id": "LAB-1", "performing_provider_name": "TECH, TEST"}
        ),
        "transactions": (
            upsert_transaction, "transaction_id",
            {"transaction_id": "TX-1", "encounter_id": "ENC-1"},
            {"insurance_plan_name": "TEST PLAN", "member_id": "MEM-01",
             "group_number": "GRP-01", "plan_type": "PPO",
             "subscriber_relationship": "SELF", "authorization_number": "AUTH-01",
             "billing_provider_npi": "1234567890",
             "guarantor_name": "EXAMPLE, TEST", "guarantor_relationship": "SELF"}
        )
    }
    assert sum(len(v[3]) for v in examples.values()) == 31
    for table, (upsert, pk, key_values, new_values) in examples.items():
        upsert({**key_values, **new_values}, db_path=db_path)
        with reader(db_path=db_path) as con:
            columns = list(new_values)
            where = ("encounter_id = ? AND observation_id = ?"
                     if table == "observations" else pk + " = ?")
            keys = (["ENC-1", "OBS-1"] if table == "observations"
                    else [key_values[pk]])
            result = con.execute(
                f"SELECT {', '.join(columns)} FROM {table} WHERE {where}", keys,
            ).fetchone()
        assert result == tuple(new_values.values()), (table, result)

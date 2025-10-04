from datetime import datetime

from storage_duckdb_entities import (
    append_message,
    init_db,
    upsert_encounter,
    upsert_observation,
    upsert_order,
    upsert_patient,
    upsert_transaction,
)
from utils import db


def test_init_db_creates_expected_tables(tmp_path):
    db_path = tmp_path / "medilacra.duckdb"
    resolved = init_db(db_path=str(db_path))
    assert resolved == str(db_path.resolve())

    with db.reader(db_path=str(db_path)) as con:
        tables = {name for (name,) in con.execute("SHOW TABLES").fetchall()}

    expected = {"patients", "encounters", "observations", "transactions", "messages", "orders"}
    assert expected.issubset(tables)


def test_entity_upserts_and_message_append(tmp_path):
    db_path = tmp_path / "medilacra.duckdb"
    init_db(db_path=str(db_path))

    patient = {
        "patient_id": "PAT123",
        "patient_name": "Testy McTestface",
        "date_of_birth": "1980-01-01",
        "sex": "F",
        "race": "Other",
        "ssn": "123-45-6789",
        "phone": "555-0100",
        "address": "123 Main St",
        "city": "Metropolis",
        "state": "CA",
        "zip": "94016",
    }
    upsert_patient(patient, db_path=str(db_path))

    encounter = {
        "encounter_id": "ENC123",
        "patient_id": "PAT123",
        "visit_number": "VN0001",
        "account_number": "ACCT999",
        "patient_class": "O",
        "assigned_patient_location": "ED",
        "admit_ts": datetime(2024, 1, 1, 12, 0, 0),
        "discharge_ts": datetime(2024, 1, 1, 13, 0, 0),
        "hospital_service": "ER",
        "ordering_provider_id": "PRV1",
        "ordering_provider_name": "Dr. Who",
        "attending_provider_id": "PRV2",
        "attending_provider_name": "Dr. Strange",
        "placer_order_number": "PO123",
        "filler_order_number": "FO123",
    }
    upsert_encounter(encounter, db_path=str(db_path))

    observation = {
        "encounter_id": "ENC123",
        "observation_id": "OBS1",
        "cpt_code": "12345",
        "icd_code": "A00",
        "procedure_description": "XRAY",
        "observation_text": "All clear",
        "observation_sub_id": "1",
        "result_status": "F",
        "completed_time": datetime(2024, 1, 1, 12, 30, 0),
        "placer_order_number": "PO123",
        "filler_order_number": "FO123",
    }
    upsert_observation(observation, db_path=str(db_path))

    order = {
        "placer_order_number": "PO123",
        "filler_order_number": "FO123",
        "patient_id": "PAT123",
        "encounter_id": "ENC123",
        "order_ts": datetime(2024, 1, 1, 12, 5, 0),
    }
    upsert_order(order, db_path=str(db_path))

    transaction = {
        "transaction_id": "TX123",
        "encounter_id": "ENC123",
        "transaction_date": datetime(2024, 1, 1, 12, 45, 0),
        "transaction_amount": 150.0,
        "unit_cost": 150.0,
        "transaction_quantity": 1,
        "fee_schedule": "Default",
        "insurance_plan_id": "PLAN1",
        "billing_provider_id": "PRV3",
        "billing_provider_name": "Dr. Billing",
    }
    upsert_transaction(transaction, db_path=str(db_path))

    ingest_time = datetime(2024, 1, 1, 14, 0, 0)
    append_message(
        {
            "run_id": "RUN1",
            "message_type": "ADT",
            "control_id": "CTRL1",
            "encounter_id": "ENC123",
            "raw_hl7": r"MSH|^~\&|",
            "written_path": "/tmp/ADT.hl7",
            "ingest_ts": ingest_time,
        },
        db_path=str(db_path),
    )

    with db.reader(db_path=str(db_path)) as con:
        patient_row = con.execute(
            "SELECT mrn, patient_name FROM patients WHERE patient_id = ?", ["PAT123"]
        ).fetchone()
        encounter_row = con.execute(
            "SELECT account_number FROM encounters WHERE encounter_id = ?", ["ENC123"]
        ).fetchone()
        order_row = con.execute(
            "SELECT patient_id FROM orders WHERE placer_order_number = ?", ["PO123"]
        ).fetchone()
        message_row = con.execute(
            "SELECT run_id, message_type, dt FROM messages WHERE encounter_id = ?", ["ENC123"]
        ).fetchone()

    assert patient_row == ("PAT123", "Testy McTestface")
    assert encounter_row == ("ACCT999",)
    assert order_row == ("PAT123",)
    assert message_row[0] == "RUN1"
    assert message_row[1] == "ADT"
    assert str(message_row[2]) == ingest_time.date().isoformat()
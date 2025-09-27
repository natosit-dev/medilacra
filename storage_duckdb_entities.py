
# storage_duckdb_entities.py
import duckdb
from typing import Dict, Any
from datetime import datetime

DEFAULT_DB_PATH = "./medilacra.duckdb"

DDL = [
    """
    CREATE TABLE IF NOT EXISTS patients (
      patient_id TEXT PRIMARY KEY,
      patient_name TEXT,
      date_of_birth DATE,
      sex TEXT,
      race TEXT,
      ssn TEXT,
      phone TEXT,
      address TEXT,
      city TEXT,
      state TEXT,
      zip TEXT,
      created_ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS encounters (
      encounter_id TEXT PRIMARY KEY,
      patient_id TEXT,
      visit_number TEXT,
      patient_class TEXT,
      assigned_patient_location TEXT,
      admit_ts TIMESTAMP,
      discharge_ts TIMESTAMP,
      hospital_service TEXT,
      ordering_provider_id TEXT,
      ordering_provider_name TEXT,
      attending_provider_id TEXT,
      attending_provider_name TEXT,
      placer_order_number TEXT,
      filler_order_number TEXT,
      created_ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS observations (
      encounter_id TEXT,
      observation_id TEXT,
      cpt_code TEXT,
      icd_code TEXT,
      procedure_description TEXT,
      observation_text TEXT,
      observation_sub_id TEXT,
      result_status TEXT,
      completed_time TIMESTAMP,
      PRIMARY KEY (encounter_id, observation_id)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS transactions (
      transaction_id TEXT PRIMARY KEY,
      encounter_id TEXT,
      transaction_date TIMESTAMP,
      transaction_amount DOUBLE,
      unit_cost DOUBLE,
      transaction_quantity INTEGER,
      fee_schedule TEXT,
      insurance_plan_id TEXT,
      billing_provider_id TEXT,
      billing_provider_name TEXT,
      created_ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS messages (
      run_id TEXT,
      message_type TEXT,   -- ADT|ORU|DFT
      control_id TEXT,
      encounter_id TEXT,
      raw_hl7 TEXT,
      written_path TEXT,
      ingest_ts TIMESTAMP,
      dt DATE
    );

    -- Add MRN to patients (unique), keep patient_id as the primary key you already use
ALTER TABLE patients ADD COLUMN IF NOT EXISTS mrn TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS ux_patients_mrn ON patients(mrn);

-- Add account number to encounters; enforce patient+visit uniqueness
ALTER TABLE encounters ADD COLUMN IF NOT EXISTS account_number TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS ux_enc_patient_visit
  ON encounters(patient_id, visit_number);

-- Add order numbers to observations for direct linking
ALTER TABLE observations ADD COLUMN IF NOT EXISTS placer_order_number TEXT;
ALTER TABLE observations ADD COLUMN IF NOT EXISTS filler_order_number TEXT;

-- Optional but recommended: a dedicated orders table (1 per order)
CREATE TABLE IF NOT EXISTS orders (
  placer_order_number TEXT PRIMARY KEY,
  filler_order_number TEXT UNIQUE,
  patient_id TEXT,
  encounter_id TEXT,
  order_ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_orders_patient ON orders(patient_id);
CREATE INDEX IF NOT EXISTS ix_orders_enc ON orders(encounter_id);

    """
]

def init_db(db_path: str = DEFAULT_DB_PATH) -> str:
    con = duckdb.connect(db_path)
    try:
        for stmt in DDL:
            con.execute(stmt)
    finally:
        con.close()
    return db_path

def _connect(db_path: str):
    return duckdb.connect(db_path)

# storage_duckdb_entities.py
def upsert_patient(p: Dict[str, Any], db_path: str = DEFAULT_DB_PATH):
    con = _connect(db_path)
    try:
        con.execute("BEGIN")
        con.execute("DELETE FROM patients WHERE patient_id = ?", [p["patient_id"]])
        con.execute(
            """INSERT INTO patients (
                 patient_id, mrn, patient_name, date_of_birth, sex, race, ssn, phone,
                 address, city, state, zip, created_ts
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, COALESCE(?, CURRENT_TIMESTAMP))""",
            [
                p.get("patient_id"),
                p.get("mrn") or p.get("patient_id"),  # <= MRN default
                p.get("patient_name"), p.get("date_of_birth"),
                p.get("sex"), p.get("race"), p.get("ssn"), p.get("phone"),
                p.get("address"), p.get("city"), p.get("state"),
                p.get("zip_code") or p.get("zip"),
                p.get("created_ts")
            ]
        )
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK"); raise
    finally:
        con.close()


def upsert_encounter(e: Dict[str, Any], db_path: str = DEFAULT_DB_PATH):
    con = _connect(db_path)
    try:
        con.execute("BEGIN")
        con.execute("DELETE FROM encounters WHERE encounter_id = ?", [e["encounter_id"]])
        con.execute(
            """INSERT INTO encounters (
                 encounter_id, patient_id, visit_number, account_number,
                 patient_class, assigned_patient_location,
                 admit_ts, discharge_ts, hospital_service,
                 ordering_provider_id, ordering_provider_name,
                 attending_provider_id, attending_provider_name,
                 placer_order_number, filler_order_number, created_ts
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, COALESCE(?, CURRENT_TIMESTAMP))""",
            [
                e.get("encounter_id"), e.get("patient_id"),
                e.get("visit_number"), e.get("account_number"),
                e.get("patient_class"), e.get("assigned_patient_location"),
                e.get("admit_datetime") or e.get("admit_ts"),
                e.get("discharge_datetime") or e.get("discharge_ts"),
                e.get("hospital_service"),
                e.get("ordering_provider_id"), e.get("ordering_provider_name"),
                e.get("attending_provider_id"), e.get("attending_provider_name"),
                e.get("placer_order_number"), e.get("filler_order_number"),
                e.get("created_ts")
            ]
        )
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK"); raise
    finally:
        con.close()


def upsert_observation(o: Dict[str, Any], db_path: str = DEFAULT_DB_PATH):
    con = _connect(db_path)
    try:
        con.execute("BEGIN")
        con.execute(
            "DELETE FROM observations WHERE encounter_id = ? AND observation_id = ?",
            [o["encounter_id"], o["observation_id"]]
        )
        con.execute(
            """INSERT INTO observations (
                 encounter_id, observation_id, cpt_code, icd_code, procedure_description,
                 observation_text, observation_sub_id, result_status, completed_time,
                 placer_order_number, filler_order_number
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                o.get("encounter_id"), o.get("observation_id"),
                o.get("cpt_code"), o.get("icd_code"), o.get("procedure_description"),
                o.get("observation_text"), o.get("observation_sub_id"),
                o.get("result_status"), o.get("completed_time"),
                o.get("placer_order_number"), o.get("filler_order_number"),
            ]
        )
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK"); raise
    finally:
        con.close()

def upsert_order(row: Dict[str, Any], db_path: str = DEFAULT_DB_PATH):
    con = _connect(db_path)
    try:
        con.execute("BEGIN")
        con.execute("DELETE FROM orders WHERE placer_order_number = ?", [row["placer_order_number"]])
        con.execute(
            """INSERT INTO orders (
                 placer_order_number, filler_order_number, patient_id, encounter_id, order_ts
               ) VALUES (?, ?, ?, ?, COALESCE(?, CURRENT_TIMESTAMP))""",
            [
                row.get("placer_order_number"), row.get("filler_order_number"),
                row.get("patient_id"), row.get("encounter_id"), row.get("order_ts"),
            ]
        )
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK"); raise
    finally:
        con.close()


def upsert_transaction(t: Dict[str, Any], db_path: str = DEFAULT_DB_PATH):
    con = _connect(db_path)
    try:
        con.execute("BEGIN")
        con.execute("DELETE FROM transactions WHERE transaction_id = ?", [t["transaction_id"]])
        con.execute(
            """INSERT INTO transactions (
                 transaction_id, encounter_id, transaction_date, transaction_amount,
                 unit_cost, transaction_quantity, fee_schedule, insurance_plan_id,
                 billing_provider_id, billing_provider_name, created_ts
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, COALESCE(?, CURRENT_TIMESTAMP))""",
            [
                t.get("transaction_id"), t.get("encounter_id"), t.get("transaction_date"),
                t.get("transaction_amount"), t.get("unit_cost"), t.get("transaction_quantity"),
                t.get("fee_schedule"), t.get("insurance_plan_id"),
                t.get("billing_provider_id"), t.get("billing_provider_name"),
                t.get("created_ts")
            ]
        )
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK"); raise
    finally:
        con.close()

def append_message(row: Dict[str, Any], db_path: str = DEFAULT_DB_PATH):
    con = _connect(db_path)
    try:
        con.execute(
            "INSERT INTO messages VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [
                row.get("run_id"), row.get("message_type"), row.get("control_id"),
                row.get("encounter_id"), row.get("raw_hl7"), row.get("written_path"),
                row.get("ingest_ts"), row.get("ingest_ts").date() if row.get("ingest_ts") else None
            ]
        )
    finally:
        con.close()

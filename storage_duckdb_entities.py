# storage_duckdb_entities.py
from typing import Dict, Any
from datetime import datetime
import json

from utils.db import writer, reader, get_db_path
from utils.log_utils import get_logger

logger = get_logger(name="MediLacra",
                    context={"component": "storage", "module": "storage_duckdb_entities", "env": "dev"})

# Keep for backwards compatibility; utils.db manages the actual path
DEFAULT_DB_PATH = get_db_path()

def _resolve_db_path(db_path: str | None = None) -> str:
    """Return the provided path or fall back to the configured default."""

    return db_path or get_db_path()

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

-- Add account number to encounters. enforce patient+visit uniqueness
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
    """,
    """
    CREATE TABLE IF NOT EXISTS coverage_profiles (
      coverage_profile_id TEXT PRIMARY KEY,
      patient_id TEXT,

      employer_id TEXT,
      employer_name TEXT,

      payer_id TEXT,
      payer_name TEXT,

      plan_id TEXT,
      plan_name TEXT,
      plan_type TEXT,

      worker_profile TEXT,
      subscriber_relationship TEXT,

      member_id TEXT,
      group_number TEXT,
      policy_number TEXT,

      effective_start DATE,
      effective_end DATE,

      employer_provenance TEXT,
      payer_provenance TEXT,
      employer_payer_provenance TEXT,
      plan_provenance TEXT,

      assignment_seed TEXT,

      created_ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    CREATE INDEX IF NOT EXISTS ix_coverage_profiles_patient
      ON coverage_profiles(patient_id);
    """,
    """
    CREATE TABLE IF NOT EXISTS payer_members (
      member_record_id TEXT PRIMARY KEY,
      payer_id TEXT,
      member_id TEXT,
      first_name TEXT,
      last_name TEXT,
      date_of_birth DATE,
      administrative_sex TEXT,
      created_ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    CREATE INDEX IF NOT EXISTS ix_payer_members_payer
      ON payer_members(payer_id);
    CREATE INDEX IF NOT EXISTS ix_payer_members_payer_member
      ON payer_members(payer_id, member_id);
    """,
    """
    CREATE TABLE IF NOT EXISTS payer_enrollments (
      enrollment_id TEXT PRIMARY KEY,
      member_record_id TEXT,
      payer_id TEXT,
      plan_id TEXT,
      group_number TEXT,
      effective_start DATE,
      effective_end DATE,
      status TEXT,
      created_ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    CREATE INDEX IF NOT EXISTS ix_payer_enrollments_member
      ON payer_enrollments(member_record_id);
    CREATE INDEX IF NOT EXISTS ix_payer_enrollments_payer
      ON payer_enrollments(payer_id);
    CREATE INDEX IF NOT EXISTS ix_payer_enrollments_plan
      ON payer_enrollments(plan_id);
    """,
    """
    CREATE TABLE IF NOT EXISTS payer_plans (
      payer_id TEXT,
      plan_id TEXT,
      plan_name TEXT,
      plan_type TEXT,
      created_ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      PRIMARY KEY (payer_id, plan_id)
    );
    """
    """
ALTER TABLE patients ADD COLUMN IF NOT EXISTS gender TEXT;
ALTER TABLE patients ADD COLUMN IF NOT EXISTS ethnicity TEXT;
ALTER TABLE patients ADD COLUMN IF NOT EXISTS marital_status TEXT;
ALTER TABLE patients ADD COLUMN IF NOT EXISTS language TEXT;
ALTER TABLE patients ADD COLUMN IF NOT EXISTS employer TEXT;
ALTER TABLE patients ADD COLUMN IF NOT EXISTS email TEXT;
ALTER TABLE encounters ADD COLUMN IF NOT EXISTS admit_source TEXT;
ALTER TABLE encounters ADD COLUMN IF NOT EXISTS discharge_disposition TEXT;
ALTER TABLE encounters ADD COLUMN IF NOT EXISTS attending_provider_taxonomy TEXT;
ALTER TABLE encounters ADD COLUMN IF NOT EXISTS attending_provider_specialty TEXT;
ALTER TABLE encounters ADD COLUMN IF NOT EXISTS mid_level_provider_id TEXT;
ALTER TABLE encounters ADD COLUMN IF NOT EXISTS mid_level_provider_name TEXT;
ALTER TABLE encounters ADD COLUMN IF NOT EXISTS referring_provider_id TEXT;
ALTER TABLE encounters ADD COLUMN IF NOT EXISTS referring_provider_name TEXT;
ALTER TABLE encounters ADD COLUMN IF NOT EXISTS place_of_service_code TEXT;
ALTER TABLE encounters ADD COLUMN IF NOT EXISTS place_of_service_description TEXT;
ALTER TABLE observations ADD COLUMN IF NOT EXISTS cpt_description TEXT;
ALTER TABLE observations ADD COLUMN IF NOT EXISTS icd_description TEXT;
ALTER TABLE observations ADD COLUMN IF NOT EXISTS diagnosis_type TEXT;
ALTER TABLE observations ADD COLUMN IF NOT EXISTS diagnosis_rank INTEGER;
ALTER TABLE observations ADD COLUMN IF NOT EXISTS performing_provider_id TEXT;
ALTER TABLE observations ADD COLUMN IF NOT EXISTS performing_provider_name TEXT;
ALTER TABLE transactions ADD COLUMN IF NOT EXISTS insurance_plan_name TEXT;
ALTER TABLE transactions ADD COLUMN IF NOT EXISTS member_id TEXT;
ALTER TABLE transactions ADD COLUMN IF NOT EXISTS group_number TEXT;
ALTER TABLE transactions ADD COLUMN IF NOT EXISTS plan_type TEXT;
ALTER TABLE transactions ADD COLUMN IF NOT EXISTS subscriber_relationship TEXT;
ALTER TABLE transactions ADD COLUMN IF NOT EXISTS authorization_number TEXT;
ALTER TABLE transactions ADD COLUMN IF NOT EXISTS billing_provider_npi TEXT;
ALTER TABLE transactions ADD COLUMN IF NOT EXISTS guarantor_name TEXT;
ALTER TABLE transactions ADD COLUMN IF NOT EXISTS guarantor_relationship TEXT;
ALTER TABLE payer_plans ADD COLUMN IF NOT EXISTS active_service_types_json TEXT;
    """
]

def _exec_ddl(db_path: str | None = None):
    resolved_path = _resolve_db_path(db_path)
    with writer(resolved_path) as con:
        for block in DDL:
            # Execute each statement within the block individually
            parts = [s.strip() for s in block.split(";") if s.strip()]
            for stmt in parts:
                # DuckDB accepts statements without trailing semicolons too
                con.execute(stmt)
        logger.info("DDL applied", extra={"extra": {"tables": ["patients","encounters","observations","transactions","messages","orders","coverage_profiles","payer_members","payer_enrollments","payer_plans"]}})

def init_db(db_path: str | None = None) -> str:
    """Initialize schema; returns the resolved DB path."""
    resolved_path = _resolve_db_path(db_path)
    _exec_ddl(resolved_path)
    # The provenance store is additive; existing entity tables stay intact.
    from reality.persistence import init_reality_store
    init_reality_store(resolved_path)
    return resolved_path

# -------------------------
# Upserts (short-lived writers)
# -------------------------
def upsert_patient(p: Dict[str, Any], db_path: str | None = None):
    resolved_path = _resolve_db_path(db_path)
    with writer(resolved_path) as con:
        con.execute("BEGIN")
        con.execute("DELETE FROM patients WHERE patient_id = ?", [p["patient_id"]])
        con.execute(
            """INSERT INTO patients (
                 patient_id, mrn, patient_name, date_of_birth, sex, race, ssn, phone,
                 address, city, state, zip, created_ts
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, COALESCE(?, CURRENT_TIMESTAMP))""",
            [
                p.get("patient_id"),
                p.get("mrn") or p.get("patient_id"),
                p.get("patient_name"), p.get("date_of_birth"),
                p.get("sex"), p.get("race"), p.get("ssn"), p.get("phone"),
                p.get("address"), p.get("city"), p.get("state"),
                p.get("zip_code") or p.get("zip"),
                p.get("created_ts")
            ]
        )
        con.execute("COMMIT")
        con.execute(
            "UPDATE patients SET gender = ?, ethnicity = ?, marital_status = ?, language = ?, employer = ?, email = ? WHERE patient_id = ?",
            [p.get("gender"), p.get("ethnicity"), p.get("marital_status"), p.get("language"), p.get("employer"), p.get("email"), *[p["patient_id"]]],
        )
        logger.info("patient.upsert", extra={"extra": {"patient_id": p.get("patient_id")}})

def upsert_encounter(e: Dict[str, Any], db_path: str | None = None):
    resolved_path = _resolve_db_path(db_path)
    with writer(resolved_path) as con:
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
        con.execute(
            "UPDATE encounters SET admit_source = ?, discharge_disposition = ?, attending_provider_taxonomy = ?, attending_provider_specialty = ?, mid_level_provider_id = ?, mid_level_provider_name = ?, referring_provider_id = ?, referring_provider_name = ?, place_of_service_code = ?, place_of_service_description = ? WHERE encounter_id = ?",
            [e.get("admit_source"), e.get("discharge_disposition"), e.get("attending_provider_taxonomy"), e.get("attending_provider_specialty"), e.get("mid_level_provider_id"), e.get("mid_level_provider_name"), e.get("referring_provider_id"), e.get("referring_provider_name"), e.get("place_of_service_code"), e.get("place_of_service_description"), *[e["encounter_id"]]],
        )
        logger.info("encounter.upsert", extra={"extra": {"encounter_id": e.get("encounter_id")}})

def upsert_observation(o: Dict[str, Any], db_path: str | None = None):
    resolved_path = _resolve_db_path(db_path)
    with writer(resolved_path) as con:
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
        con.execute(
            "UPDATE observations SET cpt_description = ?, icd_description = ?, diagnosis_type = ?, diagnosis_rank = ?, performing_provider_id = ?, performing_provider_name = ? WHERE encounter_id = ? AND observation_id = ?",
            [o.get("cpt_description"), o.get("icd_description"), o.get("diagnosis_type"), o.get("diagnosis_rank"), o.get("performing_provider_id"), o.get("performing_provider_name"), *[o["encounter_id"], o["observation_id"]]],
        )
        logger.info("observation.upsert", extra={"extra": {
            "encounter_id": o.get("encounter_id"),
            "observation_id": o.get("observation_id")
        }})

def upsert_order(row: Dict[str, Any], db_path: str | None = None):
    resolved_path = _resolve_db_path(db_path)
    with writer(resolved_path) as con:
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
        logger.info("order.upsert", extra={"extra": {
            "placer_order_number": row.get("placer_order_number"),
            "filler_order_number": row.get("filler_order_number")
        }})

def upsert_transaction(t: Dict[str, Any], db_path: str | None = None):
    resolved_path = _resolve_db_path(db_path)
    with writer(resolved_path) as con:
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
        con.execute(
            "UPDATE transactions SET insurance_plan_name = ?, member_id = ?, group_number = ?, plan_type = ?, subscriber_relationship = ?, authorization_number = ?, billing_provider_npi = ?, guarantor_name = ?, guarantor_relationship = ? WHERE transaction_id = ?",
            [t.get("insurance_plan_name"), t.get("member_id"), t.get("group_number"), t.get("plan_type"), t.get("subscriber_relationship"), t.get("authorization_number"), t.get("billing_provider_npi"), t.get("guarantor_name"), t.get("guarantor_relationship"), *[t["transaction_id"]]],
        )
        logger.info("transaction.upsert", extra={"extra": {
            "transaction_id": t.get("transaction_id"), "encounter_id": t.get("encounter_id")
        }})

def upsert_coverage_profile(profile: Dict[str, Any], db_path: str | None = None):
    """Persist one instantiated CoverageProfile.

    The table is intentionally not unique on patient_id so later coverage
    history can coexist without a destructive schema change.
    """
    resolved_path = _resolve_db_path(db_path)
    with writer(resolved_path) as con:
        con.execute("BEGIN")
        con.execute(
            "DELETE FROM coverage_profiles WHERE coverage_profile_id = ?",
            [profile["coverage_profile_id"]]
        )
        con.execute(
            """INSERT INTO coverage_profiles (
                 coverage_profile_id, patient_id,
                 employer_id, employer_name,
                 payer_id, payer_name,
                 plan_id, plan_name, plan_type,
                 worker_profile, subscriber_relationship,
                 member_id, group_number, policy_number,
                 effective_start, effective_end,
                 employer_provenance, payer_provenance,
                 employer_payer_provenance, plan_provenance,
                 assignment_seed, created_ts
               ) VALUES (
                 ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                 COALESCE(?, CURRENT_TIMESTAMP)
               )""",
            [
                profile.get("coverage_profile_id"),
                profile.get("patient_id"),
                profile.get("employer_id"),
                profile.get("employer_name"),
                profile.get("payer_id"),
                profile.get("payer_name"),
                profile.get("plan_id"),
                profile.get("plan_name"),
                profile.get("plan_type"),
                profile.get("worker_profile"),
                profile.get("subscriber_relationship"),
                profile.get("member_id"),
                profile.get("group_number"),
                profile.get("policy_number"),
                profile.get("effective_start"),
                profile.get("effective_end"),
                profile.get("employer_provenance"),
                profile.get("payer_provenance"),
                profile.get("employer_payer_provenance"),
                profile.get("plan_provenance"),
                profile.get("assignment_seed"),
                profile.get("created_ts"),
            ]
        )
        con.execute("COMMIT")
        logger.info("coverage_profile.upsert", extra={"extra": {
            "coverage_profile_id": profile.get("coverage_profile_id"),
            "patient_id": profile.get("patient_id"),
            "employer_id": profile.get("employer_id"),
            "payer_id": profile.get("payer_id"),
            "plan_id": profile.get("plan_id"),
        }})


def upsert_payer_member(member: Dict[str, Any], db_path: str | None = None):
    """Persist one payer-local member record."""
    resolved_path = _resolve_db_path(db_path)
    with writer(resolved_path) as con:
        con.execute("BEGIN")
        con.execute(
            "DELETE FROM payer_members WHERE member_record_id = ?",
            [member["member_record_id"]],
        )
        con.execute(
            """INSERT INTO payer_members (
                 member_record_id, payer_id, member_id,
                 first_name, last_name, date_of_birth,
                 administrative_sex, created_ts
               ) VALUES (?, ?, ?, ?, ?, ?, ?, COALESCE(?, CURRENT_TIMESTAMP))""",
            [
                member.get("member_record_id"),
                member.get("payer_id"),
                member.get("member_id"),
                member.get("first_name"),
                member.get("last_name"),
                member.get("date_of_birth"),
                member.get("administrative_sex"),
                member.get("created_ts"),
            ],
        )
        con.execute("COMMIT")
        logger.info("payer_member.upsert", extra={"extra": {
            "member_record_id": member.get("member_record_id"),
            "payer_id": member.get("payer_id"),
            "member_id": member.get("member_id"),
        }})


def upsert_payer_enrollment(enrollment: Dict[str, Any], db_path: str | None = None):
    """Persist one payer-local enrollment record."""
    resolved_path = _resolve_db_path(db_path)
    status = enrollment.get("status")
    if hasattr(status, "value"):
        status = status.value

    with writer(resolved_path) as con:
        con.execute("BEGIN")
        con.execute(
            "DELETE FROM payer_enrollments WHERE enrollment_id = ?",
            [enrollment["enrollment_id"]],
        )
        con.execute(
            """INSERT INTO payer_enrollments (
                 enrollment_id, member_record_id, payer_id, plan_id,
                 group_number, effective_start, effective_end,
                 status, created_ts
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, COALESCE(?, CURRENT_TIMESTAMP))""",
            [
                enrollment.get("enrollment_id"),
                enrollment.get("member_record_id"),
                enrollment.get("payer_id"),
                enrollment.get("plan_id"),
                enrollment.get("group_number"),
                enrollment.get("effective_start"),
                enrollment.get("effective_end"),
                status,
                enrollment.get("created_ts"),
            ],
        )
        con.execute("COMMIT")
        logger.info("payer_enrollment.upsert", extra={"extra": {
            "enrollment_id": enrollment.get("enrollment_id"),
            "member_record_id": enrollment.get("member_record_id"),
            "payer_id": enrollment.get("payer_id"),
        }})


def upsert_payer_plan(plan: Dict[str, Any], db_path: str | None = None):
    """Persist one payer-local plan archetype idempotently."""
    resolved_path = _resolve_db_path(db_path)
    with writer(resolved_path) as con:
        con.execute("BEGIN")
        con.execute(
            "DELETE FROM payer_plans WHERE payer_id = ? AND plan_id = ?",
            [plan["payer_id"], plan["plan_id"]],
        )
        con.execute(
            """INSERT INTO payer_plans (
                 payer_id, plan_id, plan_name, plan_type, created_ts
               ) VALUES (?, ?, ?, ?, COALESCE(?, CURRENT_TIMESTAMP))""",
            [
                plan.get("payer_id"),
                plan.get("plan_id"),
                plan.get("plan_name"),
                plan.get("plan_type"),
                plan.get("created_ts"),
            ],
        )
        con.execute(
            "UPDATE payer_plans SET active_service_types_json = ? WHERE payer_id = ? AND plan_id = ?",
            [json.dumps(list(plan.get("active_service_types") or [])), plan["payer_id"], plan["plan_id"]],
        )
        con.execute("COMMIT")
        logger.info("payer_plan.upsert", extra={"extra": {
            "payer_id": plan.get("payer_id"),
            "plan_id": plan.get("plan_id"),
        }})


def append_message(row: Dict[str, Any], db_path: str | None = None):
    resolved_path = _resolve_db_path(db_path)
    with writer(resolved_path) as con:
        con.execute(
            "INSERT INTO messages VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [
                row.get("run_id"), row.get("message_type"), row.get("control_id"),
                row.get("encounter_id"), row.get("raw_hl7"), row.get("written_path"),
                row.get("ingest_ts"), row.get("ingest_ts").date() if row.get("ingest_ts") else None
            ]
        )
        logger.info("message.append", extra={"extra": {
            "type": row.get("message_type"), "encounter_id": row.get("encounter_id")
        }})

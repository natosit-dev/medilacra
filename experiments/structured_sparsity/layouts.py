from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import duckdb


@dataclass(frozen=True)
class SyntheticCase:
    """One generated patient reality used unchanged by both layouts.

    A case may contain multiple encounters and multiple child facts per
    encounter. The child objects retain their normal MediLacra identifiers,
    so encounter_id remains the link that preserves grain.
    """

    patient: object
    encounters: tuple[object, ...]
    transactions: tuple[object, ...]
    observations: tuple[object, ...]


CANONICAL_DDL = """
CREATE TABLE patients (
    patient_id TEXT PRIMARY KEY,
    patient_name TEXT,
    zip_code TEXT
);

CREATE TABLE encounters (
    encounter_id TEXT PRIMARY KEY,
    patient_id TEXT,
    admit_datetime TEXT,
    hospital_service TEXT,
    attending_provider_id TEXT,
    attending_provider_name TEXT
);

CREATE TABLE observations (
    encounter_id TEXT,
    observation_id TEXT,
    cpt_code TEXT,
    icd_code TEXT,
    completed_time TEXT,
    PRIMARY KEY (encounter_id, observation_id)
);

CREATE TABLE transactions (
    transaction_id TEXT PRIMARY KEY,
    encounter_id TEXT,
    transaction_amount DOUBLE,
    insurance_plan_id TEXT
);
"""


BESPOKE_DDL = """
CREATE TABLE adt_activity (
    patient_id TEXT,
    patient_name TEXT,
    zip_code TEXT,
    encounter_id TEXT,
    admit_datetime TEXT,
    hospital_service TEXT,
    attending_provider_id TEXT,
    attending_provider_name TEXT
);

CREATE TABLE oru_activity (
    patient_id TEXT,
    patient_name TEXT,
    zip_code TEXT,
    encounter_id TEXT,
    admit_datetime TEXT,
    hospital_service TEXT,
    attending_provider_id TEXT,
    attending_provider_name TEXT,
    observation_id TEXT,
    cpt_code TEXT,
    icd_code TEXT,
    completed_time TEXT
);

CREATE TABLE dft_activity (
    patient_id TEXT,
    patient_name TEXT,
    zip_code TEXT,
    encounter_id TEXT,
    admit_datetime TEXT,
    hospital_service TEXT,
    transaction_id TEXT,
    transaction_amount DOUBLE,
    insurance_plan_id TEXT
);

CREATE TABLE patient_activity_report (
    patient_id TEXT,
    patient_name TEXT,
    zip_code TEXT,
    encounter_id TEXT,
    admit_datetime TEXT,
    hospital_service TEXT,
    observation_id TEXT,
    cpt_code TEXT,
    transaction_id TEXT,
    transaction_amount DOUBLE
);

CREATE TABLE provider_activity_report (
    patient_id TEXT,
    encounter_id TEXT,
    attending_provider_id TEXT,
    attending_provider_name TEXT,
    hospital_service TEXT,
    observation_id TEXT,
    cpt_code TEXT
);

CREATE TABLE financial_activity_report (
    patient_id TEXT,
    encounter_id TEXT,
    transaction_id TEXT,
    transaction_amount DOUBLE,
    insurance_plan_id TEXT
);
"""


ZIP_TABLES = {
    "canonical": ["patients"],
    "bespoke": ["adt_activity", "oru_activity", "dft_activity", "patient_activity_report"],
}


LAYOUT_TABLES = {
    "canonical": ["patients", "encounters", "observations", "transactions"],
    "bespoke": [
        "adt_activity",
        "oru_activity",
        "dft_activity",
        "patient_activity_report",
        "provider_activity_report",
        "financial_activity_report",
    ],
}


def _fresh_connection(db_path: Path, ddl: str) -> duckdb.DuckDBPyConnection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()
    con = duckdb.connect(str(db_path))
    con.execute(ddl)
    return con


def create_canonical_db(db_path: Path, cases: Iterable[SyntheticCase]) -> None:
    """Materialize each semantic fact once at its natural grain."""

    con = _fresh_connection(db_path, CANONICAL_DDL)
    try:
        con.execute("BEGIN TRANSACTION")
        for case in cases:
            p = case.patient
            con.execute("INSERT INTO patients VALUES (?, ?, ?)", [p.patient_id, p.patient_name, p.zip_code])
            for e in case.encounters:
                con.execute("INSERT INTO encounters VALUES (?, ?, ?, ?, ?, ?)", [e.encounter_id, e.patient_id, e.admit_datetime, e.hospital_service, e.attending_provider_id, e.attending_provider_name])
            for o in case.observations:
                con.execute("INSERT INTO observations VALUES (?, ?, ?, ?, ?)", [o.encounter_id, o.observation_id, o.cpt_code, o.icd_code, o.completed_time])
            for t in case.transactions:
                con.execute("INSERT INTO transactions VALUES (?, ?, ?, ?)", [t.transaction_id, t.encounter_id, t.transaction_amount, t.insurance_plan_id])
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    finally:
        con.close()


def create_bespoke_db(db_path: Path, cases: Iterable[SyntheticCase]) -> None:
    """Materialize consumer-oriented composites of the same reality."""

    con = _fresh_connection(db_path, BESPOKE_DDL)
    try:
        con.execute("BEGIN TRANSACTION")
        for case in cases:
            p = case.patient
            observations_by_encounter: dict[str, list[object]] = defaultdict(list)
            transactions_by_encounter: dict[str, list[object]] = defaultdict(list)
            for o in case.observations:
                observations_by_encounter[o.encounter_id].append(o)
            for t in case.transactions:
                transactions_by_encounter[t.encounter_id].append(t)

            for e in case.encounters:
                common = [p.patient_id, p.patient_name, p.zip_code, e.encounter_id, e.admit_datetime, e.hospital_service]
                con.execute("INSERT INTO adt_activity VALUES (?, ?, ?, ?, ?, ?, ?, ?)", common + [e.attending_provider_id, e.attending_provider_name])
                encounter_observations = observations_by_encounter[e.encounter_id]
                encounter_transactions = transactions_by_encounter[e.encounter_id]

                for o in encounter_observations:
                    con.execute("INSERT INTO oru_activity VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", common + [e.attending_provider_id, e.attending_provider_name, o.observation_id, o.cpt_code, o.icd_code, o.completed_time])
                    con.execute("INSERT INTO provider_activity_report VALUES (?, ?, ?, ?, ?, ?, ?)", [p.patient_id, e.encounter_id, e.attending_provider_id, e.attending_provider_name, e.hospital_service, o.observation_id, o.cpt_code])

                for t in encounter_transactions:
                    con.execute("INSERT INTO dft_activity VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", common + [t.transaction_id, t.transaction_amount, t.insurance_plan_id])
                    con.execute("INSERT INTO financial_activity_report VALUES (?, ?, ?, ?, ?)", [p.patient_id, e.encounter_id, t.transaction_id, t.transaction_amount, t.insurance_plan_id])

                for o in encounter_observations:
                    for t in encounter_transactions:
                        con.execute("INSERT INTO patient_activity_report VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", common + [o.observation_id, o.cpt_code, t.transaction_id, t.transaction_amount])

        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    finally:
        con.close()


def table_row_counts(db_path: Path, layout: str) -> dict[str, int]:
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        return {table: int(con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]) for table in LAYOUT_TABLES[layout]}
    finally:
        con.close()


def propagate_zip_change(db_path: Path, layout: str, patient_id: str, new_zip: str) -> dict[str, int | str]:
    """Apply one semantic patient ZIP change and count its materialized impact."""
    tables = ZIP_TABLES[layout]
    con = duckdb.connect(str(db_path))
    rows_affected = 0
    tables_affected = 0
    statements = 0
    try:
        con.execute("BEGIN TRANSACTION")
        for table in tables:
            count = int(con.execute(f"SELECT COUNT(*) FROM {table} WHERE patient_id = ?", [patient_id]).fetchone()[0])
            if count:
                tables_affected += 1
                rows_affected += count
            con.execute(f"UPDATE {table} SET zip_code = ? WHERE patient_id = ?", [new_zip, patient_id])
            statements += 1
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    finally:
        con.close()

    return {"layout": layout, "semantic_change": "patient_zip", "tables_affected": tables_affected, "rows_affected": rows_affected, "update_statements": statements}

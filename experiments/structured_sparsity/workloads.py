from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from statistics import median
from time import perf_counter

import duckdb
import pandas as pd
from pandas.testing import assert_frame_equal


@dataclass(frozen=True)
class QueryPlan:
    sql: str
    tables_touched: int
    joins: int = 0
    unions: int = 0


@dataclass(frozen=True)
class Workload:
    name: str
    meaning: str
    canonical: QueryPlan
    bespoke: QueryPlan


WORKLOADS = [
    Workload(
        name="patient_encounter_history",
        meaning="Which encounters did each patient have?",
        canonical=QueryPlan(
            sql="""
                SELECT patient_id, encounter_id, admit_datetime, hospital_service
                FROM encounters
                ORDER BY patient_id, encounter_id
            """,
            tables_touched=1,
        ),
        bespoke=QueryPlan(
            sql="""
                SELECT patient_id, encounter_id, admit_datetime, hospital_service
                FROM adt_activity
                ORDER BY patient_id, encounter_id
            """,
            tables_touched=1,
        ),
    ),
    Workload(
        name="patient_observations",
        meaning="Which observations and diagnoses belong to each patient's encounters?",
        canonical=QueryPlan(
            sql="""
                SELECT e.patient_id, e.encounter_id, o.observation_id, o.cpt_code, o.icd_code
                FROM encounters e
                JOIN observations o ON o.encounter_id = e.encounter_id
                ORDER BY e.patient_id, e.encounter_id, o.observation_id
            """,
            tables_touched=2,
            joins=1,
        ),
        bespoke=QueryPlan(
            sql="""
                SELECT patient_id, encounter_id, observation_id, cpt_code, icd_code
                FROM oru_activity
                ORDER BY patient_id, encounter_id, observation_id
            """,
            tables_touched=1,
        ),
    ),
    Workload(
        name="patient_total_charges",
        meaning="What is the total generated charge for each patient?",
        canonical=QueryPlan(
            sql="""
                SELECT e.patient_id, ROUND(SUM(t.transaction_amount), 2) AS total_charge
                FROM encounters e
                JOIN transactions t ON t.encounter_id = e.encounter_id
                GROUP BY e.patient_id
                ORDER BY e.patient_id
            """,
            tables_touched=2,
            joins=1,
        ),
        bespoke=QueryPlan(
            sql="""
                SELECT patient_id, ROUND(SUM(transaction_amount), 2) AS total_charge
                FROM dft_activity
                GROUP BY patient_id
                ORDER BY patient_id
            """,
            tables_touched=1,
        ),
    ),
    Workload(
        name="provider_clinical_activity",
        meaning="How many observations are associated with each attending provider/service?",
        canonical=QueryPlan(
            sql="""
                SELECT e.attending_provider_id, e.attending_provider_name,
                       e.hospital_service, COUNT(*) AS observation_count
                FROM encounters e
                JOIN observations o ON o.encounter_id = e.encounter_id
                GROUP BY e.attending_provider_id, e.attending_provider_name, e.hospital_service
                ORDER BY e.attending_provider_id, e.attending_provider_name, e.hospital_service
            """,
            tables_touched=2,
            joins=1,
        ),
        bespoke=QueryPlan(
            sql="""
                SELECT attending_provider_id, attending_provider_name,
                       hospital_service, COUNT(*) AS observation_count
                FROM provider_activity_report
                GROUP BY attending_provider_id, attending_provider_name, hospital_service
                ORDER BY attending_provider_id, attending_provider_name, hospital_service
            """,
            tables_touched=1,
        ),
    ),
]


def _timed_query(db_path: Path, sql: str, repeats: int) -> tuple[pd.DataFrame, float]:
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        con.execute(sql).fetchall()
        timings_ms: list[float] = []
        result: pd.DataFrame | None = None
        for _ in range(repeats):
            started = perf_counter()
            result = con.execute(sql).fetchdf()
            timings_ms.append((perf_counter() - started) * 1000.0)
        assert result is not None
        return result, median(timings_ms)
    finally:
        con.close()


def _semantic_match(left: pd.DataFrame, right: pd.DataFrame) -> bool:
    try:
        assert_frame_equal(
            left.reset_index(drop=True),
            right.reset_index(drop=True),
            check_dtype=False,
            check_like=False,
        )
        return True
    except AssertionError:
        return False


def run_workloads(canonical_db: Path, bespoke_db: Path, repeats: int = 5) -> pd.DataFrame:
    rows: list[dict] = []
    for workload in WORKLOADS:
        canonical_result, canonical_ms = _timed_query(canonical_db, workload.canonical.sql, repeats)
        bespoke_result, bespoke_ms = _timed_query(bespoke_db, workload.bespoke.sql, repeats)
        rows.append(
            {
                "workload": workload.name,
                "meaning": workload.meaning,
                "semantic_match": _semantic_match(canonical_result, bespoke_result),
                "result_rows": len(canonical_result),
                "canonical_median_ms": round(canonical_ms, 4),
                "bespoke_median_ms": round(bespoke_ms, 4),
                "canonical_tables_touched": workload.canonical.tables_touched,
                "bespoke_tables_touched": workload.bespoke.tables_touched,
                "canonical_joins": workload.canonical.joins,
                "bespoke_joins": workload.bespoke.joins,
                "canonical_unions": workload.canonical.unions,
                "bespoke_unions": workload.bespoke.unions,
            }
        )
    return pd.DataFrame(rows)

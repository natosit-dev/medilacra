"""Versioned, replayable core synthetic-case materialization in DuckDB.

Keeps independent clinical/payer records and complete source snapshots. Optional
synthetic lab observations are intentionally outside this core persistence contract.
"""
from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
import hashlib
import json
from typing import Any
from types import SimpleNamespace

from utils.db import reader, writer

SCHEMA_VERSION = 1


def _json_value(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return _json_value(asdict(value))
    if isinstance(value, SimpleNamespace):
        return _json_value(vars(value))
    if isinstance(value, Enum):
        return _json_value(value.value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {str(k): _json_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(v) for v in value]
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    raise TypeError(f"Unsupported core snapshot type: {type(value).__name__}")


def encode_snapshot(source_records: dict[str, Any]) -> str:
    """Stable serialization. Never fill missing facts or call synthetic generators."""
    if not source_records or any(not key for key in source_records):
        raise ValueError("A case snapshot requires named source records")
    return json.dumps(
        _json_value(source_records), sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False,
    )


def snapshot_hash(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def init_reality_store(db_path: str) -> None:
    """Additive schema only. Safe on a disposable DB; back up existing DBs first."""
    with writer(db_path) as con:
        con.execute("""CREATE TABLE IF NOT EXISTS simulation_runs (
            run_id TEXT PRIMARY KEY,
            seed BIGINT,
            source_revision TEXT,
            scenario_version TEXT,
            started_at TIMESTAMP,
            options_json TEXT,
            status TEXT NOT NULL DEFAULT 'started'
        )""")
        con.execute("""CREATE TABLE IF NOT EXISTS simulation_cases (
            case_id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL,
            schema_version INTEGER NOT NULL,
            snapshot_json TEXT NOT NULL,
            snapshot_sha256 TEXT NOT NULL,
            materialized_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            status TEXT NOT NULL DEFAULT 'materialized'
        )""")
        con.execute("""CREATE TABLE IF NOT EXISTS semantic_records (
            case_id TEXT NOT NULL,
            record_name TEXT NOT NULL,
            record_owner TEXT NOT NULL,
            record_json TEXT NOT NULL,
            PRIMARY KEY (case_id, record_name)
        )""")
        con.execute("""CREATE TABLE IF NOT EXISTS artifact_index (
            case_id TEXT NOT NULL,
            artifact_type TEXT NOT NULL,
            artifact_path TEXT NOT NULL,
            payload_sha256 TEXT NOT NULL,
            validation_status TEXT NOT NULL DEFAULT 'unverified',
            PRIMARY KEY (case_id, artifact_type, artifact_path)
        )""")


def persist_case(
    *,
    db_path: str,
    run_id: str,
    case_id: str,
    source_records: dict[str, Any],
    owner_by_record: dict[str, str],
    seed: int | None = None,
    source_revision: str = "unrecorded",
    scenario_version: str = "medilacra-provenance-v1",
    options: dict[str, Any] | None = None,
    started_at: datetime | None = None,
) -> str:
    """Persist one whole snapshot and separately queryable owner-owned JSON records.

    Immutable case IDs: replaying identical facts is idempotent; attempts to
    overwrite an existing case with changed facts fail instead of losing history.
    """
    if not run_id or not case_id:
        raise ValueError("run_id and case_id are required")
    if set(owner_by_record) != set(source_records):
        raise ValueError("Every record must have an explicit institutional owner")
    if not all(owner_by_record.values()):
        raise ValueError("Record owner cannot be blank")
    payload = encode_snapshot(source_records)
    digest = snapshot_hash(payload)
    record_values = _json_value(source_records)
    with writer(db_path) as con:
        con.execute("BEGIN")
        existing = con.execute(
            "SELECT snapshot_sha256 FROM simulation_cases WHERE case_id = ?",
            [case_id],
        ).fetchone()
        if existing and existing[0] != digest:
            raise ValueError(f"Immutable case collision for {case_id}")
        run = con.execute(
            "SELECT run_id FROM simulation_runs WHERE run_id = ?", [run_id],
        ).fetchone()
        if not run:
            con.execute(
                """INSERT INTO simulation_runs
                (run_id, seed, source_revision, scenario_version, started_at,
                 options_json, status) VALUES (?, ?, ?, ?, ?, ?, 'started')""",
                [run_id, seed, source_revision, scenario_version, started_at,
                 json.dumps(_json_value(options or {}), sort_keys=True)],
            )
        if not existing:
            con.execute(
                """INSERT INTO simulation_cases
                (case_id, run_id, schema_version, snapshot_json, snapshot_sha256)
                VALUES (?, ?, ?, ?, ?)""",
                [case_id, run_id, SCHEMA_VERSION, payload, digest],
            )
            for name, record in record_values.items():
                con.execute(
                    """INSERT INTO semantic_records
                    (case_id, record_name, record_owner, record_json)
                    VALUES (?, ?, ?, ?)""",
                    [case_id, name, owner_by_record[name],
                     json.dumps(record, sort_keys=True, allow_nan=False)],
                )
        con.execute("COMMIT")
    return digest


def load_case(db_path: str, case_id: str) -> dict[str, Any]:
    """Read the exact semantic values that were materialized; no Faker calls."""
    with reader(db_path=db_path) as con:
        row = con.execute(
            "SELECT snapshot_json, snapshot_sha256 FROM simulation_cases WHERE case_id = ?",
            [case_id],
        ).fetchone()
    if not row:
        raise KeyError(case_id)
    payload, digest = row
    if snapshot_hash(payload) != digest:
        raise ValueError(f"Corrupted snapshot for {case_id}")
    return json.loads(payload)


def register_artifact(
    db_path: str, case_id: str, artifact_type: str, artifact_path: str,
    content: str, *, validation_status: str = "unverified",
) -> None:
    if not artifact_type or not artifact_path:
        raise ValueError("Artifact type and path required")
    with writer(db_path) as con:
        con.execute(
            """INSERT INTO artifact_index
            (case_id, artifact_type, artifact_path, payload_sha256, validation_status)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT (case_id, artifact_type, artifact_path)
            DO UPDATE SET payload_sha256=excluded.payload_sha256,
                          validation_status=excluded.validation_status""",
            [case_id, artifact_type, artifact_path,
             snapshot_hash(content), validation_status],
        )


def finish_case(db_path: str, case_id: str) -> None:
    with writer(db_path) as con:
        con.execute(
            "UPDATE simulation_cases SET status = 'completed' WHERE case_id = ?",
            [case_id],
        )

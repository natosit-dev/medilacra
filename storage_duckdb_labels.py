# storage_duckdb_labels.py

import os
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any

import duckdb

DEFAULT_DB_PATH = str(Path("data") / "labels.duckdb")


def init_db(db_path: str = DEFAULT_DB_PATH) -> None:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(db_path)
    # Very simple v0 schema; you can normalize later
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS labels (
            label_id       BIGINT,
            created_at     TIMESTAMP,
            case_id        VARCHAR,
            coder_id       VARCHAR,
            service_line   VARCHAR,
            message_type   VARCHAR,
            backend        VARCHAR,
            icd_threshold  DOUBLE,
            cpt_threshold  DOUBLE,
            icd_selected   VARCHAR,
            cpt_selected   VARCHAR,
            icd_suggested  VARCHAR,
            cpt_suggested  VARCHAR,
            rationale_text VARCHAR,
            needs_query    BOOLEAN,
            documentation_missing    BOOLEAN,
            insufficient_detail      BOOLEAN,
            conflicting_information  BOOLEAN,
            note_text      VARCHAR
        )
        """
    )
    con.close()


def append_label(row: Dict[str, Any], db_path: str = DEFAULT_DB_PATH) -> None:
    con = duckdb.connect(db_path)
    con.execute(
        """
        INSERT INTO labels (
            created_at,
            case_id,
            coder_id,
            service_line,
            message_type,
            backend,
            icd_threshold,
            cpt_threshold,
            icd_selected,
            cpt_selected,
            icd_suggested,
            cpt_suggested,
            rationale_text,
            needs_query,
            documentation_missing,
            insufficient_detail,
            conflicting_information,
            note_text
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            datetime.utcnow(),
            row.get("case_id"),
            row.get("coder_id"),
            row.get("service_line"),
            row.get("message_type"),
            row.get("backend"),
            row.get("icd_threshold"),
            row.get("cpt_threshold"),
            "|".join(row.get("icd_selected", [])),
            "|".join(row.get("cpt_selected", [])),
            "|".join(row.get("icd_suggested", [])),
            "|".join(row.get("cpt_suggested", [])),
            row.get("rationale_text") or "",
            bool(row.get("needs_query", False)),
            bool(row.get("documentation_missing", False)),
            bool(row.get("insufficient_detail", False)),
            bool(row.get("conflicting_information", False)),
            row.get("note_text") or "",
        ],
    )
    con.close()

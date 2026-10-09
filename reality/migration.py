"""Backup guard for additive DuckDB migrations on existing local databases."""
from __future__ import annotations

from pathlib import Path
import shutil

import duckdb


def preserve_pre_migration_db(db_path: str) -> Path | None:
    """Take a one-time verified snapshot before a refactor-era schema migration.

    Requires no active DuckDB writer (read-only open enforces that in DuckDB).
    New empty DBs need no backup. Backup is beside the source, never committed.
    """
    target = Path(db_path).expanduser().resolve()
    if not target.is_file() or target.stat().st_size == 0:
        return None
    backup = target.with_name(target.name + ".pre-reality-refactor.bak")
    if backup.exists():
        return backup
    # This must fail rather than copy a DB while a different process is writing.
    with duckdb.connect(str(target), read_only=True) as con:
        con.execute("SELECT 1").fetchone()
    shutil.copy2(target, backup)
    try:
        with duckdb.connect(str(backup), read_only=True) as con:
            con.execute("SELECT 1").fetchone()
    except Exception:
        backup.unlink(missing_ok=True)
        raise
    return backup

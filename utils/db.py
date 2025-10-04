# utils/db.py
import os
import threading
from contextlib import contextmanager
from typing import Optional

import duckdb
from utils.log_utils import get_logger

logger = get_logger(name="MediLacra", context={"component": "db", "module": "utils.db", "env": "dev"})
_lock = threading.Lock()


def _normalize_path(db_path: str) -> str:
    """Resolve and ensure the parent directory for a DuckDB file exists."""
    absolute = os.path.abspath(db_path)
    parent = os.path.dirname(absolute)
    if parent:
        os.makedirs(parent, exist_ok=True)
    return absolute

def get_db_path() -> str:

    """Return the active DuckDB path.

    The path can be overridden by setting the ``MEDILACRA_DB_PATH`` environment
    variable to an absolute or relative file location. When unset, the database
    is stored in ``./data/medilacra.duckdb`` relative to the current working
    directory.
    """
    override = os.getenv("MEDILACRA_DB_PATH")
    if override:
        return _normalize_path(override)
    # Keep it stable and clean (avoid 'C:\\Data Generator.' style paths)
    base = os.path.abspath(os.path.join(os.getcwd(), "data"))
    os.makedirs(base, exist_ok=True)
    db = os.path.join(base, "medilacra.duckdb")
    return db

@contextmanager
def writer(db_path: Optional[str] = None):
    """Exclusive writer. Opens, commits, and closes every time (releases lock)."""
    db = _normalize_path(db_path) if db_path else get_db_path()
    with _lock:
        logger.info("duckdb.writer.open", extra={"extra": {"db": db}})
        con = duckdb.connect(db)
        try:
            yield con
            con.commit()
        finally:
            try:
                con.close()
            finally:
                logger.info("duckdb.writer.close", extra={"extra": {"db": db}})

@contextmanager
def reader(read_only: bool = True, db_path: Optional[str] = None):
    """Reader connection; closed after use. Safe for quick selects."""
    db = _normalize_path(db_path) if db_path else get_db_path()
    logger.info("duckdb.reader.open", extra={"extra": {"db": db, "read_only": read_only}})
    con = duckdb.connect(db, read_only=read_only)
    try:
        yield con
    finally:
        try:
            con.close()
        finally:
            logger.info("duckdb.reader.close", extra={"extra": {"db": db}})

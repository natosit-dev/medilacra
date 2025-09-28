# utils/db.py
import os
import threading
from contextlib import contextmanager

import duckdb
from utils.log_utils import get_logger

logger = get_logger(name="MediLacra", context={"component": "db", "module": "utils.db", "env": "dev"})
_lock = threading.Lock()

def get_db_path() -> str:
    # Keep it stable and clean (avoid 'C:\\Data Generator.' style paths)
    base = os.path.abspath(os.path.join(os.getcwd(), "data"))
    os.makedirs(base, exist_ok=True)
    db = os.path.join(base, "medilacra.duckdb")
    return db

@contextmanager
def writer():
    """Exclusive writer. Opens, commits, and closes every time (releases lock)."""
    db = get_db_path()
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
def reader(read_only: bool = True):
    """Reader connection; closed after use. Safe for quick selects."""
    db = get_db_path()
    logger.info("duckdb.reader.open", extra={"extra": {"db": db, "read_only": read_only}})
    con = duckdb.connect(db, read_only=read_only)
    try:
        yield con
    finally:
        try:
            con.close()
        finally:
            logger.info("duckdb.reader.close", extra={"extra": {"db": db}})

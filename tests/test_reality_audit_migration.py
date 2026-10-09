"""Read-only DB auditing and migration safety checks."""
from pathlib import Path

import pytest

from reality.migration import preserve_pre_migration_db
from scripts.audit_reality_duckdb import audit_database
from storage_duckdb_entities import init_db, upsert_patient


def test_audit_reads_metadata_not_patient_values(tmp_path):
    path = str(tmp_path / "test.duckdb")
    init_db(path)
    upsert_patient({
        "patient_id": "PAT-SECRET-TO-OMIT",
        "patient_name": "INTERNAL TEST PATIENT",
        "date_of_birth": "1980-01-01",
        "email": "private@example.invalid",
    }, db_path=path)
    result = audit_database(path)
    assert result["read_only"] is True
    assert result["contains_row_values"] is False
    assert result["tables"]["patients"]["row_count"] == 1
    assert result["tables"]["patients"]["missing_model_fields"] == []
    assert result["tables"]["patients"]["null_counts"]["email"] == 0
    text = str(result)
    assert "private@example.invalid" not in text
    assert "INTERNAL TEST PATIENT" not in text
    with pytest.raises(FileNotFoundError):
        audit_database(str(tmp_path / "does_not_exist.duckdb"))
    assert not (tmp_path / "does_not_exist.duckdb").exists()


def test_existing_duckdb_is_backed_up_once_before_migration(tmp_path):
    path = str(tmp_path / "legacy.duckdb")
    init_db(path)
    upsert_patient({"patient_id": "PAT-BACKUP"}, db_path=path)
    backup = preserve_pre_migration_db(path)
    assert backup == Path(path + ".pre-reality-refactor.bak")
    assert backup.is_file()
    assert audit_database(str(backup))["tables"]["patients"]["row_count"] == 1
    assert preserve_pre_migration_db(path) == backup

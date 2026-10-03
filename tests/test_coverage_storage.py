from storage_duckdb_entities import (
    init_db,
    upsert_coverage_profile,
)
from utils import db


def _coverage(profile_id: str, patient_id: str, plan_id: str):
    return {
        "coverage_profile_id": profile_id,
        "patient_id": patient_id,
        "employer_id": "STARBUCKS",
        "employer_name": "Starbucks Corporation",
        "payer_id": "AETNA",
        "payer_name": "Aetna",
        "plan_id": plan_id,
        "plan_name": "Standard PPO",
        "plan_type": "PPO",
        "worker_profile": "DEFAULT_FULL_TIME_EMPLOYEE",
        "subscriber_relationship": "SELF",
        "member_id": f"MEM-{profile_id}",
        "group_number": "GRP-STARBUCKS-000001",
        "policy_number": f"POL-{profile_id}",
        "effective_start": "2026-01-01",
        "effective_end": "2026-12-31",
        "employer_provenance": "researched",
        "payer_provenance": "researched",
        "employer_payer_provenance": "synthetic",
        "plan_provenance": "synthetic",
        "assignment_seed": "12345",
    }


def test_init_db_creates_coverage_profiles_table(tmp_path):
    db_path = tmp_path / "medilacra.duckdb"
    init_db(db_path=str(db_path))

    with db.reader(db_path=str(db_path)) as con:
        tables = {
            name
            for (name,) in con.execute(
                "SHOW TABLES"
            ).fetchall()
        }

    assert "coverage_profiles" in tables


def test_coverage_profile_round_trip_and_patient_history(tmp_path):
    db_path = tmp_path / "medilacra.duckdb"
    init_db(db_path=str(db_path))

    first = _coverage(
        "COV-ONE",
        "PAT-HISTORY-001",
        "STANDARD_PPO",
    )
    second = _coverage(
        "COV-TWO",
        "PAT-HISTORY-001",
        "STANDARD_HMO",
    )
    second["plan_name"] = "Standard HMO"
    second["plan_type"] = "HMO"
    second["effective_start"] = "2027-01-01"
    second["effective_end"] = "2027-12-31"

    upsert_coverage_profile(
        first,
        db_path=str(db_path),
    )
    upsert_coverage_profile(
        second,
        db_path=str(db_path),
    )

    with db.reader(db_path=str(db_path)) as con:
        rows = con.execute(
            """
            SELECT
              coverage_profile_id,
              patient_id,
              employer_id,
              payer_id,
              plan_id,
              member_id,
              effective_start,
              effective_end
            FROM coverage_profiles
            WHERE patient_id = ?
            ORDER BY coverage_profile_id
            """,
            ["PAT-HISTORY-001"],
        ).fetchall()

    assert len(rows) == 2
    assert rows[0][0] == "COV-ONE"
    assert rows[1][0] == "COV-TWO"
    assert rows[0][1] == "PAT-HISTORY-001"
    assert rows[0][2] == "STARBUCKS"
    assert rows[0][3] == "AETNA"
    assert rows[0][4] == "STANDARD_PPO"
    assert rows[0][5] == "MEM-COV-ONE"
    assert str(rows[0][6]) == "2026-01-01"
    assert str(rows[0][7]) == "2026-12-31"


def test_upsert_replaces_same_coverage_profile_id(tmp_path):
    db_path = tmp_path / "medilacra.duckdb"
    init_db(db_path=str(db_path))

    profile = _coverage(
        "COV-REPLACE",
        "PAT-REPLACE-001",
        "STANDARD_PPO",
    )
    upsert_coverage_profile(
        profile,
        db_path=str(db_path),
    )

    profile["payer_id"] = "UHC"
    profile["payer_name"] = "UnitedHealthcare"

    upsert_coverage_profile(
        profile,
        db_path=str(db_path),
    )

    with db.reader(db_path=str(db_path)) as con:
        rows = con.execute(
            """
            SELECT payer_id
            FROM coverage_profiles
            WHERE coverage_profile_id = ?
            """,
            ["COV-REPLACE"],
        ).fetchall()

    assert rows == [("UHC",)]

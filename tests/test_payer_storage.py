from payer.models import (
    BenefitPlan,
    EnrollmentRecord,
    EnrollmentStatus,
    MemberRecord,
)
from storage_duckdb_entities import (
    init_db,
    upsert_payer_enrollment,
    upsert_payer_member,
    upsert_payer_plan,
)
from utils import db


def _payload(obj):
    return obj.__dict__.copy()


def test_init_db_creates_payer_tables(tmp_path):
    db_path = tmp_path / "payer.duckdb"
    init_db(db_path=str(db_path))

    with db.reader(db_path=str(db_path)) as con:
        tables = {
            name
            for (name,) in con.execute(
                "SHOW TABLES"
            ).fetchall()
        }

    assert {
        "payer_members",
        "payer_enrollments",
        "payer_plans",
    }.issubset(tables)


def test_payer_primitives_round_trip_and_plan_upsert_is_idempotent(tmp_path):
    db_path = tmp_path / "payer.duckdb"
    init_db(db_path=str(db_path))

    member = MemberRecord(
        member_record_id="PM-001",
        payer_id="KAISER",
        member_id="MEM-001",
        first_name="DEVIN",
        last_name="KELLEY",
        date_of_birth="1949-01-16",
        administrative_sex="M",
    )
    enrollment = EnrollmentRecord(
        enrollment_id="PE-001",
        member_record_id=member.member_record_id,
        payer_id=member.payer_id,
        plan_id="STANDARD_PPO",
        group_number="GRP-CVS-398915",
        effective_start="2026-01-01",
        effective_end="2026-12-31",
        status=EnrollmentStatus.ACTIVE,
    )
    plan = BenefitPlan(
        payer_id="KAISER",
        plan_id="STANDARD_PPO",
        plan_name="Standard PPO",
        plan_type="PPO",
    )

    upsert_payer_member(
        _payload(member),
        db_path=str(db_path),
    )
    upsert_payer_enrollment(
        _payload(enrollment),
        db_path=str(db_path),
    )
    upsert_payer_plan(
        _payload(plan),
        db_path=str(db_path),
    )
    upsert_payer_plan(
        _payload(plan),
        db_path=str(db_path),
    )

    with db.reader(db_path=str(db_path)) as con:
        member_row = con.execute(
            """
            SELECT
              payer_id,
              member_id,
              first_name,
              last_name,
              date_of_birth,
              administrative_sex
            FROM payer_members
            WHERE member_record_id = ?
            """,
            [member.member_record_id],
        ).fetchone()

        enrollment_row = con.execute(
            """
            SELECT
              member_record_id,
              payer_id,
              plan_id,
              group_number,
              effective_start,
              effective_end,
              status
            FROM payer_enrollments
            WHERE enrollment_id = ?
            """,
            [enrollment.enrollment_id],
        ).fetchone()

        plan_rows = con.execute(
            """
            SELECT payer_id, plan_id, plan_name, plan_type
            FROM payer_plans
            WHERE payer_id = ? AND plan_id = ?
            """,
            [plan.payer_id, plan.plan_id],
        ).fetchall()

    assert member_row[:4] == (
        "KAISER",
        "MEM-001",
        "DEVIN",
        "KELLEY",
    )
    assert str(member_row[4]) == "1949-01-16"
    assert member_row[5] == "M"

    assert enrollment_row[:4] == (
        "PM-001",
        "KAISER",
        "STANDARD_PPO",
        "GRP-CVS-398915",
    )
    assert str(enrollment_row[4]) == "2026-01-01"
    assert str(enrollment_row[5]) == "2026-12-31"
    assert enrollment_row[6] == "ACTIVE"

    assert plan_rows == [
        (
            "KAISER",
            "STANDARD_PPO",
            "Standard PPO",
            "PPO",
        )
    ]

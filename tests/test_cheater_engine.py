from dataclasses import replace

import pandas as pd
import pytest

from cheater_engine import (
    EXERCISES,
    build_cohort,
    cohort_counts,
    execute_python,
    execute_sql,
    render_python,
    render_sql,
)


def _assert_same_rows(left: pd.DataFrame, right: pd.DataFrame) -> None:
    assert set(left.columns) == set(right.columns)
    columns = sorted(left.columns)

    left_normalized = (
        left[columns]
        .sort_values(columns, kind="stable")
        .reset_index(drop=True)
    )
    right_normalized = (
        right[columns]
        .sort_values(columns, kind="stable")
        .reset_index(drop=True)
    )

    pd.testing.assert_frame_equal(
        left_normalized,
        right_normalized,
        check_dtype=False,
    )


def test_cohort_shape():
    cohort = build_cohort()

    assert cohort_counts(cohort) == {
        "patients": 100,
        "encounters": 200,
        "orders": 200,
        "observations": 200,
        "transactions": 200,
    }
    assert cohort["encounters"].groupby("patient_id").size().eq(2).all()
    assert cohort["orders"]["encounter_id"].nunique() == 200
    assert cohort["observations"]["encounter_id"].nunique() == 200
    assert cohort["transactions"]["encounter_id"].nunique() == 200


@pytest.mark.parametrize(
    "kwargs",
    [
        {"n_patients": 0},
        {"encounters_per_patient": 0},
    ],
)
def test_cohort_rejects_empty_dimensions(kwargs):
    with pytest.raises(ValueError):
        build_cohort(**kwargs)


@pytest.mark.parametrize("exercise_key", list(EXERCISES))
def test_generated_sql_and_python_materialize_same_result(exercise_key):
    cohort = build_cohort()
    spec = EXERCISES[exercise_key]

    sql_result = execute_sql(render_sql(spec), cohort, spec)
    python_result = execute_python(render_python(spec), cohort, spec)

    _assert_same_rows(sql_result, python_result)


def test_latest_per_group_default_is_one_latest_row_per_patient():
    cohort = build_cohort()
    spec = EXERCISES["latest_per_group"]

    result = execute_sql(render_sql(spec), cohort, spec)
    expected = (
        cohort["encounters"]
        .groupby("patient_id")["admit_ts"]
        .max()
        .sort_index()
    )
    actual = result.set_index("patient_id")["admit_ts"].sort_index()

    assert len(result) == 100
    assert actual.equals(expected)
    assert "ROW_NUMBER()" in render_sql(spec)
    assert "EXCLUDE" not in render_sql(spec)


def test_top_per_group_renderers_honor_direction_and_limit():
    cohort = build_cohort()
    spec = replace(
        EXERCISES["latest_per_group"],
        order_direction="ASC",
        limit=2,
    )

    sql_result = execute_sql(render_sql(spec), cohort, spec)
    python_result = execute_python(render_python(spec), cohort, spec)

    assert len(sql_result) == 200
    assert len(python_result) == 200
    assert "ORDER BY admit_ts ASC" in render_sql(spec)
    assert "reverse=False" in render_python(spec)

    _assert_same_rows(sql_result, python_result)


def test_missing_exercise_does_not_mutate_base_cohort():
    cohort = build_cohort()
    base_rows = len(cohort["encounters"])
    spec = EXERCISES["existence_quality_missing"]

    result = execute_sql(render_sql(spec), cohort, spec)

    assert len(result) == 1
    assert len(cohort["encounters"]) == base_rows


def test_duplicate_exercise_does_not_mutate_base_cohort():
    cohort = build_cohort()
    base_rows = len(cohort["encounters"])
    spec = EXERCISES["existence_quality_duplicates"]

    result = execute_python(render_python(spec), cohort, spec)

    assert len(result) == 1
    assert result.iloc[0]["row_count"] == 2
    assert len(cohort["encounters"]) == base_rows


def test_edited_sql_changes_output():
    cohort = build_cohort()
    spec = EXERCISES["latest_per_group"]

    latest = execute_sql(render_sql(spec), cohort, spec)
    earliest_sql = render_sql(spec).replace(
        "ORDER BY admit_ts DESC",
        "ORDER BY admit_ts ASC",
    )
    earliest = execute_sql(earliest_sql, cohort, spec)

    assert len(latest) == 100
    assert len(earliest) == 100
    assert not latest["encounter_id"].equals(earliest["encounter_id"])


def test_edited_python_changes_output():
    cohort = build_cohort()
    spec = EXERCISES["filter"]

    outpatient = execute_python(render_python(spec), cohort, spec)
    inpatient_code = render_python(spec).replace("OUTPATIENT", "INPATIENT")
    inpatient = execute_python(inpatient_code, cohort, spec)

    assert set(outpatient["patient_class"]) == {"OUTPATIENT"}
    assert set(inpatient["patient_class"]) == {"INPATIENT"}
    assert not outpatient["encounter_id"].equals(inpatient["encounter_id"])


def test_python_execution_uses_disposable_table_copies():
    cohort = build_cohort()
    spec = EXERCISES["filter"]

    result = execute_python(
        "encounters.clear()\nresult = encounters",
        cohort,
        spec,
    )

    assert result.empty
    assert len(cohort["encounters"]) == 200


def test_sql_execution_rejects_writes():
    cohort = build_cohort()
    spec = EXERCISES["filter"]

    with pytest.raises(ValueError, match="read-only"):
        execute_sql("DELETE FROM encounters", cohort, spec)


def test_sql_execution_rejects_multiple_statements():
    cohort = build_cohort()
    spec = EXERCISES["filter"]

    with pytest.raises(ValueError, match="one SQL statement"):
        execute_sql(
            "SELECT * FROM encounters; SELECT * FROM patients",
            cohort,
            spec,
        )


def test_python_requires_result_variable():
    cohort = build_cohort()
    spec = EXERCISES["filter"]

    with pytest.raises(ValueError, match="result"):
        execute_python("x = len(encounters)", cohort, spec)

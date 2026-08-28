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
    run_pandas,
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


def test_filter():
    result = run_pandas(EXERCISES["filter"], build_cohort())
    assert not result.empty
    assert set(result["patient_class"]) == {"OUTPATIENT"}
    assert "WHERE patient_class" in render_sql(EXERCISES["filter"])


def test_group_aggregate():
    result = run_pandas(EXERCISES["group_aggregate"], build_cohort())
    assert len(result) == 100
    assert result["encounter_count"].eq(2).all()


def test_join():
    result = run_pandas(EXERCISES["join"], build_cohort())
    assert len(result) == 200
    assert result["patient_name"].notna().all()


def test_latest_per_group():
    cohort = build_cohort()
    result = run_pandas(EXERCISES["latest_per_group"], cohort)
    assert len(result) == 100
    expected = cohort["encounters"].groupby("patient_id")["admit_ts"].max().sort_index()
    actual = result.set_index("patient_id")["admit_ts"].sort_index()
    assert actual.equals(expected)
    assert "ROW_NUMBER()" in render_sql(EXERCISES["latest_per_group"])
    assert "latest = {}" in render_python(EXERCISES["latest_per_group"])


def test_missing_exercise_uses_view_not_base_cohort():
    cohort = build_cohort()
    base_rows = len(cohort["encounters"])
    result = run_pandas(EXERCISES["existence_quality_missing"], cohort)
    assert len(result) == 1
    assert len(cohort["encounters"]) == base_rows


def test_duplicate_exercise_uses_view_not_base_cohort():
    cohort = build_cohort()
    base_rows = len(cohort["encounters"])
    result = run_pandas(EXERCISES["existence_quality_duplicates"], cohort)
    assert len(result) == 1
    assert result.iloc[0]["row_count"] == 2
    assert len(cohort["encounters"]) == base_rows


@pytest.mark.parametrize("exercise_key", list(EXERCISES))
def test_generated_sql_executes(exercise_key):
    cohort = build_cohort()
    spec = EXERCISES[exercise_key]
    result = execute_sql(render_sql(spec), cohort, spec)
    assert isinstance(result, pd.DataFrame)


@pytest.mark.parametrize("exercise_key", list(EXERCISES))
def test_generated_python_executes(exercise_key):
    cohort = build_cohort()
    spec = EXERCISES[exercise_key]
    result = execute_python(render_python(spec), cohort, spec)
    assert isinstance(result, pd.DataFrame)


def test_edited_sql_changes_output():
    cohort = build_cohort()
    spec = EXERCISES["latest_per_group"]

    latest = execute_sql(render_sql(spec), cohort, spec)
    earliest_sql = render_sql(spec).replace("ORDER BY admit_ts DESC", "ORDER BY admit_ts ASC")
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


def test_sql_execution_rejects_writes():
    cohort = build_cohort()
    spec = EXERCISES["filter"]
    with pytest.raises(ValueError, match="read-only"):
        execute_sql("DELETE FROM encounters", cohort, spec)


def test_python_requires_result_variable():
    cohort = build_cohort()
    spec = EXERCISES["filter"]
    with pytest.raises(ValueError, match="result"):
        execute_python("x = len(encounters)", cohort, spec)

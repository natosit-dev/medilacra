from cheater_engine import (
    EXERCISES,
    build_cohort,
    cohort_counts,
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

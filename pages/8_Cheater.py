import streamlit as st

from cheater_engine import (
    EXERCISES,
    FAMILY_OPTIONS,
    SCHEMA,
    build_cohort,
    cohort_counts,
    render_python,
    render_sql,
    run_pandas,
    semantic_steps,
)

st.set_page_config(page_title="MediLacra — Cheater", layout="wide")
st.title("😈 MediLacra — Cheater")
st.caption(
    "Deterministic interview translator: identify the data shape first, "
    "then materialize it as SQL or plain Python."
)


@st.cache_data
def load_cohort():
    return build_cohort(n_patients=100, encounters_per_patient=2, seed=42)


cohort = load_cohort()
counts = cohort_counts(cohort)

with st.sidebar:
    st.header("Problem Shape")
    family = st.selectbox("Question family", list(FAMILY_OPTIONS.keys()))
    exercise_keys = FAMILY_OPTIONS[family]
    exercise_key = st.selectbox(
        "Exercise",
        exercise_keys,
        format_func=lambda key: EXERCISES[key].label,
    )
    spec = EXERCISES[exercise_key]

    st.markdown("---")
    st.subheader("Cohort")
    st.write("100 patients × 2 encounters")
    for table, count in counts.items():
        st.caption(f"{table}: {count}")

st.subheader("1. Normalize the problem")
for idx, step in enumerate(semantic_steps(spec), start=1):
    st.write(f"{idx}. {step}")

with st.expander("Data dictionary", expanded=False):
    selected_table = st.selectbox("Table", list(SCHEMA.keys()))
    st.code("\n".join(SCHEMA[selected_table]))
    st.dataframe(cohort[selected_table].head(10), use_container_width=True)

st.subheader("2. Materialize the transformation")
sql_col, py_col = st.columns(2)
with sql_col:
    st.markdown("#### SQL")
    st.code(render_sql(spec), language="sql")
with py_col:
    st.markdown("#### Plain Python")
    st.code(render_python(spec), language="python")

st.subheader("3. See the result")
result = run_pandas(spec, cohort)
base_source = spec.source_a.replace("_exercise", "")
input_rows = len(cohort[base_source]) if base_source in cohort else len(cohort["encounters"])
metric_a, metric_b = st.columns(2)
metric_a.metric("Input rows", input_rows)
metric_b.metric("Output rows", len(result))
st.dataframe(result.head(50), use_container_width=True)

st.caption(
    "The preview is executed with pandas only to verify the transformation. "
    "The displayed answers remain SQL and plain Python."
)

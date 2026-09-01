import streamlit as st
from code_editor import code_editor

from cheater_engine import (
    EXERCISES,
    FAMILY_OPTIONS,
    SCHEMA,
    build_cohort,
    cohort_counts,
    execute_python,
    execute_sql,
    render_python,
    render_sql,
    semantic_steps,
)

st.set_page_config(page_title="MediLacra — Cheater", layout="wide")
st.title("😈 MediLacra — Cheater")
st.caption(
    "Deterministic interview translator: identify the data shape, inspect a "
    "generated starting point, then edit and execute the actual SQL or Python."
)


RUN_BUTTON = [{
    "name": "Run",
    "feather": "Play",
    "primary": True,
    "hasText": True,
    "showWithIcon": True,
    "commands": ["submit"],
    "style": {"bottom": "0.44rem", "right": "0.4rem"},
}]

EDITOR_OPTIONS = {
    "wrap": True,
    "showLineNumbers": True,
    "tabSize": 4,
}


@st.cache_data
def load_cohort():
    return build_cohort(
        n_patients=100,
        encounters_per_patient=2,
        seed=42,
    )


def _handle_submission(response, language, spec, cohort):
    """Execute one editor submission and store the visible result."""
    if not response or response.get("type") != "submit":
        return

    response_id = response.get("id")
    processed_key = f"cheater_processed_{language}_{spec.key}"

    if (
        response_id is not None
        and st.session_state.get(processed_key) == response_id
    ):
        return

    code = response.get("text", "")

    try:
        if language == "SQL":
            result = execute_sql(code, cohort, spec)
        else:
            result = execute_python(code, cohort, spec)

        st.session_state["cheater_execution"] = {
            "exercise": spec.key,
            "language": language,
            "code": code,
            "result": result,
            "error": None,
        }
    except Exception as exc:
        st.session_state["cheater_execution"] = {
            "exercise": spec.key,
            "language": language,
            "code": code,
            "result": None,
            "error": str(exc),
        }

    if response_id is not None:
        st.session_state[processed_key] = response_id


cohort = load_cohort()
counts = cohort_counts(cohort)

with st.sidebar:
    st.header("Problem Shape")
    family = st.selectbox(
        "Question family",
        list(FAMILY_OPTIONS.keys()),
    )
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

if st.session_state.get("cheater_active_exercise") != exercise_key:
    st.session_state["cheater_active_exercise"] = exercise_key
    st.session_state.pop("cheater_execution", None)

st.subheader("1. Normalize the problem")
for idx, step in enumerate(semantic_steps(spec), start=1):
    st.write(f"{idx}. {step}")

with st.expander("Data dictionary", expanded=False):
    selected_table = st.selectbox(
        "Table",
        list(SCHEMA.keys()),
    )
    st.code("\n".join(SCHEMA[selected_table]))
    st.dataframe(
        cohort[selected_table].head(10),
        use_container_width=True,
    )

st.subheader("2. Materialize the transformation")
st.caption(
    "These are generated starting points, not fixed answers. Edit either one "
    "and press Run inside that editor; the submitted code becomes the "
    "transformation that produces the result."
)

sql_col, py_col = st.columns(2)

with sql_col:
    st.markdown("#### SQL")
    sql_response = code_editor(
        render_sql(spec),
        lang="sql",
        buttons=RUN_BUTTON,
        options=EDITOR_OPTIONS,
        allow_reset=True,
        key=f"cheater_sql_{exercise_key}",
    )
    _handle_submission(
        sql_response,
        "SQL",
        spec,
        cohort,
    )

with py_col:
    st.markdown("#### Plain Python")
    st.caption(
        "Table names are available as lists of dictionaries. "
        "Assign final output to `result`."
    )
    python_response = code_editor(
        render_python(spec),
        lang="python",
        buttons=RUN_BUTTON,
        options=EDITOR_OPTIONS,
        allow_reset=True,
        key=f"cheater_python_{exercise_key}",
    )
    _handle_submission(
        python_response,
        "Python",
        spec,
        cohort,
    )

st.subheader("3. See the executed result")
execution = st.session_state.get("cheater_execution")

if not execution or execution.get("exercise") != exercise_key:
    st.info(
        "Edit either materialization—or leave it alone—and press Run "
        "inside that editor."
    )
elif execution.get("error"):
    st.error(
        f"{execution['language']} execution failed: "
        f"{execution['error']}"
    )
else:
    result = execution["result"]
    metric_a, metric_b = st.columns(2)
    metric_a.metric("Executed language", execution["language"])
    metric_b.metric("Output rows", len(result))

    st.dataframe(
        result,
        use_container_width=True,
    )

    with st.expander("Executed code", expanded=False):
        language = (
            "sql"
            if execution["language"] == "SQL"
            else "python"
        )
        st.code(
            execution["code"],
            language=language,
        )

st.caption(
    "Execution is local and disposable. SQL runs read-only against an "
    "in-memory DuckDB cohort. Python runs against copies of the same "
    "exercise tables with imports disabled."
)

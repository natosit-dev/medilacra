from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parents[1]
B_ROOT = REPO_ROOT / "experiments" / "method_b_workflow_reconstruction"
C_ROOT = REPO_ROOT / "experiments" / "method_c_workflow_validation"
DETAIL_PATH = B_ROOT / "output" / "workflow_detail.csv"
VALIDATION_PATH = C_ROOT / "output" / "validation_results.csv"
HISTORY_PATH = C_ROOT / "output" / "validation_history.csv"
MODEL_DOC = B_ROOT / "RECONSTRUCTED_MODEL.md"
CORRECTED_NOTES = C_ROOT / "CORRECTED_SOURCE_NOTES.md"


def build_evidence() -> None:
    subprocess.run(
        [sys.executable, str(C_ROOT / "run_validation.py")],
        check=True,
        cwd=REPO_ROOT,
    )


def ensure_evidence() -> None:
    if not DETAIL_PATH.exists() or not VALIDATION_PATH.exists():
        build_evidence()


def load_data() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    detail = pd.read_csv(DETAIL_PATH)
    validation = pd.read_csv(VALIDATION_PATH)
    history = pd.read_csv(HISTORY_PATH) if HISTORY_PATH.exists() else validation.copy()
    return detail, validation, history


st.set_page_config(page_title="MediLacra Workflow Operations", layout="wide")
st.title("MediLacra Workflow Operations")
st.caption("Thin operational interface over the reconstructed and validated synthetic workflow model.")

if st.button("Rebuild synthetic evidence"):
    with st.spinner("Reconstructing and validating synthetic workflow evidence..."):
        build_evidence()
    st.success("Evidence rebuilt.")

ensure_evidence()
detail, validation, history = load_data()

ops_tab, metrics_tab, validation_tab, history_tab, docs_tab = st.tabs(
    ["Operations", "Metrics", "Validation", "History", "How It Works"]
)

with ops_tab:
    open_mask = detail["workflow_state"].isin(["queued", "active"])
    overdue_mask = detail["due_status"].eq("OVERDUE")
    mismatch_mask = detail["appointment_match_status"].eq("MISMATCH")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total workflows", len(detail))
    c2.metric("Open", int(open_mask.sum()))
    c3.metric("Overdue", int(overdue_mask.sum()))
    c4.metric("Appointment mismatches", int(mismatch_mask.sum()))

    type_options = sorted(detail["workflow_type"].dropna().unique().tolist())
    state_options = sorted(detail["workflow_state"].dropna().unique().tolist())
    selected_types = st.multiselect("Workflow type", type_options, default=type_options)
    selected_states = st.multiselect("Workflow state", state_options, default=state_options)

    filtered = detail[
        detail["workflow_type"].isin(selected_types)
        & detail["workflow_state"].isin(selected_states)
    ]
    st.dataframe(
        filtered[
            [
                "workflow_id",
                "patient_id",
                "workflow_type",
                "workflow_state",
                "due_status",
                "assigned_staff_name",
                "assigned_staff_role",
                "appointment_match_status",
                "closure_outcome",
            ]
        ],
        use_container_width=True,
        hide_index=True,
    )

with metrics_tab:
    st.subheader("State distribution")
    state_counts = (
        detail.groupby(["workflow_type", "workflow_state"], dropna=False)
        .size()
        .reset_index(name="count")
    )
    st.dataframe(state_counts, use_container_width=True, hide_index=True)

    st.subheader("Due status")
    due_counts = (
        detail.groupby(["workflow_type", "due_status"], dropna=False)
        .size()
        .reset_index(name="count")
    )
    st.dataframe(due_counts, use_container_width=True, hide_index=True)

    st.subheader("Appointment reconciliation")
    appointment_counts = (
        detail.groupby(["workflow_type", "appointment_match_status"], dropna=False)
        .size()
        .reset_index(name="count")
    )
    st.dataframe(appointment_counts, use_container_width=True, hide_index=True)

with validation_tab:
    status_counts = validation["status"].value_counts().to_dict()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("PASS", int(status_counts.get("PASS", 0)))
    c2.metric("FAIL", int(status_counts.get("FAIL", 0)))
    c3.metric("WARN", int(status_counts.get("WARN", 0)))
    c4.metric("NOT TESTABLE", int(status_counts.get("NOT_TESTABLE", 0)))

    st.dataframe(
        validation[["check_id", "check_name", "status", "classification", "evidence"]],
        use_container_width=True,
        hide_index=True,
    )
    st.info(
        "A FAIL is not automatically a pipeline defect. In this fixture the lifecycle documentation check is expected to fail because the evidence contains a valid canceled state omitted by the original notes."
    )

with history_tab:
    st.caption("Append-only validation history. Rebuild the evidence to add another run.")
    st.dataframe(
        history.sort_values("run_ts", ascending=False),
        use_container_width=True,
        hide_index=True,
    )

with docs_tab:
    st.subheader("Reconstructed model")
    st.markdown(MODEL_DOC.read_text(encoding="utf-8"))
    st.divider()
    st.subheader("Evidence-backed corrections")
    st.markdown(CORRECTED_NOTES.read_text(encoding="utf-8"))

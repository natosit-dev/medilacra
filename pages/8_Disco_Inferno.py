from __future__ import annotations

import time
from dataclasses import fields
from pathlib import Path

import pandas as pd
import streamlit as st

from hl7_demo.models import Encounter, Observation, Patient, Transaction
from experiments.disco_inferno.process_control import (
    get_active_run,
    get_job_status,
    load_completed_run,
    start_run,
    stop_active_run,
    tail_job_log,
)


TABLE_CLASSES = {
    "patients": Patient,
    "encounters": Encounter,
    "observations": Observation,
    "transactions": Transaction,
}
TABLE_FIELDS = {
    table: [field.name for field in fields(model_class)]
    for table, model_class in TABLE_CLASSES.items()
}


def _identifier_candidates(table: str) -> list[str]:
    candidates = []
    for name in TABLE_FIELDS[table]:
        if (
            name.endswith("_id")
            or name.endswith("_number")
            or name.endswith("_npi")
            or name in {"ssn", "visit_number", "account_number"}
        ):
            candidates.append(name)
    return candidates or TABLE_FIELDS[table]


def _default_index(options: list[str], default: str) -> int:
    return options.index(default) if default in options else 0


def _file_size(path: Path) -> str:
    size = path.stat().st_size
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / (1024 * 1024):.2f} MB"


def _preview_arm(result: dict, arm_name: str, preview_rows: int) -> None:
    arm = result["arms"][arm_name]
    manifest = arm.manifest
    table = manifest["table"]
    if not table:
        st.info("Control is intentionally identical to Beatrice.")
        return

    beatrice = result["beatrice"][table]
    inferno = arm.model[table]

    if arm_name == "Null":
        positions = manifest.get("selected_positions", [])[:preview_rows]
        left = beatrice.iloc[positions] if positions else beatrice.head(preview_rows)
        right = inferno.iloc[positions] if positions else inferno.head(preview_rows)
        st.caption("Showing rows selected by Minos for nulling.")
    elif arm_name == "Cerberus":
        positions = manifest.get("selected_positions", [])[:preview_rows]
        left = beatrice.iloc[positions] if positions else beatrice.head(preview_rows)
        source_rows = int(manifest["source_rows"])
        right = inferno.iloc[source_rows : source_rows + len(positions)]
        st.caption("Beatrice shows the selected source rows; Inferno shows their appended copies.")
    else:
        left = beatrice.head(preview_rows)
        right = inferno.head(preview_rows)
        st.caption("Same rows, with Charon's selected identifier field removed from Inferno.")

    col_left, col_right = st.columns(2)
    with col_left:
        st.markdown("#### Beatrice")
        st.dataframe(left, use_container_width=True, hide_index=True)
    with col_right:
        st.markdown(f"#### Inferno — {arm_name}")
        st.dataframe(right, use_container_width=True, hide_index=True)

    with st.expander("Corruption manifest"):
        st.json(manifest)


def _render_result(result: dict) -> None:
    run_id = result["run_id"]
    beatrice = result["beatrice"]
    arms = result["arms"]
    artifacts = result["artifacts"]

    st.success(f"Run {run_id} complete. Control delta = 0.")

    st.markdown("### Beatrice")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Patients", f"{len(beatrice['patients']):,}")
    m2.metric("Encounters", f"{len(beatrice['encounters']):,}")
    m3.metric("Observations", f"{len(beatrice['observations']):,}")
    m4.metric("Transactions", f"{len(beatrice['transactions']):,}")

    damage_rows = []
    for arm_name in ("Charon", "Null", "Cerberus"):
        manifest = arms[arm_name].manifest
        damage_rows.append(
            {
                "Resident": arm_name,
                "Operator": manifest["operator"],
                "Target": (
                    f"{manifest['table']}.{manifest['field']}"
                    if manifest.get("field")
                    else manifest["table"]
                ),
                "Affected": int(manifest.get("affected_rows", 0)),
                "Fraction": float(manifest.get("fraction", 0.0)),
            }
        )
    st.dataframe(pd.DataFrame(damage_rows), use_container_width=True, hide_index=True)

    preview_rows = st.slider(
        "Rows to preview per corruption",
        min_value=1,
        max_value=50,
        value=10,
        step=1,
    )

    overview_tab, charon_tab, null_tab, cerberus_tab, artifacts_tab, report_tab = st.tabs(
        ["Overview", "Charon", "Null", "Cerberus", "Artifacts", "Report"]
    )

    with overview_tab:
        metrics = pd.concat(result["metrics_by_arm"].values(), ignore_index=True)
        st.markdown("#### Beatrice vs Inferno measurements")
        st.dataframe(metrics, use_container_width=True, hide_index=True)
        st.markdown("#### Source-reality export")
        st.code(Path(artifacts["source_duckdb"]).name)
        st.markdown("#### HL7 message counts")
        st.caption(
            "SDOH enrichment: "
            + ("enabled" if result["manifest"]["settings"]["include_sdoh"] else "disabled")
        )
        st.dataframe(
            pd.DataFrame(
                [
                    {"Message type": name, "Messages": count}
                    for name, count in result["manifest"]["hl7"]["message_counts"].items()
                ]
            ),
            use_container_width=True,
            hide_index=True,
        )

    with charon_tab:
        _preview_arm(result, "Charon", preview_rows)

    with null_tab:
        _preview_arm(result, "Null", preview_rows)

    with cerberus_tab:
        _preview_arm(result, "Cerberus", preview_rows)

    with artifacts_tab:
        bundle_path = Path(artifacts["bundle"])
        st.download_button(
            "Download complete timestamped experiment bundle",
            data=bundle_path.read_bytes(),
            file_name=bundle_path.name,
            mime="application/zip",
            use_container_width=True,
        )

        artifact_rows = []
        for label, raw_path in artifacts.items():
            path = Path(raw_path)
            artifact_rows.append(
                {
                    "Artifact": label,
                    "File": path.name,
                    "Size": _file_size(path),
                }
            )
        st.dataframe(pd.DataFrame(artifact_rows), use_container_width=True, hide_index=True)

        st.markdown("#### Individual downloads")
        for label, raw_path in artifacts.items():
            path = Path(raw_path)
            if label == "bundle":
                continue
            mime = "application/octet-stream"
            if path.suffix == ".md":
                mime = "text/markdown"
            elif path.suffix == ".json":
                mime = "application/json"
            elif path.suffix == ".csv":
                mime = "text/csv"
            elif path.suffix == ".hl7":
                mime = "text/plain"
            st.download_button(
                f"{label}: {path.name}",
                data=path.read_bytes(),
                file_name=path.name,
                mime=mime,
                key=f"download-{run_id}-{label}",
                use_container_width=True,
            )

        st.caption(f"Local output directory: {result['run_dir']}")

    with report_tab:
        st.markdown(Path(artifacts["report"]).read_text(encoding="utf-8"))


st.title("🔥 Disco Inferno")
st.caption(
    "Medilacra entropy engine — hold reality and model constant, then compare "
    "Beatrice with controlled corruption."
)

active_run = get_active_run()
session_job_id = st.session_state.get("disco_inferno_job_id")
session_job_status = get_job_status(session_job_id)

if active_run:
    active_job_id = str(active_run["job_id"])
    active_pid = active_run.get("pid") or "starting"
    st.warning(
        f"🔒 Generator locked — job `{active_job_id}` • PID `{active_pid}`. "
        "Only one Disco Inferno generation process can run at a time."
    )
    stop_col, log_col = st.columns([1, 3])
    with stop_col:
        if st.button("🛑 Stop active run", type="primary", use_container_width=True):
            stopped = stop_active_run()
            st.session_state.pop("disco_inferno_result", None)
            if stopped.get("stopped"):
                st.session_state["disco_inferno_job_id"] = active_job_id
            st.rerun()
    with log_col:
        st.caption(
            "The generator is isolated in its own process. Stopping it terminates "
            "the worker process group without stopping Streamlit."
        )

    with st.expander("Live worker log", expanded=True):
        current_log = tail_job_log(active_job_id, max_lines=100)
        st.code(current_log or "Worker starting...", language="text")

if session_job_status:
    state = session_job_status.get("status")
    if state == "complete":
        loaded_job = st.session_state.get("disco_inferno_loaded_job")
        if loaded_job != session_job_id:
            try:
                loaded_result = load_completed_run(session_job_status["run_dir"])
                st.session_state["disco_inferno_result"] = loaded_result
                st.session_state["disco_inferno_loaded_job"] = session_job_id
            except Exception as exc:
                st.error(f"Run completed, but the UI could not reload its artifacts: {exc}")
    elif state == "failed":
        st.error(f"Worker failed: {session_job_status.get('error', 'unknown error')}")
        with st.expander("Worker log", expanded=True):
            st.code(tail_job_log(session_job_id, max_lines=150) or "No log output.", language="text")
    elif state == "stopped":
        st.info("🛑 The previous Disco Inferno worker was stopped and the generator lock was released.")

st.markdown("### Experiment controls")

with st.expander("Beatrice — source reality", expanded=True):
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        patients = int(
            st.number_input("Patients", min_value=1, max_value=10000, value=100, step=10)
        )
    with c2:
        encounters_per_patient = int(
            st.number_input("Encounters / patient", min_value=1, max_value=10, value=2, step=1)
        )
    with c3:
        observations_per_encounter = int(
            st.number_input("Observations / encounter", min_value=1, max_value=10, value=2, step=1)
        )
    with c4:
        transactions_per_encounter = int(
            st.number_input("Transactions / encounter", min_value=1, max_value=10, value=2, step=1)
        )

    s1, s2, s3 = st.columns(3)
    with s1:
        reality_seed = int(st.number_input("Reality seed", value=42, step=1))
    with s2:
        include_labs = st.checkbox("Include lab ORM + lab ORU exports", value=True)
    with s3:
        include_sdoh = st.checkbox(
            "Include SDOH enrichment (slow / external APIs)",
            value=False,
            help=(
                "Off by default. Enable only when external SDOH enrichment is part of the experiment. "
                "When off, the worker blocks Census, AirNow, PLACES, and BLS network lookups."
            ),
        )

with st.expander("Minos — Inferno controls", expanded=True):
    inferno_seed = int(st.number_input("Inferno seed", value=666, step=1))

    st.markdown("#### Charon — drop identifier")
    cc1, cc2 = st.columns(2)
    with cc1:
        charon_tables = list(TABLE_CLASSES)
        charon_table = st.selectbox(
            "Charon table",
            charon_tables,
            index=_default_index(charon_tables, "observations"),
        )
    with cc2:
        charon_fields = _identifier_candidates(charon_table)
        charon_field = st.selectbox(
            "Identifier / reference field",
            charon_fields,
            index=_default_index(charon_fields, "encounter_id"),
        )

    st.markdown("#### Null — erase facts")
    nc1, nc2, nc3 = st.columns([1, 1.5, 1])
    with nc1:
        null_tables = list(TABLE_CLASSES)
        null_table = st.selectbox(
            "Null table",
            null_tables,
            index=_default_index(null_tables, "observations"),
        )
    with nc2:
        null_fields = TABLE_FIELDS[null_table]
        null_field_name = st.selectbox(
            "Field to null",
            null_fields,
            index=_default_index(null_fields, "observation_text"),
        )
    with nc3:
        null_percent = st.slider("Null %", min_value=0, max_value=100, value=10, step=1)

    st.markdown("#### Cerberus — duplicate records")
    dc1, dc2 = st.columns(2)
    with dc1:
        duplicate_tables = list(TABLE_CLASSES)
        duplicate_table = st.selectbox(
            "Duplicate table",
            duplicate_tables,
            index=_default_index(duplicate_tables, "transactions"),
        )
    with dc2:
        duplicate_percent = st.slider(
            "Duplicate %", min_value=0, max_value=100, value=10, step=1
        )

st.caption(
    "Defaults reproduce the validated MVP: 100 / 2 / 2 / 2, reality seed 42, "
    "Inferno seed 666, Charon observations.encounter_id, 10% observation_text nulling, "
    "and 10% transaction duplication. External SDOH enrichment is OFF by default, "
    "matching the local deterministic experiment boundary used by Structured Sparsity."
)

start_disabled = active_run is not None
if st.button(
    "❤️‍🔥 Descend into the Inferno",
    type="primary",
    use_container_width=True,
    disabled=start_disabled,
):
    config = {
        "patients": patients,
        "encounters_per_patient": encounters_per_patient,
        "observations_per_encounter": observations_per_encounter,
        "transactions_per_encounter": transactions_per_encounter,
        "reality_seed": reality_seed,
        "inferno_seed": inferno_seed,
        "charon_table": charon_table,
        "charon_field": charon_field,
        "null_table": null_table,
        "null_field_name": null_field_name,
        "null_fraction": null_percent / 100.0,
        "duplicate_table": duplicate_table,
        "duplicate_fraction": duplicate_percent / 100.0,
        "include_labs": include_labs,
        "include_sdoh": include_sdoh,
    }
    try:
        job = start_run(config)
        st.session_state["disco_inferno_job_id"] = job["job_id"]
        st.session_state.pop("disco_inferno_result", None)
        st.session_state.pop("disco_inferno_loaded_job", None)
        st.rerun()
    except Exception as exc:
        st.exception(exc)

result = st.session_state.get("disco_inferno_result")
if result:
    _render_result(result)

if active_run:
    time.sleep(1.0)
    st.rerun()

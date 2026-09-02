from __future__ import annotations

import json
import os
from pathlib import Path

import pandas as pd
import streamlit as st

from connectathon.piqitt_bridge import (
    backend_path,
    convert_hl7_text,
    default_piqitt_repo,
    inspect_hl7_text,
)
from connectathon.preflight import preflight_bundle
from connectathon.scenarios import (
    DEFAULT_SCENARIOS,
    build_scenario_pack,
    load_case,
    zip_run_directory,
)


RESULT_ROOT = Path("connectathon/results")


def _discover_hl7_files() -> list[Path]:
    candidates: list[Path] = []
    patterns = (
        "output/*.hl7",
        "experiments/disco_inferno/output/*/hl7/*.hl7",
    )
    for pattern in patterns:
        candidates.extend(path for path in Path(".").glob(pattern) if path.is_file())
    unique = {str(path.resolve()): path for path in candidates}
    return sorted(unique.values(), key=lambda path: path.stat().st_mtime, reverse=True)


def _bundle_resource_counts(bundle: dict) -> dict[str, int]:
    counts: dict[str, int] = {}
    for entry in bundle.get("entry", []):
        resource = entry.get("resource", {}) if isinstance(entry, dict) else {}
        resource_type = resource.get("resourceType")
        if resource_type:
            counts[resource_type] = counts.get(resource_type, 0) + 1
    return counts


def _json_bytes(payload: dict) -> bytes:
    return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _read_selected_source(mode: str, uploaded_file, local_file: str | None) -> tuple[str | None, str | None]:
    if mode == "Upload HL7":
        if uploaded_file is None:
            return None, None
        return uploaded_file.getvalue().decode("utf-8", errors="ignore"), uploaded_file.name

    if not local_file:
        return None, None
    path = Path(local_file)
    return path.read_text(encoding="utf-8", errors="ignore"), str(path)


st.title("🧪 PIQI Connectathon 43")
st.caption(
    "MediLacra → PIQITT → FHIR baseline → controlled PIQI-shaped mutants. "
    "This page is the local Connectathon workbench."
)

st.info(
    "First-pass boundary: this UI builds and inspects the local evidence pack. "
    "External PIQI endpoint submission is intentionally not wired until the September 2 track kickoff "
    "confirms the live submission/report contract."
)

with st.expander("Experiment contract", expanded=False):
    st.markdown(
        """
- **MediLacra** creates the synthetic source reality and HL7.
- **PIQITT** remains the source of truth for HL7 → FHIR conversion; this branch loads its existing converter rather than copying it.
- **Disco Inferno** introduces exactly one declared FHIR mutation per mutant case.
- The untouched FHIR baseline is preserved alongside each mutant and its machine-readable manifest.
- Local preflight is deliberately weaker than PIQI/US Core conformance: it only proves the artifacts are shaped well enough for the next ingestion step.
        """
    )

st.markdown("## 1. Select source and materialize FHIR")

piqitt_default = str(default_piqitt_repo())
piqitt_repo = st.text_input(
    "Local PIQITT repository",
    value=os.getenv("PIQITT_REPO", piqitt_default),
    help="Expected to contain scripts/fhir_convert_backend.py. Default assumes medilacra and piqitt are sibling folders.",
)

backend = backend_path(piqitt_repo)
if backend.exists():
    st.success(f"PIQITT converter found: {backend}")
else:
    st.error(f"PIQITT converter not found: {backend}")

source_mode = st.radio("HL7 source", ["Existing MediLacra / Disco output", "Upload HL7"], horizontal=True)
local_files = _discover_hl7_files()
selected_local: str | None = None
uploaded = None

if source_mode == "Existing MediLacra / Disco output":
    if local_files:
        selected_path = st.selectbox(
            "Existing HL7 file",
            local_files,
            format_func=lambda path: f"{path.name} — {path.parent}",
        )
        selected_local = str(selected_path)
    else:
        st.warning("No local HL7 files found under output/ or Disco Inferno output directories.")
else:
    uploaded = st.file_uploader("Drop one MediLacra HL7/.txt file", type=["hl7", "txt"])

source_text, source_name = _read_selected_source(source_mode, uploaded, selected_local)
message_summary: list[dict] = []
message_index = 1

if source_text and backend.exists():
    try:
        message_summary = inspect_hl7_text(source_text, piqitt_repo=piqitt_repo)
    except Exception as exc:
        st.exception(exc)

if message_summary:
    st.caption(f"{len(message_summary)} HL7 message(s) found in {source_name}")
    st.dataframe(pd.DataFrame(message_summary), use_container_width=True, hide_index=True)
    options = [row["message_index"] for row in message_summary]
    message_index = st.selectbox(
        "Message to materialize",
        options,
        format_func=lambda index: (
            f"#{index} — "
            + next(row["message_type"] for row in message_summary if row["message_index"] == index)
        ),
    )

materialize_disabled = not source_text or not backend.exists() or not message_summary
if st.button(
    "Materialize FHIR baseline with PIQITT",
    type="primary",
    use_container_width=True,
    disabled=materialize_disabled,
):
    try:
        bundle, metadata = convert_hl7_text(
            source_text,
            message_index=int(message_index),
            piqitt_repo=piqitt_repo,
        )
        metadata["source_name"] = source_name
        st.session_state["piqi43_baseline"] = bundle
        st.session_state["piqi43_source_metadata"] = metadata
        st.session_state.pop("piqi43_run", None)
        st.success("FHIR baseline materialized from PIQITT's existing converter.")
    except Exception as exc:
        st.exception(exc)

baseline = st.session_state.get("piqi43_baseline")
source_metadata = st.session_state.get("piqi43_source_metadata", {})

if baseline:
    counts = _bundle_resource_counts(baseline)
    preflight = preflight_bundle(baseline)
    metric_cols = st.columns(4)
    metric_cols[0].metric("FHIR entries", len(baseline.get("entry", [])))
    metric_cols[1].metric("Patients", counts.get("Patient", 0))
    metric_cols[2].metric("Observations", counts.get("Observation", 0))
    metric_cols[3].metric("Local preflight", preflight["status"])

    st.dataframe(
        pd.DataFrame([{"Resource": key, "Count": value} for key, value in sorted(counts.items())]),
        use_container_width=True,
        hide_index=True,
    )

    with st.expander("Baseline FHIR JSON"):
        st.json(baseline)
    st.download_button(
        "Download baseline FHIR JSON",
        data=_json_bytes(baseline),
        file_name="baseline.fhir.json",
        mime="application/fhir+json",
        use_container_width=True,
    )

st.markdown("## 2. Build controlled Connectathon cases")
scenario_labels = {scenario["case_id"]: scenario["label"] for scenario in DEFAULT_SCENARIOS}
selected_case_ids = st.multiselect(
    "Cases",
    options=list(scenario_labels),
    default=list(scenario_labels),
    format_func=lambda case_id: scenario_labels[case_id],
    help="The three non-control SAM targets remain provisional until the track kickoff confirms the rubric targets.",
)
mutation_seed = int(st.number_input("Mutation seed", value=666, step=1))

if st.button(
    "Build local PIQI scenario pack",
    type="primary",
    use_container_width=True,
    disabled=not baseline or not selected_case_ids,
):
    try:
        run = build_scenario_pack(
            baseline,
            output_root=RESULT_ROOT,
            case_ids=selected_case_ids,
            mutation_seed=mutation_seed,
            source_metadata=source_metadata,
        )
        st.session_state["piqi43_run"] = run
        st.success(f"Scenario pack created: {run['run_id']}")
    except Exception as exc:
        st.exception(exc)

run = st.session_state.get("piqi43_run")
if run:
    st.markdown("### Local evidence pack")
    case_frame = pd.DataFrame(run["cases"])
    display_columns = [
        "case_id",
        "operator",
        "resource",
        "path",
        "expected_sam",
        "expected_status",
        "preflight",
        "changed_paths",
    ]
    st.dataframe(case_frame[display_columns], use_container_width=True, hide_index=True)

    run_dir = Path(run["run_dir"])
    st.download_button(
        "Download complete local Connectathon pack",
        data=zip_run_directory(run_dir),
        file_name=f"PIQI_CONNECTATHON_43_{run['run_id']}.zip",
        mime="application/zip",
        use_container_width=True,
    )
    st.caption(f"Local artifact directory: {run_dir}")

    selected_case = st.selectbox(
        "Inspect case",
        [case["case_id"] for case in run["cases"]],
        format_func=lambda case_id: scenario_labels.get(case_id, case_id),
    )
    case = load_case(run_dir, selected_case)
    manifest = case["manifest"]

    mutation = manifest["mutation"]
    c1, c2, c3 = st.columns(3)
    c1.metric("Operator", mutation["operator"])
    c2.metric("Expected SAM", manifest.get("expected", {}).get("sam") or "Control")
    c3.metric("Changed JSON paths", len(manifest.get("changed_paths", [])))

    baseline_tab, mutant_tab, manifest_tab, preflight_tab = st.tabs(
        ["Baseline", "Mutant", "Manifest", "Preflight"]
    )
    with baseline_tab:
        st.json(case["baseline"])
        st.download_button(
            "Download case baseline",
            data=_json_bytes(case["baseline"]),
            file_name=f"{selected_case}_baseline.fhir.json",
            mime="application/fhir+json",
            key=f"baseline-{run['run_id']}-{selected_case}",
        )
    with mutant_tab:
        st.json(case["mutant"])
        st.download_button(
            "Download case mutant",
            data=_json_bytes(case["mutant"]),
            file_name=f"{selected_case}_mutant.fhir.json",
            mime="application/fhir+json",
            key=f"mutant-{run['run_id']}-{selected_case}",
        )
    with manifest_tab:
        st.json(manifest)
        st.caption(
            "The manifest is the corruption receipt. For non-control cases, exactly one JSON path must differ from baseline."
        )
    with preflight_tab:
        st.json(case["preflight"])
        st.warning(
            "LOCAL_ONLY preflight is not an HL7/US Core/PIQI conformance claim and is not evidence that the track endpoint accepted the payload."
        )

st.markdown("## 3. PIQI endpoint execution")
st.warning(
    "Waiting on the September 2 track kickoff for the current endpoint submission mechanics and Evaluation/Audit Report shape. "
    "The next slice will preserve raw endpoint responses before we normalize or compare anything."
)
st.button("Submit pack to PIQI endpoints", disabled=True, use_container_width=True)

from __future__ import annotations

import json

import streamlit as st

from connectathon.shn_provider.client import SHNProviderClient
from connectathon.shn_provider.scenario import get_scenario, list_scenarios
from connectathon.shn_provider.workflow import ProviderWorkflow, cohort_rows


st.set_page_config(
    page_title="MediLacra — SHN Provider ePA",
    page_icon="🔁",
    layout="wide",
)

st.title("🔁 MediLacra → SHN Provider ePA")
st.caption(
    "Thin provider-side workbench for MediLacra reality → CRD → DTR → "
    "QuestionnaireResponse → PAS. Workflow and healthcare logic live outside the UI."
)

scenarios = list_scenarios()
scenario_by_id = {scenario.id: scenario for scenario in scenarios}
scenario_ids = [scenario.id for scenario in scenarios]
credentials_ready = SHNProviderClient.credentials_available()
client = SHNProviderClient.from_environment() if credentials_ready else None
workflow = ProviderWorkflow(client=client)

with st.sidebar:
    st.header("Provider connection")
    if credentials_ready:
        st.success("SHN credentials available")
        st.caption("Bearer tokens are obtained on demand and remain in memory.")
    else:
        st.warning("SHN credentials not found")
        st.caption(
            "Offline request construction still works. Live buttons are disabled. "
            "Set SHN_CLIENT_FILE or use the existing ignored provider-test client.json."
        )
    st.code("https://pa-test.shn-preview.org", language=None)
    st.caption("Provider test endpoint • route configured per scenario")


def _json_download(label: str, payload, filename: str, key: str) -> None:
    if payload is None:
        return
    st.download_button(
        label,
        data=json.dumps(payload, indent=2, sort_keys=True) + "\n",
        file_name=filename,
        mime="application/json",
        key=key,
    )


def _stage_card(title: str, stage, *, extra: str | None = None) -> None:
    st.markdown(f"**{title}**")
    if stage.error:
        st.error(stage.error)
    elif stage.response is not None:
        status = stage.transport.get("status_code") if stage.transport else "?"
        st.success(f"HTTP {status}")
    elif stage.request is not None:
        st.info("Built")
    else:
        st.caption("Not run")
    if extra:
        st.caption(extra)


def _trace(stage) -> None:
    if not stage.transport:
        return
    st.caption(
        f"Correlation: {stage.transport.get('correlation_id') or stage.transport.get('sent_correlation_id')} "
        f"• SHN leg: {stage.transport.get('leg_id') or '—'} "
        f"• {stage.transport.get('elapsed_ms', 0):.1f} ms"
    )
    trace = stage.transport.get("trace_url")
    if trace:
        st.link_button("Open SHN trace", trace)


single_tab, cohort_tab, artifact_tab = st.tabs(
    ["Single Patient", "Cohort", "Artifacts / Raw"]
)

with single_tab:
    controls = st.columns([2, 1, 1])
    with controls[0]:
        selected_scenario_id = st.selectbox(
            "Scenario",
            scenario_ids,
            format_func=lambda scenario_id: scenario_by_id[scenario_id].label,
            key="shn_provider_scenario",
        )
    with controls[1]:
        seed = int(
            st.number_input(
                "Seed",
                min_value=0,
                max_value=10_000_000,
                value=300,
                step=1,
                key="shn_provider_seed",
            )
        )
    with controls[2]:
        st.metric("Payer route", scenario_by_id[selected_scenario_id].payer_route)

    scenario = get_scenario(selected_scenario_id)
    case_key = (selected_scenario_id, seed)
    if st.session_state.get("shn_provider_case_key") != case_key:
        st.session_state["shn_provider_case"] = workflow.create_case(
            selected_scenario_id,
            seed,
        )
        st.session_state["shn_provider_case_key"] = case_key

    case = st.session_state["shn_provider_case"]

    with st.expander("Scenario contract", expanded=False):
        st.write(scenario.description)
        if scenario.notes:
            st.markdown("\n".join(f"- {note}" for note in scenario.notes))
        st.json(scenario.raw)

    reality = case.reality
    patient = reality["entities"]["patient"]
    encounter = reality["entities"]["encounter"]
    facts = reality["clinical_facts"]
    service = facts["ordered_service"]

    st.markdown("### Reality")
    metrics = st.columns(5)
    metrics[0].metric("Patient", patient["patient_id"])
    metrics[1].metric("Encounter", encounter["encounter_id"])
    metrics[2].metric("Service", service["code"])
    diagnosis = facts.get("diagnosis") or {}
    metrics[3].metric("Diagnosis", diagnosis.get("code") or "—")
    metrics[4].metric("Status", case.status)

    action_cols = st.columns(3)
    with action_cols[0]:
        if st.button("Build CRD request", use_container_width=True):
            try:
                workflow.build_crd(case)
                st.rerun()
            except Exception as exc:
                st.exception(exc)
    with action_cols[1]:
        if st.button(
            "Run next live stage",
            type="primary",
            use_container_width=True,
            disabled=not credentials_ready or case.status in {"complete", "failed"},
        ):
            try:
                workflow.run_next(case)
                st.rerun()
            except Exception as exc:
                st.exception(exc)
    with action_cols[2]:
        if st.button(
            "Run to completion",
            use_container_width=True,
            disabled=not credentials_ready or case.status in {"complete", "failed"},
        ):
            try:
                workflow.run_to_completion(case)
                st.rerun()
            except Exception as exc:
                st.exception(exc)

    if case.stop_reason:
        st.info(f"Stop reason: {case.stop_reason}")

    st.markdown("### Provider workflow")
    stage_cols = st.columns(5)
    with stage_cols[0]:
        st.markdown("**Reality**")
        st.success("Materialized")
        st.caption(case.case_id)
    with stage_cols[1]:
        crd_extra = None
        if case.crd.summary:
            crd_extra = (
                f"{case.crd.summary.get('covered') or '—'} • "
                f"{case.crd.summary.get('pa-needed') or 'no PA code'}"
            )
        _stage_card("CRD", case.crd, extra=crd_extra)
    with stage_cols[2]:
        dtr_extra = None
        if case.dtr.summary:
            dtr_extra = case.dtr.summary.get("questionnaire") or "No questionnaire"
        _stage_card("DTR", case.dtr, extra=dtr_extra)
    with stage_cols[3]:
        st.markdown("**Documentation**")
        if case.questionnaire_response is not None:
            st.success("Completed")
            st.caption(
                f"{len((case.materialization or {}).get('answers', []))} mapped answers"
            )
        else:
            st.caption("Not materialized")
    with stage_cols[4]:
        pas_extra = None
        if case.pas.summary:
            pas_extra = (
                f"{case.pas.summary.get('review_action_code') or '—'} "
                f"{case.pas.summary.get('review_action_display') or ''}"
            ).strip()
        _stage_card("PAS", case.pas, extra=pas_extra)

    if case.crd.summary:
        st.markdown("### CRD decision")
        st.json(case.crd.summary, expanded=False)
        _trace(case.crd)

    if case.dtr.summary:
        st.markdown("### DTR package")
        st.json(case.dtr.summary, expanded=False)
        _trace(case.dtr)

    if case.materialization:
        st.markdown("### Payer question → MediLacra fact → answer")
        st.dataframe(
            case.materialization["answers"],
            use_container_width=True,
            hide_index=True,
        )

    if case.pas.summary:
        st.markdown("### PAS decision")
        pas_cols = st.columns(4)
        pas_cols[0].metric(
            "Outcome",
            case.pas.summary.get("claim_response_outcome") or "—",
        )
        pas_cols[1].metric(
            "Review",
            case.pas.summary.get("review_action_code") or "—",
        )
        pas_cols[2].metric(
            "Authorization",
            case.pas.summary.get("authorization") or "—",
        )
        pas_cols[3].metric(
            "Communication requests",
            case.pas.summary.get("communication_request_count", 0),
        )
        if case.pas.summary.get("behavior_match") is True:
            st.success("PAS response matches the configured scenario expectation.")
        _trace(case.pas)


with cohort_tab:
    st.markdown("### Provider cohort")
    st.caption(
        "Runs the same ProviderWorkflow repeatedly. Scenario selection controls only "
        "the input/config contract; live payer responses still control branching."
    )

    c1, c2 = st.columns(2)
    with c1:
        cohort_start = int(
            st.number_input(
                "Start seed",
                min_value=0,
                value=300,
                step=1,
                key="shn_cohort_start",
            )
        )
        cohort_count = int(
            st.number_input(
                "Case count",
                min_value=1,
                max_value=100,
                value=9,
                step=1,
                key="shn_cohort_count",
            )
        )
    with c2:
        cohort_scenarios = st.multiselect(
            "Scenarios",
            scenario_ids,
            default=scenario_ids,
            format_func=lambda scenario_id: scenario_by_id[scenario_id].label,
            key="shn_cohort_scenarios",
        )

    if st.button(
        "Run live cohort",
        type="primary",
        disabled=not credentials_ready or not cohort_scenarios,
        use_container_width=True,
    ):
        with st.spinner("Running provider cohort through SHN..."):
            cases = workflow.run_cohort(
                start_seed=cohort_start,
                count=cohort_count,
                scenario_ids=cohort_scenarios,
            )
        st.session_state["shn_provider_cohort"] = cases

    cohort_cases = st.session_state.get("shn_provider_cohort")
    if cohort_cases:
        rows = cohort_rows(cohort_cases)
        completed = sum(row["status"] == "complete" for row in rows)
        failed = sum(row["status"] == "failed" for row in rows)
        pas_a1 = sum(row["pas_review"] == "A1" for row in rows)
        cohort_metrics = st.columns(4)
        cohort_metrics[0].metric("Cases", len(rows))
        cohort_metrics[1].metric("Completed", completed)
        cohort_metrics[2].metric("Failed", failed)
        cohort_metrics[3].metric("PAS A1", pas_a1)
        st.dataframe(rows, use_container_width=True, hide_index=True)


with artifact_tab:
    case = st.session_state.get("shn_provider_case")
    if case is None:
        st.info("Create a single-patient case first.")
    else:
        st.caption(f"Artifact directory: {case.artifact_dir or 'not persisted'}")
        st.markdown("### Reality")
        st.json(case.reality, expanded=False)
        _json_download(
            "Download reality.json",
            case.reality,
            "reality.json",
            "dl-reality",
        )

        for stage_name, stage in (
            ("CRD", case.crd),
            ("DTR", case.dtr),
            ("PAS", case.pas),
        ):
            with st.expander(stage_name):
                if stage.request is not None:
                    st.markdown("**Request**")
                    st.json(stage.request, expanded=False)
                    _json_download(
                        f"Download {stage_name} request",
                        stage.request,
                        f"{stage_name.lower()}_request.json",
                        f"dl-{stage_name}-request",
                    )
                if stage.response is not None:
                    st.markdown("**Response**")
                    st.json(stage.response, expanded=False)
                    _json_download(
                        f"Download {stage_name} response",
                        stage.response,
                        f"{stage_name.lower()}_response.json",
                        f"dl-{stage_name}-response",
                    )
                if stage.transport is not None:
                    st.markdown("**Transport**")
                    st.json(stage.transport, expanded=False)

        if case.questionnaire_response is not None:
            with st.expander("Materialized QuestionnaireResponse"):
                st.json(case.questionnaire_response, expanded=False)
                st.json(case.materialization, expanded=False)
                _json_download(
                    "Download QuestionnaireResponse",
                    case.questionnaire_response,
                    "questionnaire_response.json",
                    "dl-qr",
                )

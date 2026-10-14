from __future__ import annotations

import hashlib
import json

import streamlit as st

from connectathon.shn_provider.client import SHNProviderClient
from connectathon.shn_provider.crd import validate_payer_route
from connectathon.shn_provider.export import export_zip_bytes
from connectathon.shn_provider.scenario import get_scenario, list_scenarios
from connectathon.shn_provider.reference_suite import ReferenceSuiteRunner, result_rows
from connectathon.shn_provider.run_logging import event_rows
from connectathon.shn_provider.test_case import get_test_case, list_test_cases
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
reference_cases = list_test_cases()
reference_by_id = {case.id: case for case in reference_cases}

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
    crd_route = st.radio(
        "CRD order-sign destination",
        ["SHN Preview (direct)", "AEGIS Touchstone (proxy)"],
        key="shn_provider_crd_route",
    )
    touchstone_crd_url = None
    touchstone_user_key = None
    if crd_route == "AEGIS Touchstone (proxy)":
        touchstone_crd_url = st.text_input(
            "Touchstone full request URL",
            value="https://touchstone.aegis.net:59747/cds-services/shn-order-sign",
            help="Confirm this exact URL on Touchstone's Waiting for Request page.",
            key="shn_touchstone_crd_url",
        )
        touchstone_user_key = st.text_input(
            "Touchstone USER_KEY",
            type="password",
            key="shn_touchstone_user_key",
            help="From the active Touchstone execution; never enter your SHN client secret.",
        )
        st.caption(
            "Only CRD order-sign goes through AEGIS. The SHN token is still "
            "obtained directly from SHN; DTR and PAS remain direct. "
            "Touchstone sees the proxied bearer token and synthetic request."
        )
        if not touchstone_user_key:
            st.warning("Enter USER_KEY from the Touchstone Waiting for Request instructions.")
    else:
        st.code("https://pa-test.shn-preview.org", language=None)
        st.caption("Provider test endpoint • route configured per scenario")

    st.divider()
    payer_input = st.text_input(
        "Payer ID (CRD / DTR / PAS)",
        value=scenarios[0].payer_route,
        key="shn_provider_payer_route",
        help="SHN payer routing identifier, e.g. 00301. Leading zeros are significant.",
    )
    st.caption("Changes only the network payer identity; synthetic clinical facts stay the same.")
    try:
        payer_route = validate_payer_route(payer_input)
    except ValueError as exc:
        st.error(str(exc))
        st.stop()

# Keep the previously validated reference suite on the direct SHN route.
# Only the interactive provider workflow opts into the Touchstone proxy.
client = None
if credentials_ready and (
    crd_route == "SHN Preview (direct)" or touchstone_user_key
):
    try:
        client = SHNProviderClient.from_environment(
            touchstone_crd_url=touchstone_crd_url,
            touchstone_user_key=touchstone_user_key,
        )
    except ValueError as exc:
        st.sidebar.error(str(exc))

live_ready = client is not None
workflow = ProviderWorkflow(client=client)
reference_runner = ReferenceSuiteRunner(
    client=SHNProviderClient.from_environment() if credentials_ready else None,
    execution_mode="streamlit",
)


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


single_tab, cohort_tab, artifact_tab, reference_tab = st.tabs(
    ["Single Patient", "Cohort", "Artifacts / Raw", "Reference Suite"]
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
        st.metric("Payer route", payer_route)

    scenario = get_scenario(selected_scenario_id)
    # Prevent changing destinations or matching keys mid-case.
    route_fingerprint = hashlib.sha256(
        (touchstone_user_key or "").encode("utf-8")
    ).hexdigest() if crd_route == "AEGIS Touchstone (proxy)" else ""
    case_key = (selected_scenario_id, seed, payer_route, crd_route, touchstone_crd_url, route_fingerprint)
    if st.session_state.get("shn_provider_case_key") != case_key:
        st.session_state["shn_provider_case"] = workflow.create_case(
            selected_scenario_id,
            seed,
            payer_route=payer_route,
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
            disabled=not live_ready or case.status in {"complete", "failed"},
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
            disabled=not live_ready or case.status in {"complete", "failed"},
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
        disabled=not live_ready or not cohort_scenarios,
        use_container_width=True,
    ):
        with st.spinner("Running provider cohort through SHN..."):
            cases = workflow.run_cohort(
                start_seed=cohort_start,
                count=cohort_count,
                scenario_ids=cohort_scenarios,
                payer_route=payer_route,
            )
        st.session_state["shn_provider_cohort"] = cases
        st.session_state["shn_provider_cohort_route"] = payer_route

    cohort_cases = (
        st.session_state.get("shn_provider_cohort")
        if st.session_state.get("shn_provider_cohort_route") == payer_route
        else None
    )
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


with reference_tab:
    st.markdown("### SHN Connectathon reference suite")
    st.caption("Reference Suite remains on the direct SHN Preview route.")
    st.caption(
        "Executable TP-01–TP-05 and TN-01–TN-10 contracts. "
        "Positive cases reuse known-good reference payload structure; negative cases "
        "apply exactly one named mutation immediately before transport."
    )

    reference_id = st.selectbox(
        "Test case",
        [case.id for case in reference_cases],
        format_func=lambda test_id: (
            f"{test_id} — {reference_by_id[test_id].label}"
        ),
        key="shn_reference_test_id",
    )
    reference_case = get_test_case(reference_id)

    ref_cols = st.columns(3)
    ref_cols[0].metric("Kind", reference_case.kind)
    ref_cols[1].metric("Route", reference_case.route or "multiple")
    ref_cols[2].metric(
        "Execution",
        "manual" if reference_case.manual else "automated",
    )

    st.write(reference_case.description)
    if reference_case.notes:
        st.markdown("\n".join(f"- {note}" for note in reference_case.notes))

    with st.expander("Test contract", expanded=False):
        st.json(reference_case.raw)

    can_run_reference = reference_case.manual or credentials_ready
    if st.button(
        "Run reference test",
        type="primary",
        disabled=not can_run_reference,
        use_container_width=True,
        key="run-shn-reference-test",
    ):
        try:
            if reference_case.manual:
                manual_runner = ReferenceSuiteRunner(client=None)
                reference_result = manual_runner.run(reference_id)
            else:
                with st.spinner(f"Running {reference_id} through SHN..."):
                    reference_result = reference_runner.run(reference_id)
            st.session_state["shn_reference_result"] = reference_result
        except Exception as exc:
            st.exception(exc)

    reference_result = st.session_state.get("shn_reference_result")
    if reference_result and reference_result.test_id == reference_id:
        if reference_result.passed is True:
            st.success(f"{reference_result.test_id}: PASS")
        elif reference_result.passed is False:
            st.error(f"{reference_result.test_id}: FAIL")
        else:
            st.info(f"{reference_result.test_id}: manual observation required")

        st.caption(
            f"Run: {reference_result.run_id} • "
            f"Artifacts: {reference_result.artifact_dir or 'not persisted'}"
        )
        st.dataframe(
            result_rows(reference_result),
            use_container_width=True,
            hide_index=True,
        )

        st.markdown("### Full execution log")
        st.caption(
            f"{len(reference_result.events)} chronological events • "
            "credentials and bearer-token values are intentionally excluded"
        )
        if reference_result.events:
            st.dataframe(
                event_rows(reference_result.events),
                use_container_width=True,
                hide_index=True,
            )
            with st.expander("Raw event stream", expanded=False):
                st.json(reference_result.events, expanded=False)

        if reference_result.artifact_dir:
            try:
                export_bytes = export_zip_bytes(reference_result.artifact_dir)
                st.download_button(
                    "Export Full Test Log",
                    data=export_bytes,
                    file_name=(
                        f"medilacra-test-log-{reference_result.run_id}.zip"
                    ),
                    mime="application/zip",
                    key=f"export-full-log-{reference_result.run_id}",
                    use_container_width=True,
                )
            except Exception as exc:
                st.warning(f"Could not build full-log export: {exc}")

        for index, operation in enumerate(reference_result.operations, start=1):
            marker = (
                "PASS" if operation.passed is True
                else "FAIL" if operation.passed is False
                else "MANUAL"
            )
            with st.expander(
                f"{index}. {operation.operation_id} — {operation.operation_type} — {marker}",
                expanded=operation.passed is False,
            ):
                exp_col, obs_col = st.columns(2)
                with exp_col:
                    st.markdown("**Expected**")
                    st.json(operation.expected)
                with obs_col:
                    st.markdown("**Observed**")
                    st.json(operation.observed)

                if operation.transport:
                    st.markdown("**Transport**")
                    st.json(operation.transport, expanded=False)
                    if isinstance(operation.transport, dict):
                        direct_trace = operation.transport.get("trace_url")
                        if direct_trace:
                            st.link_button(
                                "Open SHN trace",
                                direct_trace,
                                key=f"ref-trace-{reference_result.run_id}-{index}",
                            )
                        for leg_name in ("first", "second"):
                            leg = operation.transport.get(leg_name)
                            if isinstance(leg, dict) and leg.get("trace_url"):
                                st.link_button(
                                    f"Open {leg_name} SHN trace",
                                    leg["trace_url"],
                                    key=(
                                        f"ref-trace-{reference_result.run_id}-"
                                        f"{index}-{leg_name}"
                                    ),
                                )

                if operation.error:
                    st.error(operation.error)

                if operation.request is not None:
                    st.markdown("**Request**")
                    st.json(operation.request, expanded=False)
                if operation.response is not None:
                    st.markdown("**Response**")
                    st.json(operation.response, expanded=False)

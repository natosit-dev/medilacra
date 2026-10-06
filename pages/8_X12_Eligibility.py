# pages/8_X12_Eligibility.py

from __future__ import annotations

from datetime import date, datetime

import streamlit as st

from x12.scenarios import (
    SCENARIO_LABELS,
    build_exchange_zip,
    build_scenario,
    run_scenario,
)


st.set_page_config(
    page_title="MediLacra — X12 Eligibility",
    layout="wide",
)

st.title("MediLacra — X12 Eligibility")
st.caption(
    "Synthetic 270/271 eligibility exchange between independent "
    "clinical and payer realities."
)


def _display_name(hl7_name: str) -> str:
    parts = (hl7_name or "").split("^")
    last_name = parts[0] if parts else ""
    first_name = parts[1] if len(parts) > 1 else ""
    return " ".join(
        value for value in (first_name, last_name) if value
    )


def _x12_for_display(message: str) -> str:
    return message.replace("~", "~\n").strip()


scenario_keys = list(SCENARIO_LABELS)
selected_key = st.selectbox(
    "Scenario",
    options=scenario_keys,
    format_func=lambda key: SCENARIO_LABELS[key],
)

service_date = st.date_input(
    "Service Date",
    value=date(2026, 10, 6),
)

scenario = build_scenario(selected_key)

st.caption(scenario.description)

clinical_col, payer_col = st.columns(2)

with clinical_col:
    st.subheader("Clinical Reality")
    st.write(f"**Patient:** {_display_name(scenario.clinical_patient.patient_name)}")
    st.write(f"**DOB:** {scenario.clinical_patient.date_of_birth}")
    st.write(f"**Member ID:** {scenario.clinical_coverage.member_id}")
    st.write(
        f"**Payer:** {scenario.clinical_coverage.payer_name} "
        f"({scenario.clinical_coverage.payer_id})"
    )
    st.write(
        f"**Plan:** {scenario.clinical_coverage.plan_name} "
        f"({scenario.clinical_coverage.plan_id})"
    )
    st.write(f"**Group:** {scenario.clinical_coverage.group_number}")

with payer_col:
    st.subheader("Payer Reality")
    st.write(
        f"**Member:** {scenario.payer_member.first_name.title()} "
        f"{scenario.payer_member.last_name.title()}"
    )
    st.write(f"**DOB:** {scenario.payer_member.date_of_birth}")
    st.write(f"**Member ID:** {scenario.payer_member.member_id}")
    st.write(
        f"**Payer:** {scenario.payer_member.payer_id}"
    )
    st.write(
        f"**Enrollment:** {scenario.payer_enrollment.status.value}"
    )
    st.write(
        f"**Plan:** {scenario.payer_plan.plan_name} "
        f"({scenario.payer_plan.plan_id})"
    )
    st.write(f"**Group:** {scenario.payer_enrollment.group_number}")

st.info(
    "The payer evaluates the inquiry against payer-held state. "
    "It does not dereference the clinical Patient or CoverageProfile."
)

run_exchange = st.button(
    "Run 270/271 Exchange",
    type="primary",
    use_container_width=True,
)

if run_exchange:
    try:
        with st.spinner("Running synthetic eligibility exchange..."):
            st.session_state["x12_eligibility_result"] = run_scenario(
                selected_key,
                service_date=service_date,
                run_at=datetime.now(),
            )
    except Exception as exc:
        st.error(f"X12 eligibility exchange failed: {exc}")

result = st.session_state.get("x12_eligibility_result")
result_matches_controls = bool(
    result
    and result.scenario_key == selected_key
    and result.service_date == service_date.isoformat()
)

if result and not result_matches_controls:
    st.info(
        "Scenario or service date changed. Run the exchange again "
        "to generate matching artifacts."
    )

if result_matches_controls:
    st.markdown("---")
    st.header("Exchange Result")

    metric_match, metric_eligibility, metric_plan, metric_trace = st.columns(4)

    metric_match.metric(
        "Member Match",
        result.match_result.outcome.value,
    )
    metric_eligibility.metric(
        "Eligibility",
        result.eligibility_response.outcome.value,
    )
    metric_plan.metric(
        "Plan",
        result.payer_plan.plan_name,
    )
    metric_trace.metric(
        "Trace",
        result.parsed_270.trace_id,
    )

    st.write(
        f"**Coverage:** {result.payer_enrollment.effective_start} "
        f"→ {result.payer_enrollment.effective_end}"
    )

    if result.match_result.conflicting_fields:
        clinical_last = result.clinical_patient.patient_name.split("^", 1)[0]
        st.warning(
            "Payer identity differs from inquiry. "
            f"Conflicting fields: {', '.join(result.match_result.conflicting_fields)}. "
            f"Clinical last name: {clinical_last.title()}. "
            f"Payer last name: {result.payer_member.last_name.title()}."
        )
    else:
        st.success("Clinical inquiry identity and payer member identity agree.")

    request_tab, response_tab = st.tabs(
        ["X12 270 Request", "X12 271 Response"]
    )

    with request_tab:
        st.code(
            _x12_for_display(result.x270),
            language="text",
        )
        st.caption(
            "Clinical-side request: "
            f"{result.parsed_270.inquiry.last_name} / "
            f"{result.parsed_270.inquiry.first_name} • "
            f"Member {result.parsed_270.inquiry.member_id} • "
            f"Service Type {result.parsed_270.inquiry.service_type} • "
            f"Date {result.parsed_270.inquiry.service_date}"
        )
        st.download_button(
            "Download 270",
            data=result.x270.encode("utf-8"),
            file_name=result.x270_filename,
            mime="text/plain",
            key="x12_download_270",
        )

    with response_tab:
        st.code(
            _x12_for_display(result.x271),
            language="text",
        )
        st.caption(
            "Payer-authored response: "
            f"{result.parsed_271.subscriber_last_name} / "
            f"{result.parsed_271.subscriber_first_name} • "
            f"Member {result.parsed_271.subscriber_member_id} • "
            f"Plan {result.parsed_271.plan_name} • "
            f"Coverage {result.parsed_271.coverage_start} "
            f"→ {result.parsed_271.coverage_end}"
        )
        st.download_button(
            "Download 271",
            data=result.x271.encode("utf-8"),
            file_name=result.x271_filename,
            mime="text/plain",
            key="x12_download_271",
        )

    st.subheader("Exchange Bundle")
    st.download_button(
        "Download Exchange ZIP",
        data=build_exchange_zip(result),
        file_name=result.zip_filename,
        mime="application/zip",
        key="x12_download_zip",
    )
    st.caption(
        "Downloads use the exchange run timestamp: "
        f"{result.timestamp}"
    )

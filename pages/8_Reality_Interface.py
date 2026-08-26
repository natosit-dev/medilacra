from dataclasses import asdict
from hashlib import sha256

import pandas as pd
import streamlit as st

from reality_interface.pipeline import analyze_uploaded_bytes, finalize_run


st.title("Reality Interface")
st.caption(
    "WAV → measured periodicity → human validation → synthetic context → HL7 v2 → FHIR"
)

uploaded = st.file_uploader("Drop a WAV", type=["wav"])
if uploaded is None:
    st.stop()

payload = uploaded.getvalue()
upload_hash = sha256(payload).hexdigest()
st.audio(payload, format="audio/wav")

if st.session_state.get("reality_interface_upload_hash") != upload_hash:
    with st.spinner("Measuring repeating pattern..."):
        analysis = analyze_uploaded_bytes(uploaded.name, payload)
    st.session_state["reality_interface_upload_hash"] = upload_hash
    st.session_state["reality_interface_analysis"] = analysis
    st.session_state.pop("reality_interface_finalized", None)

analysis = st.session_state["reality_interface_analysis"]
audio = analysis.audio
measurement = analysis.measurement

meta1, meta2, meta3 = st.columns(3)
meta1.metric("Duration", f"{audio.duration_seconds:.2f} s")
meta2.metric("Source rate", f"{audio.source_sample_rate_hz:,} Hz")
meta3.metric("Channels", str(audio.source_channels))

result1, result2, result3 = st.columns(3)
result1.metric(
    "Estimated cycle",
    f"{measurement.estimated_cycle_period_seconds:.3f} s",
)
result2.metric(
    "Estimated rate",
    f"{measurement.estimated_rate_per_minute:.1f} /min",
)
result3.metric("Periodicity score", f"{measurement.periodicity_score:.3f}")

st.subheader("Signal")
# Streamlit-native charts first. Thin the display only; analysis uses the full
# downsampled working signal returned by the backend.
max_points = 5000
step = max(1, audio.waveform.size // max_points)
waveform_df = pd.DataFrame(
    {
        "seconds": audio.time_seconds[::step],
        "waveform": audio.waveform[::step],
    }
).set_index("seconds")
st.line_chart(waveform_df)

st.subheader("Energy envelope")
envelope_time = (
    pd.Series(range(measurement.envelope.size), dtype="float64")
    / audio.analysis_sample_rate_hz
)
envelope_df = pd.DataFrame(
    {
        "seconds": envelope_time.iloc[::step].to_numpy(),
        "envelope": measurement.envelope[::step],
    }
).set_index("seconds")
st.line_chart(envelope_df)

st.caption(
    f"Source artifact: {analysis.artifacts.source_filename} · "
    f"{analysis.artifacts.source_location}"
)

st.subheader("Human validation")
with st.form("reality_interface_validation"):
    interpretation = st.selectbox(
        "What does this repeating measurement represent?",
        options=["heart_rate", "other"],
        format_func=lambda value: "Heart rate" if value == "heart_rate" else "Other / unspecified",
    )
    accepted = st.checkbox("Accept measured rate", value=True)
    override_enabled = st.checkbox("Override measured rate", value=False)
    override = st.number_input(
        "Override rate (/min)",
        min_value=1.0,
        value=float(measurement.estimated_rate_per_minute),
        step=0.1,
        disabled=not override_enabled,
    )
    notes = st.text_area("Notes", value="")
    finalize = st.form_submit_button("Generate synthetic context, HL7, and FHIR")

if finalize:
    if interpretation != "heart_rate":
        st.warning("Reality Interface v0.1 only binds Heart rate downstream.")
    elif not accepted:
        st.warning("Accept the measurement before generating clinical context.")
    else:
        with st.spinner("Projecting validated measurement through MediLacra..."):
            finalized = finalize_run(
                analysis,
                interpretation=interpretation,
                accepted=accepted,
                override_rate_per_minute=(override if override_enabled else None),
                notes=(notes or None),
            )
        st.session_state["reality_interface_finalized"] = finalized

finalized = st.session_state.get("reality_interface_finalized")
if finalized is not None:
    st.subheader("Synthetic clinical context")
    st.json(
        {
            "patient": asdict(finalized.clinical.patient),
            "encounter": asdict(finalized.clinical.encounter),
            "observation": {
                "code": finalized.clinical.observation_code,
                "display": finalized.clinical.observation_display,
                "value": finalized.clinical.value,
                "unit": finalized.clinical.unit,
                "source_filename": analysis.artifacts.source_filename,
                "source_location": analysis.artifacts.source_location,
            },
        }
    )

    st.subheader("HL7 v2 ORU^R01")
    st.code(finalized.hl7_message.replace("\r", "\n"), language="text")

    st.subheader("FHIR Bundle")
    st.json(finalized.fhir_bundle)

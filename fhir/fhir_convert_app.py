
import streamlit as st
import pandas as pd
import json, io, zipfile
from pathlib import Path

from fhir_convert_backend import split_messages, convert_message_to_bundle, detect_message_type

st.set_page_config(page_title="HL7 v2 → FHIR Converter", layout="wide")
st.title("HL7 v2 → FHIR Converter")
st.caption("Upload HL7 v2 files (ADT / ORU / DFT). We'll split on MSH and convert each message to a FHIR Bundle.")

with st.sidebar:
    st.header("Export Options")
    as_ndjson = st.checkbox("Export as NDJSON", value=False)
    pretty_json = st.checkbox("Pretty-print JSON (ZIP only)", value=True)

uploaded_files = st.file_uploader("Drop .hl7 or .txt files", type=["hl7","txt"], accept_multiple_files=True)

summary = []
bundles_by_file = {}

if uploaded_files:
    for uf in uploaded_files:
        raw = uf.read().decode("utf-8", errors="ignore")
        messages = split_messages(raw)
        file_bundles = []
        for i, msg in enumerate(messages, start=1):
            bundle, mtype = convert_message_to_bundle(msg)
            file_bundles.append(bundle)
            patient_id = next((e["resource"]["id"] for e in bundle["entry"] if e["resource"]["resourceType"]=="Patient"), None)
            summary.append({
                "file": uf.name,
                "msg_idx": i,
                "type": mtype,
                "patient": patient_id,
                "resource_types": ", ".join(sorted({e["resource"]["resourceType"] for e in bundle["entry"]}))
            })
        bundles_by_file[uf.name] = file_bundles

if summary:
    st.subheader("Parsed Messages")
    st.dataframe(pd.DataFrame(summary), use_container_width=True)
    st.subheader("Download")
    if as_ndjson:
        # One NDJSON per input file, packaged into a ZIP
        if st.button("Build NDJSON ZIP"):
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
                for fname, bundles in bundles_by_file.items():
                    lines = [json.dumps(b) for b in bundles]
                    zf.writestr(Path(fname).with_suffix(".ndjson").name, ("\n".join(lines)).encode("utf-8"))
            st.download_button("Download NDJSON ZIP", data=buf.getvalue(), file_name="fhir_bundles_ndjson.zip")
    else:
        if st.button("Build Bundles ZIP"):
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
                for fname, bundles in bundles_by_file.items():
                    base = Path(fname).stem
                    for idx, b in enumerate(bundles, start=1):
                        data = json.dumps(b, indent=2) if pretty_json else json.dumps(b)
                        zf.writestr(f"{base}/bundle_{idx:03d}.json", data.encode("utf-8"))
            st.download_button("Download Bundles ZIP", data=buf.getvalue(), file_name="fhir_bundles.zip")

st.markdown("---")
st.write("This is a minimal starter app. Extend with IG-compliant mappings and stronger validation as needed.")

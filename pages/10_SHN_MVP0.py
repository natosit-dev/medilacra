from __future__ import annotations

import json

import streamlit as st

from connectathon.shn_mvp0 import build_case, case_zip_bytes


st.set_page_config(page_title="SHN MVP-0", page_icon="🔁", layout="wide")

st.title("MediLacra → SHN MVP-0")
st.caption(
    "Build one coherent synthetic patient reality and project it as a DTR 2.1 "
    "QuestionnaireResponse ready for SHN /demo/transform."
)

seed = int(st.number_input("Synthetic case seed", min_value=0, value=43, step=1))

if "shn_mvp0_case" not in st.session_state or st.session_state.get("shn_mvp0_seed") != seed:
    st.session_state["shn_mvp0_case"] = build_case(seed)
    st.session_state["shn_mvp0_seed"] = seed

case = st.session_state["shn_mvp0_case"]
reality = case["reality"]

c1, c2, c3 = st.columns(3)
c1.metric("Case", reality["case_id"])
c2.metric("Input contract", "pa.dtr 2.1")
c3.metric("Target", "pa.dtr 2.2")

st.subheader("Reality")
for relationship in reality["relationships"]:
    st.code(
        f'{relationship["subject"]}  --{relationship["predicate"]}-->  {relationship["object"]}',
        language=None,
    )

st.subheader("DTR 2.1 FHIR payload")
st.json(case["dtr_input"], expanded=False)

st.subheader("SHN POST body")
st.caption("PIQITT can POST this object to SHN's /demo/transform endpoint.")
st.json(case["shn_request"], expanded=False)

st.subheader("Expected meaning to preserve")
st.json(case["expected_invariants"], expanded=False)

st.download_button(
    "Download MVP-0 case pack",
    data=case_zip_bytes(case),
    file_name=f'{reality["case_id"]}.zip',
    mime="application/zip",
)

st.download_button(
    "Download SHN request JSON",
    data=json.dumps(case["shn_request"], indent=2, sort_keys=True) + "\n",
    file_name=f'{reality["case_id"]}.shn.json',
    mime="application/json",
)

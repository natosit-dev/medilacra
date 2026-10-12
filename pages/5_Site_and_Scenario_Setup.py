# pages/10_Site_and_Scenario_Setup.py
# Streamlit page: Site & Scenario Setup (MVP)
# - Define Facilities/Locations, Departments/Service Lines, Visit Mix & Routing
# - Save/Load YAML scenario profiles to ./data/scenario_profiles
# - Validate and preview 10 encounter skeletons with PV1-2, PV1-3, PV1-10

import os
import random
import re
from typing import Dict, List, Optional, Tuple

import streamlit as st

from profiles.site_profile import (
    default_profile as unified_default_profile,
    generate_preview as unified_generate_preview,
    list_profiles as unified_list_profiles,
    load_profile as unified_load_profile,
    save_profile as unified_save_profile,
    validate_profile as unified_validate_profile,
)
from profiles.hl7_interface_profile import analyze_hl7, build_interface_record

try:
    import yaml  # PyYAML
except Exception as e:
    st.error("PyYAML is required for this page. Install with: pip install pyyaml")
    raise

# Optional: integrate with your logging framework if present
try:
    from utils.log_utils import get_logger  # type: ignore
    logger = get_logger(__name__)
except Exception:
    import logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    logger = logging.getLogger(__name__)

# -----------------------
# Constants / Enumerations
# -----------------------
LOCATION_TYPES = [
    "ICU", "MEDSURG", "ED", "OR", "CLINIC", "LAB", "RAD", "OBS", "OTHER"
]

SERVICE_LINES = [
    "Medicine", "Emergency", "Radiology", "Laboratory", "Pathology", "Surgery",
    "Cardiology", "Primary Care"
]

VISIT_CLASSES = ["IP", "OP", "ED", "OBS", "AS", "CL"]  # Ambulatory Surgery = AS; Clinic = CL

PATIENT_CLASS_MAP = {  # PV1-2 mapping
    "IP": "I",
    "OP": "O",
    "ED": "E",
    "OBS": "O",
    "AS": "O",
    "CL": "O",
}

# -----------------------
# Session State
# -----------------------
def init_state():
    if "scenario_profile" not in st.session_state:
        st.session_state["scenario_profile"] = unified_default_profile()

def get_profile() -> Dict:
    return st.session_state["scenario_profile"]

def set_profile(p: Dict) -> None:
    st.session_state["scenario_profile"] = p

# -----------------------
# UI Components
# -----------------------
def facilities_locations_tab():
    profile = get_profile()
    st.subheader("Facilities & Locations")

    add_fac = st.button("Add Facility", key="btn_add_facility")
    if add_fac:
        profile["facilities"].append({
            "facility_code": "",
            "name": "",
            "address": "",
            "city": "",
            "state": "",
            "zip": "",
            "timezone": "America/New_York",
            "org_id": "",
            "locations": []
        })

    to_remove_idx: Optional[int] = None
    for idx, fac in enumerate(profile.get("facilities") or []):
        with st.expander(f"Facility #{idx+1} — {fac.get('facility_code') or '(unset)'}", expanded=False):
            cols = st.columns(3)
            fac["facility_code"] = cols[0].text_input("facility_code", value=fac.get("facility_code", ""), key=f"fac_code_{idx}")
            fac["name"] = cols[1].text_input("name", value=fac.get("name", ""), key=f"fac_name_{idx}")
            fac["org_id"] = cols[2].text_input("org_id (optional)", value=fac.get("org_id", ""), key=f"fac_org_{idx}")

            cols2 = st.columns(4)
            fac["address"] = cols2[0].text_input("address", value=fac.get("address", ""), key=f"fac_addr_{idx}")
            fac["city"] = cols2[1].text_input("city", value=fac.get("city", ""), key=f"fac_city_{idx}")
            fac["state"] = cols2[2].text_input("state", value=fac.get("state", ""), key=f"fac_state_{idx}")
            fac["zip"] = cols2[3].text_input("zip", value=fac.get("zip", ""), key=f"fac_zip_{idx}")

            fac["timezone"] = st.text_input("timezone", value=fac.get("timezone", "America/New_York"), key=f"fac_tz_{idx}", help="IANA timezone, e.g., America/New_York")

            st.markdown("**Locations**")
            add_loc = st.button("Add Location", key=f"btn_add_loc_{idx}")
            if add_loc:
                fac["locations"].append({
                    "location_code": "",
                    "location_type": "MEDSURG",
                    "room_format": "",
                    "bed_format": "",
                    "rooms_count": 0,
                    "beds_per_room": 0,
                    "weight": 1
                })

            # Render locations
            loc_remove_idx: Optional[int] = None
            for j, loc in enumerate(fac.get("locations") or []):
                with st.container():
                    lc1, lc2, lc3, lc4 = st.columns([1,1,1,1])
                    loc["location_code"] = lc1.text_input("location_code", value=loc.get("location_code", ""), key=f"loc_code_{idx}_{j}")
                    loc["location_type"] = lc2.selectbox("location_type", LOCATION_TYPES, index=max(0, LOCATION_TYPES.index(loc.get("location_type", "MEDSURG"))), key=f"loc_type_{idx}_{j}")
                    loc["weight"] = lc3.number_input("weight", min_value=0.0, value=float(loc.get("weight", 1.0)), step=1.0, key=f"loc_w_{idx}_{j}", help="Bias for choosing this location within its type")
                    remove_loc = lc4.button("Remove", key=f"btn_remove_loc_{idx}_{j}")
                    rc1, rc2, rc3 = st.columns(3)
                    loc["room_format"] = rc1.text_input("room_format", value=loc.get("room_format", ""), key=f"loc_roomfmt_{idx}_{j}", help="e.g., R###")
                    loc["beds_per_room"] = int(rc2.number_input("beds_per_room", min_value=0, value=int(loc.get("beds_per_room", 0)), step=1, key=f"loc_bpr_{idx}_{j}"))
                    loc["bed_format"] = rc3.text_input("bed_format", value=loc.get("bed_format", ""), key=f"loc_bedfmt_{idx}_{j}", help="e.g., B#")
                    st.divider()
                    if remove_loc:
                        loc_remove_idx = j
                if loc_remove_idx is not None:
                    del fac["locations"][loc_remove_idx]
                    loc_remove_idx = None
                    st.rerun()

            remove_fac = st.button("Remove Facility", key=f"btn_remove_fac_{idx}")
            if remove_fac:
                to_remove_idx = idx
        # end expander

    if to_remove_idx is not None:
        del profile["facilities"][to_remove_idx]
        st.rerun()

def departments_tab():
    profile = get_profile()
    st.subheader("Departments & Service Lines")

    add_dept = st.button("Add Department", key="btn_add_dept")
    if add_dept:
        profile["departments"].append({
            "facility_code": "",
            "department_code": "",
            "name": "",
            "service_line": "Medicine",
            "hospital_service": ""
        })

    remove_idx: Optional[int] = None
    for idx, d in enumerate(profile.get("departments") or []):
        with st.container():
            c1, c2, c3, c4, c5 = st.columns([1,1,1,1,0.5])
            d["facility_code"] = c1.text_input("facility_code", value=d.get("facility_code", ""), key=f"dept_fac_{idx}", help="Scope to a facility; leave blank to make it global")
            d["department_code"] = c2.text_input("department_code", value=d.get("department_code", ""), key=f"dept_code_{idx}")
            d["name"] = c3.text_input("name", value=d.get("name", ""), key=f"dept_name_{idx}")
            d["service_line"] = c4.selectbox("service_line", SERVICE_LINES, index=max(0, SERVICE_LINES.index(d.get("service_line", "Medicine"))), key=f"dept_sl_{idx}")
            d["hospital_service"] = c5.text_input("PV1-10 (hospital_service)", value=d.get("hospital_service", ""), key=f"dept_hs_{idx}")

            rbtn = st.button("Remove Department", key=f"btn_remove_dept_{idx}")
            st.divider()
            if rbtn:
                remove_idx = idx
    if remove_idx is not None:
        del profile["departments"][remove_idx]
        st.rerun()

def visit_mix_routing_tab():
    profile = get_profile()
    st.subheader("Visit Mix & Routing")

    st.markdown("**Visit Class Weights (must sum to 100)**")
    vm_cols = st.columns(len(VISIT_CLASSES))
    for i, vc in enumerate(VISIT_CLASSES):
        current = float(profile["visit_mix"].get(vc, 0))
        profile["visit_mix"][vc] = vm_cols[i].number_input(vc, min_value=0.0, max_value=100.0, step=1.0, value=current, key=f"vm_{vc}")
    st.caption(f"Current total: {sum(profile['visit_mix'].get(vc, 0) for vc in VISIT_CLASSES)}")

    st.markdown("**Routing Rules (per visit class)**")
    dept_codes = [d.get("department_code", "") for d in profile.get("departments") or [] if d.get("department_code")]
    for vc in VISIT_CLASSES:
        with st.expander(f"{vc} Routing", expanded=False):
            rule = profile["routing"].setdefault(vc, {"location_types": {}, "default_department_code": ""})

            # location types selection with weights
            chosen_types = list(rule.get("location_types", {}).keys())
            current_sel = [t for t in chosen_types if t in LOCATION_TYPES]
            sel = st.multiselect("Allowed location_types", LOCATION_TYPES, default=current_sel, key=f"rt_types_{vc}")

            # prune removed types
            lt_map = rule.setdefault("location_types", {})
            for t in list(lt_map.keys()):
                if t not in sel:
                    lt_map.pop(t, None)
            # sliders/inputs for each selected type
            for t in sel:
                cur = float(lt_map.get(t, 0))
                lt_map[t] = st.number_input(f"{t} weight", min_value=0.0, max_value=100.0, step=1.0, value=cur, key=f"rt_w_{vc}_{t}")

            # default department code suggestion
            rule["default_department_code"] = st.selectbox(
                "default_department_code (PV1-10 via department.hospital_service)",
                options=[""] + dept_codes,
                index=([""] + dept_codes).index(rule.get("default_department_code", "")) if rule.get("default_department_code", "") in ([""] + dept_codes) else 0,
                key=f"rt_dept_{vc}"
            )

def header_bar():
    profile = get_profile()
    left, mid, right = st.columns([1,1,1])
    with left:
        st.text_input("Profile Name", value=profile.get("profile_name", "New Scenario"), key="profile_name_input")
        profile["profile_name"] = st.session_state["profile_name_input"]

    with mid:
        existing = unified_list_profiles()
        selected = st.selectbox("Load existing profile", options=["(select)"] + existing, index=0, key="load_profile_select")
        if selected != "(select)":
            if st.button("Load", key="btn_load"):
                try:
                    loaded = unified_load_profile(selected)
                    set_profile(loaded)
                    st.session_state.pop("hl7_interface_analysis", None)
                    st.success(f"Loaded {selected}")
                except Exception as e:
                    logger.exception("Failed to load profile")
                    st.error(f"Failed to load: {e}")

    with right:
        if st.button("Save", key="btn_save"):
            try:
                saved_name = unified_save_profile(profile)
                st.success(f"Saved as {saved_name}")
            except Exception as e:
                logger.exception("Failed to save profile")
                st.error(f"Failed to save: {e}")

    st.text_area("Notes", value=profile.get("notes", ""), key="profile_notes")
    profile["notes"] = st.session_state["profile_notes"]

def interface_profile_tab():
    profile = get_profile()
    profile.setdefault("interfaces", {})

    st.subheader("HL7 Interface Profile")
    st.caption(
        "Drop real HL7 examples here to observe the interface. Raw messages and "
        "example values are not saved into the profile."
    )

    left, right = st.columns([2, 1])
    with left:
        pasted = st.text_area(
            "Paste HL7 v2 messages",
            height=220,
            placeholder="MSH|^~\\&|...\nPID|...\nPV1|...",
            key="interface_hl7_paste",
        )
    with right:
        uploaded = st.file_uploader(
            "Or upload one .hl7/.txt file",
            type=["hl7", "txt"],
            key="interface_hl7_upload",
        )
        analyze = st.button(
            "Analyze Messages",
            type="primary",
            use_container_width=True,
            key="interface_analyze",
        )
        st.caption(
            "MVP fields: MSH-9, PID-3.1, PID-3.4, PID-7, PV1-44."
        )

    if analyze:
        try:
            source = ""
            if uploaded is not None:
                source = uploaded.getvalue().decode("utf-8", errors="replace")
            elif pasted.strip():
                source = pasted

            if not source.strip():
                st.warning("Paste or upload HL7 messages first.")
            else:
                st.session_state["hl7_interface_analysis"] = analyze_hl7(source)
        except Exception as exc:
            logger.exception("HL7 interface analysis failed")
            st.error(f"Analysis failed: {exc}")

    analysis = st.session_state.get("hl7_interface_analysis")
    if not analysis:
        existing = profile.get("interfaces") or {}
        if existing:
            st.markdown("**Saved interface message profiles**")
            st.dataframe(
                [
                    {
                        "MSH-9": signature,
                        "root_schema": value.get("root_schema"),
                        "messages_profiled": value.get("sample_message_count"),
                    }
                    for signature, value in sorted(existing.items())
                ],
                use_container_width=True,
                hide_index=True,
            )
        return

    m1, m2 = st.columns(2)
    m1.metric("Messages analyzed", analysis["message_count"])
    m2.metric("Distinct MSH-9 triplets", analysis["group_count"])

    signatures = [group["signature"] for group in analysis["groups"]]
    selected_signature = st.selectbox(
        "Message semantics",
        signatures,
        key="interface_signature",
    )
    group = next(
        group
        for group in analysis["groups"]
        if group["signature"] == selected_signature
    )

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("MSH-9.1", group["message_code"])
    c2.metric("MSH-9.2", group["trigger_event"])
    c3.metric("MSH-9.3", group["root_schema"] or "—")
    c4.metric("Messages", group["message_count"])

    resolution = group["schema_resolution"]
    if resolution.get("resolved"):
        st.success(
            f"Root schema {group['root_schema']} found in the existing "
            f"HL7 v{resolution.get('registry_version') or '?'} registry."
        )
    elif not group["root_schema"]:
        st.warning("MSH-9.3 is blank; no root schema was supplied by this feed.")
    elif resolution.get("registry_available"):
        st.warning(
            f"MSH-9.3 {group['root_schema']} was not found in the existing registry."
        )
    else:
        st.warning("The local HL7 registry is unavailable, so MSH-9.3 was not resolved.")

    rows = []
    for key in ("mrn", "assigning_authority", "date_of_birth", "pv1_44"):
        field = group["fields"][key]
        rows.append(
            {
                "Data Element": field["label"],
                "Destination": field["path"],
                "Observed": f"{field['present']}/{field['total']}",
                "Coverage": f"{field['coverage_pct']:.1f}%",
                "Unique Values": field["unique_values"],
            }
        )

    st.markdown("**Observed fields**")
    st.dataframe(rows, use_container_width=True, hide_index=True)
    st.caption(
        "MRN and Assigning Authority are treated as one identifier mapping: "
        "PID-3.1 + PID-3.4."
    )

    if st.checkbox(
        "Show transient example values (may contain PHI)",
        value=False,
        key="interface_show_examples",
    ):
        st.warning("Examples are shown only in this session and are not saved.")
        st.json(
            {
                group["fields"][key]["path"]: group["fields"][key]["examples"]
                for key in group["fields"]
            }
        )

    existing_group = (profile.get("interfaces") or {}).get(selected_signature, {})
    existing_pv1 = (
        existing_group.get("mappings", {})
        .get("pv1_44", {})
        .get("transaction_dictionary_message", "")
    )
    pv1_44_meaning = st.text_input(
        f"PV1-44 meaning for {selected_signature}",
        value=existing_pv1,
        placeholder="e.g. Admission date/time",
        help=(
            "Human-confirmed meaning for this exact message code + trigger + "
            "root structure. Leave blank if not yet known."
        ),
        key=f"pv1_44_meaning_{selected_signature}",
    )

    if st.button(
        "Apply this message profile",
        use_container_width=True,
        key=f"apply_interface_{selected_signature}",
    ):
        profile["interfaces"][selected_signature] = build_interface_record(
            group,
            pv1_44_meaning=pv1_44_meaning,
        )
        st.success(
            f"Applied {selected_signature} to the current site profile. "
            "Use Save above to write the unified JSON profile."
        )

    if profile.get("interfaces"):
        st.markdown("**Currently attached to this site profile**")
        attached = []
        for signature, value in sorted(profile["interfaces"].items()):
            pv1 = (
                value.get("mappings", {})
                .get("pv1_44", {})
                .get("transaction_dictionary_message", "")
            )
            attached.append(
                {
                    "MSH-9": signature,
                    "root_schema": value.get("root_schema") or "—",
                    "PV1-44 meaning": pv1 or "unconfirmed",
                    "messages_profiled": value.get("sample_message_count"),
                }
            )
        st.dataframe(attached, use_container_width=True, hide_index=True)


def validate_and_preview():
    profile = get_profile()
    st.subheader("Validate & Preview")
    c1, c2, c3 = st.columns([1,1,1])

    seed = c1.number_input("Preview Seed", min_value=0, value=int(profile.get("preview_seed", 1234)), step=1, key="preview_seed")
    profile["preview_seed"] = int(seed)
    n = int(c2.number_input("Rows", min_value=1, max_value=50, value=10, step=1, key="preview_rows"))
    validate_btn = c3.button("Validate & Preview", key="btn_preview")

    if validate_btn:
        errs = unified_validate_profile(profile)
        if errs:
            st.error("Validation failed:")
            for e in errs:
                st.write(f"- {e}")
            return

        rows = unified_generate_preview(profile, n=n, seed=seed)
        if not rows:
            st.warning("No preview rows generated.")
            return

        import pandas as pd
        df = pd.DataFrame(rows, columns=[
            "visit_class", "PV1-2", "PV1-3", "PV1-10", "facility_code", "location_code", "department_code"
        ])
        st.dataframe(df, use_container_width=True)

# -----------------------
# Page Entrypoint
# -----------------------
def main():
    st.set_page_config(page_title="Site & Scenario Setup", page_icon=None, layout="wide")
    st.title("Site & Interface Profile")
    st.caption(
        "Define the site's facilities, generation probabilities, routing, and "
        "observed HL7 interface semantics in one profile."
    )

    init_state()
    header_bar()

    tabs = st.tabs([
        "Facilities & Locations",
        "Departments",
        "Visit Mix & Routing",
        "Interface Profile",
        "Validate & Preview",
    ])
    with tabs[0]:
        facilities_locations_tab()
    with tabs[1]:
        departments_tab()
    with tabs[2]:
        visit_mix_routing_tab()
    with tabs[3]:
        interface_profile_tab()
    with tabs[4]:
        validate_and_preview()

if __name__ == "__main__":
    main()

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
PROFILE_DIR = os.path.join(".", "data", "scenario_profiles")

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
# Utilities
# -----------------------
def ensure_dirs() -> None:
    os.makedirs(PROFILE_DIR, exist_ok=True)

def list_profiles() -> List[str]:
    ensure_dirs()
    files = [f for f in os.listdir(PROFILE_DIR) if f.lower().endswith(".yaml")]
    return sorted(files)

def profile_path(name: str) -> str:
    ensure_dirs()
    # sanitize filename
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", name.strip())
    return os.path.join(PROFILE_DIR, f"{safe}.yaml")

def default_profile() -> Dict:
    # Minimal, empty MVP profile with a workable default visit mix that sums to 100
    return {
        "profile_version": 1,
        "profile_name": "New Scenario",
        "notes": "MVP profile; PV1 routing only.",
        "facilities": [],
        "departments": [],
        "visit_mix": {"IP": 25, "OP": 40, "ED": 20, "OBS": 10, "AS": 3, "CL": 2},
        "routing": {
            "IP": {"location_types": {"MEDSURG": 80, "ICU": 20}, "default_department_code": "MED"},
            "OP": {"location_types": {"CLINIC": 70, "RAD": 30}, "default_department_code": "MED"},
            "ED": {"location_types": {"ED": 100}, "default_department_code": "ED"},
            "OBS": {"location_types": {"OBS": 80, "MEDSURG": 20}, "default_department_code": "MED"},
            "AS": {"location_types": {"OR": 100}, "default_department_code": "SUR"},
            "CL": {"location_types": {"CLINIC": 100}, "default_department_code": "MED"},
        },
        "preview_seed": 1234,
    }

def load_profile(file_name: str) -> Dict:
    path = os.path.join(PROFILE_DIR, file_name)
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}

def save_profile(profile: Dict, name_override: Optional[str] = None) -> str:
    name = name_override or profile.get("profile_name") or "Scenario"
    path = profile_path(name)
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(profile, f, sort_keys=False, allow_unicode=True)
    return os.path.basename(path)

def weighted_choice(weights: Dict[str, float]) -> Optional[str]:
    # weights: {"key": weight, ...}
    items = [(k, float(v)) for k, v in (weights or {}).items() if float(v) > 0]
    if not items:
        return None
    keys, vals = zip(*items)
    total = sum(vals)
    if total <= 0:
        return None
    pick = random.uniform(0, total)
    cum = 0.0
    for k, v in items:
        cum += v
        if pick <= cum:
            return k
    return items[-1][0]  # fallback

def render_format(fmt: Optional[str], max_digit: int = 9) -> str:
    # Replace each '#' in fmt with a random digit 0..max_digit
    if not fmt:
        return ""
    out = []
    for ch in str(fmt):
        if ch == "#":
            out.append(str(random.randint(0, max_digit)))
        else:
            out.append(ch)
    return "".join(out)

def collect_locations_by_type(facilities: List[Dict]) -> Dict[str, List[Tuple[str, Dict]]]:
    """
    Build a map: location_type -> list of (facility_code, location_dict)
    """
    by_type: Dict[str, List[Tuple[str, Dict]]] = {}
    for f in facilities:
        fcode = f.get("facility_code", "")
        for loc in f.get("locations", []) or []:
            lt = loc.get("location_type")
            if lt:
                by_type.setdefault(lt, []).append((fcode, loc))
    return by_type

def get_department(profile: Dict, facility_code: str, dept_code: str) -> Optional[Dict]:
    for d in profile.get("departments", []) or []:
        if d.get("facility_code") == facility_code and d.get("department_code") == dept_code:
            return d
    # allow fallback if not facility-scoped
    for d in profile.get("departments", []) or []:
        if d.get("department_code") == dept_code:
            return d
    return None

def validate_profile(profile: Dict) -> List[str]:
    errors: List[str] = []

    facilities = profile.get("facilities") or []
    departments = profile.get("departments") or []
    visit_mix = profile.get("visit_mix") or {}
    routing = profile.get("routing") or {}

    if not facilities:
        errors.append("At least one facility is required.")
    else:
        has_any_location = any((f.get("locations") or []) for f in facilities)
        if not has_any_location:
            errors.append("At least one location across all facilities is required.")

    if not departments:
        errors.append("At least one department is required.")

    # Sum of visit class weights = 100
    total = sum(float(visit_mix.get(vc, 0)) for vc in VISIT_CLASSES)
    if round(total, 4) != 100.0:
        errors.append(f"Visit mix must sum to 100. Current sum: {total}")

    # Routing references should exist
    valid_loc_types = set(LOCATION_TYPES)
    dept_codes = set(d.get("department_code") for d in departments if d.get("department_code"))
    for vc, rule in routing.items():
        if vc not in VISIT_CLASSES:
            errors.append(f"Unknown visit class in routing: {vc}")
            continue
        lt = (rule or {}).get("location_types") or {}
        for t in lt.keys():
            if t not in valid_loc_types:
                errors.append(f"Routing for {vc} references unknown location_type: {t}")
        dflt = (rule or {}).get("default_department_code")
        if dflt and dflt not in dept_codes:
            # Allow this as a warning-level in MVP; we keep as error so page is explicit
            errors.append(f"Routing for {vc} references unknown department_code: {dflt}")

    return errors

def generate_preview(profile: Dict, n: int = 10, seed: Optional[int] = None) -> List[Dict]:
    if seed is not None:
        random.seed(seed)

    facilities = profile.get("facilities") or []
    routing = profile.get("routing") or {}
    visit_mix = profile.get("visit_mix") or {}
    loc_by_type = collect_locations_by_type(facilities)

    # Build a flat list of candidate visit classes based on percentage weights
    visit_classes: List[str] = []
    for vc in VISIT_CLASSES:
        w = int(round(float(visit_mix.get(vc, 0))))
        visit_classes.extend([vc] * max(0, w))

    rows: List[Dict] = []
    for i in range(n):
        if not visit_classes:
            break
        chosen_vc = random.choice(visit_classes)
        pv1_2 = PATIENT_CLASS_MAP.get(chosen_vc, "O")

        rule = routing.get(chosen_vc, {}) or {}
        lt_weights: Dict[str, float] = rule.get("location_types") or {}
        chosen_lt = weighted_choice(lt_weights)

        # pick a concrete location from chosen type
        facility_code = ""
        location_code = ""
        room = ""
        bed = ""

        candidate_locations: List[Tuple[str, Dict]] = []
        if chosen_lt and chosen_lt in loc_by_type:
            candidate_locations = loc_by_type.get(chosen_lt, [])

        if not candidate_locations:
            # fallback: any location anywhere
            for f in facilities:
                for loc in f.get("locations", []) or []:
                    candidate_locations.append((f.get("facility_code", ""), loc))

        if candidate_locations:
            # weight by location weight if present
            weights = []
            for fc, loc in candidate_locations:
                w = float(loc.get("weight", 1))
                if w <= 0:
                    w = 1.0
                weights.append(w)
            pick = random.choices(candidate_locations, weights=weights, k=1)[0]
            facility_code, location = pick
            location_code = location.get("location_code", "")

            room_fmt = location.get("room_format")
            bed_fmt = location.get("bed_format")
            rooms_count = int(location.get("rooms_count") or 0)
            beds_per_room = int(location.get("beds_per_room") or 0)

            # If templating provided, synthesize room/bed; otherwise leave blank
            room = render_format(room_fmt) if room_fmt else ""
            if beds_per_room > 0 and bed_fmt:
                bed = render_format(bed_fmt, max_digit=max(1, beds_per_room))
            else:
                bed = render_format(bed_fmt) if bed_fmt else ""

        # department and PV1-10
        default_dept_code = rule.get("default_department_code", "")
        dept = get_department(profile, facility_code, default_dept_code) if default_dept_code else None
        hospital_service = (dept or {}).get("hospital_service") or default_dept_code or ""

        pv1_3 = "^".join([location_code or "", room or "", bed or "", facility_code or ""]).rstrip("^")

        rows.append({
            "visit_class": chosen_vc,
            "PV1-2": pv1_2,
            "PV1-3": pv1_3,  # point_of_care ^ room ^ bed ^ facility
            "PV1-10": hospital_service,
            "facility_code": facility_code,
            "location_code": location_code,
            "department_code": default_dept_code,
        })

    return rows

# -----------------------
# Session State
# -----------------------
def init_state():
    if "scenario_profile" not in st.session_state:
        st.session_state["scenario_profile"] = default_profile()

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
        existing = list_profiles()
        selected = st.selectbox("Load existing profile", options=["(select)"] + existing, index=0, key="load_profile_select")
        if selected != "(select)":
            if st.button("Load", key="btn_load"):
                try:
                    loaded = load_profile(selected)
                    set_profile(loaded)
                    st.success(f"Loaded {selected}")
                except Exception as e:
                    logger.exception("Failed to load profile")
                    st.error(f"Failed to load: {e}")

    with right:
        if st.button("Save", key="btn_save"):
            try:
                saved_name = save_profile(profile)
                st.success(f"Saved as {saved_name}")
            except Exception as e:
                logger.exception("Failed to save profile")
                st.error(f"Failed to save: {e}")

    st.text_area("Notes", value=profile.get("notes", ""), key="profile_notes")
    profile["notes"] = st.session_state["profile_notes"]

def validate_and_preview():
    profile = get_profile()
    st.subheader("Validate & Preview")
    c1, c2, c3 = st.columns([1,1,1])

    seed = c1.number_input("Preview Seed", min_value=0, value=int(profile.get("preview_seed", 1234)), step=1, key="preview_seed")
    profile["preview_seed"] = int(seed)
    n = int(c2.number_input("Rows", min_value=1, max_value=50, value=10, step=1, key="preview_rows"))
    validate_btn = c3.button("Validate & Preview", key="btn_preview")

    if validate_btn:
        errs = validate_profile(profile)
        if errs:
            st.error("Validation failed:")
            for e in errs:
                st.write(f"- {e}")
            return

        rows = generate_preview(profile, n=n, seed=seed)
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
    st.title("Site & Scenario Setup (MVP)")
    st.caption("Define facilities, locations, departments, and visit routing. Save a scenario profile for generators to consume.")

    init_state()
    header_bar()

    tabs = st.tabs(["Facilities & Locations", "Departments", "Visit Mix & Routing", "Validate & Preview"])
    with tabs[0]:
        facilities_locations_tab()
    with tabs[1]:
        departments_tab()
    with tabs[2]:
        visit_mix_routing_tab()
    with tabs[3]:
        validate_and_preview()

if __name__ == "__main__":
    main()

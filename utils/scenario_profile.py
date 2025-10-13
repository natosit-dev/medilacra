# utils/scenario_profile.py
# Scenario Profile loader and PV1 field computation for MediLacra MVP

import os, re, random
from typing import Dict, List, Tuple, Optional

try:
    import yaml  # PyYAML
except Exception as e:
    raise RuntimeError("PyYAML is required: pip install pyyaml") from e

PROFILE_DIR = os.path.join(".", "data", "scenario_profiles")

VISIT_CLASSES = ["IP", "OP", "ED", "OBS", "AS", "CL"]
PV1_CLASS_MAP = {"IP": "I", "OP": "O", "ED": "E", "OBS": "O", "AS": "O", "CL": "O"}

def _list_profiles() -> List[str]:
    os.makedirs(PROFILE_DIR, exist_ok=True)
    return sorted([f for f in os.listdir(PROFILE_DIR) if f.lower().endswith(".yaml")])

def load_profile(filename: Optional[str] = None) -> Dict:
    """
    Load a scenario profile YAML from ./data/scenario_profiles.
    If filename is None, pick the alphabetically last profile.
    """
    os.makedirs(PROFILE_DIR, exist_ok=True)
    if filename is None:
        files = _list_profiles()
        if not files:
            raise FileNotFoundError("No scenario profiles found in ./data/scenario_profiles")
        filename = files[-1]
    path = os.path.join(PROFILE_DIR, filename)
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}

def _render_format(fmt: Optional[str], max_digit: int = 9) -> str:
    if not fmt:
        return ""
    out = []
    for ch in str(fmt):
        out.append(str(random.randint(0, max_digit)) if ch == "#" else ch)
    return "".join(out)

def _collect_locations_by_type(facilities: List[Dict]) -> Dict[str, List[Tuple[str, Dict]]]:
    by_type: Dict[str, List[Tuple[str, Dict]]] = {}
    for f in facilities or []:
        fcode = f.get("facility_code", "")
        for loc in f.get("locations", []) or []:
            lt = loc.get("location_type")
            if lt:
                by_type.setdefault(lt, []).append((fcode, loc))
    return by_type

def _weighted_choice(weights: Dict[str, float]) -> Optional[str]:
    items = [(k, float(v)) for k, v in (weights or {}).items() if float(v) > 0]
    if not items:
        return None
    keys, vals = zip(*items)
    total = sum(vals)
    if total <= 0:
        return None
    pick = random.uniform(0, total)
    s = 0.0
    for k, v in items:
        s += v
        if pick <= s:
            return k
    return items[-1][0]

def _get_department(profile: Dict, facility_code: str, dept_code: str) -> Optional[Dict]:
    for d in profile.get("departments", []) or []:
        if d.get("facility_code") == facility_code and d.get("department_code") == dept_code:
            return d
    for d in profile.get("departments", []) or []:
        if d.get("department_code") == dept_code:
            return d
    return None

def compute_pv1_fields(profile: Dict, *, seed: Optional[int] = None) -> Dict:
    """
    Returns:
      {
        "visit_class": <IP/OP/...>,
        "pv1_2": <I/O/E>,
        "pv1_3": "<poc>^<room>^<bed>^<facility_code>",
        "hospital_service": <department.hospital_service or dept code>,
        "facility_code": ...,
        "location_code": ...,
        "department_code": ...
      }
    """
    if seed is not None:
        random.seed(seed)

    facilities = profile.get("facilities") or []
    routing = profile.get("routing") or {}
    visit_mix = profile.get("visit_mix") or {}
    loc_by_type = _collect_locations_by_type(facilities)

    # Build a proportional list for random pick
    visit_classes: List[str] = []
    for vc in VISIT_CLASSES:
        w = int(round(float(visit_mix.get(vc, 0))))
        visit_classes.extend([vc] * max(0, w))
    if not visit_classes:
        raise ValueError("Scenario profile visit_mix produced no visit classes")

    chosen_vc = random.choice(visit_classes)
    pv1_2 = PV1_CLASS_MAP.get(chosen_vc, "O")

    rule = routing.get(chosen_vc, {}) or {}
    lt_weights: Dict[str, float] = rule.get("location_types") or {}
    chosen_lt = _weighted_choice(lt_weights)

    # Candidate concrete locations
    candidates: List[Tuple[str, Dict]] = []
    if chosen_lt and chosen_lt in loc_by_type:
        candidates = loc_by_type.get(chosen_lt, [])
    if not candidates:
        # Fallback: any location anywhere
        for f in facilities:
            for loc in f.get("locations", []) or []:
                candidates.append((f.get("facility_code", ""), loc))
    if not candidates:
        raise ValueError("Scenario profile has no locations to choose from")

    # Weight by location weight if present
    weights = []
    for fc, loc in candidates:
        w = float(loc.get("weight", 1.0))
        weights.append(w if w > 0 else 1.0)
    facility_code, location = random.choices(candidates, weights=weights, k=1)[0]
    location_code = location.get("location_code", "")

    # Room/bed synthesis
    room_fmt = location.get("room_format")
    bed_fmt = location.get("bed_format")
    rooms_count = int(location.get("rooms_count") or 0)
    beds_per_room = int(location.get("beds_per_room") or 0)
    room = _render_format(room_fmt) if room_fmt else ""
    bed = _render_format(bed_fmt, max_digit=max(1, beds_per_room)) if beds_per_room > 0 and bed_fmt else (_render_format(bed_fmt) if bed_fmt else "")

    default_dept_code = rule.get("default_department_code", "")
    dept = _get_department(profile, facility_code, default_dept_code) if default_dept_code else None
    hospital_service = (dept or {}).get("hospital_service") or default_dept_code or ""

    pv1_3 = "^".join([location_code or "", room or "", bed or "", facility_code or ""]).rstrip("^")

    return {
        "visit_class": chosen_vc,
        "pv1_2": pv1_2,
        "pv1_3": pv1_3,
        "hospital_service": hospital_service,
        "facility_code": facility_code,
        "location_code": location_code,
        "department_code": default_dept_code,
    }

from datetime import datetime
from .segments import seg_msh, seg_evn, seg_pid, seg_pv1, seg_orc, seg_obr, seg_obx, seg_obx_lines, seg_ft1, seg_dg1
from .sdoh import get_police_station_count_by_zip, build_obx_police_count, get_air_quality_by_zip, build_obx_air_quality, get_poverty_pct_by_zcta, build_obx_poverty_pct
from .vitals import predict_vitals, build_obx_vitals
from .models import Patient, Encounter, Transaction, Observation
from typing import List, Optional, Dict

AIRNOW_MILES_DEFAULT = 75


def build_adt(
    p: Patient,
    enc: Encounter,
    add_police_obx: bool = True,
    add_air_obx: bool = True,
    add_poverty_obx: bool = True,
    miles: int = AIRNOW_MILES_DEFAULT,
    obs: Optional[Observation] = None,   # <— add this
) -> str:
    parts = [seg_msh("ADT^A01"), seg_evn(enc, "A01"), seg_pid(p), seg_pv1(enc)]

    # --- your existing SDOH/vitals OBXs (unchanged) ---
    set_id = 1
    if add_police_obx and getattr(p, "zip_code", ""):
        cnt = get_police_station_count_by_zip(p.zip_code)
        parts.append(build_obx_police_count(cnt, set_id=set_id)); set_id += 1

    if add_air_obx and getattr(p, "zip_code", ""):
        aq = get_air_quality_by_zip(p.zip_code)  # miles no longer needed
        obx_aq = build_obx_air_quality(aq, set_id=set_id)
        if obx_aq: parts.append(obx_aq); set_id += 1

    if add_poverty_obx and getattr(p, "zip_code", ""):
        pov = get_poverty_pct_by_zcta(p.zip_code)
        obx_pov = build_obx_poverty_pct(pov, set_id=set_id)
        if obx_pov: parts.append(obx_pov); set_id += 1

    try:
        age = datetime.now().year - datetime.strptime(p.date_of_birth, "%Y-%m-%d").year
        pov = get_poverty_pct_by_zcta(p.zip_code) or 0.0
        aq = get_air_quality_by_zip(p.zip_code); aqi_val = float(aq.get("aqi", 50)) if aq else 50.0
        parts.extend(build_obx_vitals(predict_vitals(age, pov, aqi_val), start_set_id=set_id))
    except Exception as e:
        print(f"[WARN] Failed to generate vitals for {p.patient_id}: {e}")

    # --- NEW: DG1 AFTER OBX group (use admitting diagnosis for ADT) ---
    if obs and obs.icd_code:
        dg1_dt = obs.completed_time or enc.admit_datetime
        parts.append(seg_dg1(enc, icd_code=obs.icd_code, desc="", set_id=1, diag_type="A", diag_dt=dg1_dt))

    return "\r".join(parts)





def build_oru(p: Patient, enc: Encounter, obs_list: list[Observation]) -> str:
    obr = seg_obr(enc, obs_list[0]) if obs_list else "OBR|1||||"
    obxs = []; set_id = 1
    for o in obs_list:
        parts = seg_obx_lines(o, start_set_id=set_id)
        obxs.extend(parts); set_id += len(parts)
    return "\r".join([seg_msh("ORU^R01"), seg_pid(p), seg_pv1(enc), obr] + obxs)

def build_dft(p: Patient, enc: Encounter, txs: List[Transaction], obs_list: List[Observation]) -> str:
    parts = [seg_msh("DFT^P03"), seg_pid(p), seg_pv1(enc)]

    # FT1 first
    parts += [seg_ft1(t, obs_list[0] if obs_list else None) for t in txs]

    # DG1(s) after FT1 group (final diagnoses for billing)
    if obs_list:
        set_id = 1
        seen = set()
        for o in obs_list:
            icd = (o.icd_code or "").strip()
            if not icd or icd in seen: 
                continue
            parts.append(seg_dg1(enc, icd_code=icd, desc="", set_id=set_id, diag_type="F", diag_dt=o.completed_time))
            seen.add(icd); set_id += 1

    # Optional OBR/OBX narrative after charges/diagnoses
    if obs_list:
        parts.append(seg_obr(enc, obs_list[0]))
        parts.extend(seg_obx(o) for o in obs_list)

    return "\r".join(parts)


from datetime import datetime
from .segments import (
    seg_msh, seg_evn, seg_pid, seg_pv1, seg_orc, seg_obr, seg_obx, seg_obx_lines, seg_ft1, seg_dg1,
    seg_obx_gender_identity, seg_obx_pronouns, seg_obx_spcu   # ← ADD THESE
)

from .sdoh import  get_air_quality_by_zip, build_obx_air_quality, get_poverty_pct_by_zcta, build_obx_poverty_pct, build_obx_places_obesity, build_obx_unemployment
from .vitals import predict_vitals, build_obx_vitals
from .models import Patient, Encounter, Transaction, Observation
from typing import List, Optional, Dict
from .labs import build_lab_orm as _build_lab_orm
from .labs import build_lab_oru as _build_lab_oru
from .labs import predict_labs_for_patient as _predict_labs_for_patient
from .generators import choose_gender_harmony_values


AIRNOW_MILES_DEFAULT = 75

# messages.py — update build_adt signature and body
def build_adt(
    p: Patient,
    enc: Encounter,
    add_air_obx: bool = True,
    add_poverty_obx: bool = True,
    add_places_obesity_obx: bool = False,
    add_unemployment_obx: bool = False,
    miles: int = AIRNOW_MILES_DEFAULT,
    obs: Optional[Observation] = None,

    # --- NEW flags for Gender Harmony (v2.5 via OBX) ---
    add_gi_obx: bool = True,
    add_pronouns_obx: bool = True,
    add_spcu_obx: bool = True,
) -> str:

    parts = [seg_msh("ADT^A01"), seg_evn(enc, "A01"), seg_pid(p), seg_pv1(enc)]

    set_id = 1

    if add_air_obx and getattr(p, "zip_code", ""):
        aq = get_air_quality_by_zip(p.zip_code)
        obx_aq = build_obx_air_quality(aq, set_id=set_id)
        if obx_aq: parts.append(obx_aq); set_id += 1

    if add_poverty_obx and getattr(p, "zip_code", ""):
        pov = get_poverty_pct_by_zcta(p.zip_code)
        obx_pov = build_obx_poverty_pct(pov, set_id=set_id)
        if obx_pov: parts.append(obx_pov); set_id += 1

    # Vitals OBXs (this returns a list; bump set_id accordingly)
    try:
        age = datetime.now().year - datetime.strptime(p.date_of_birth, "%Y-%m-%d").year
        pov = get_poverty_pct_by_zcta(p.zip_code) or 0.0
        aq = get_air_quality_by_zip(p.zip_code); aqi_val = float(aq.get("aqi", 50)) if aq else 50.0
        vital_obxs = build_obx_vitals(predict_vitals(age, pov, aqi_val), start_set_id=set_id)
        parts.extend(vital_obxs)
        set_id += len(vital_obxs)                            # <<< IMPORTANT
    except Exception as e:
        print(f"[WARN] Failed to generate vitals for {p.patient_id}: {e}")

    # --- NEW SDOH (no-key APIs), appended at the end of ADT ---

    if add_places_obesity_obx:
        parts.append(build_obx_places_obesity(p.zip_code, set_id=set_id)); set_id += 1
    if add_unemployment_obx:
        parts.append(build_obx_unemployment(p.zip_code, set_id=set_id)); set_id += 1


    # --- NEW: Gender Harmony (v2.5 via OBX) ---------------------------
    _now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Pick values with 95% alignment to PID-8 (M/F), else non-typical
    gh = choose_gender_harmony_values(getattr(p, "sex", ""), match_bias=0.95)

    if add_gi_obx:
        gi_code, gi_text, gi_sys = gh["gi"]
        parts.append(
            seg_obx_gender_identity(
                set_id=set_id,
                gi_code=gi_code, gi_text=gi_text, gi_system=gi_sys,
                effective_dt=_now,
                method=("ptReport", "Patient-reported", "HL7"),
                performing_org="MEDILACRAHS"
            )
        ); set_id += 1

    if add_pronouns_obx:
        pn_code, pn_text, pn_sys = gh["pro"]
        parts.append(
            seg_obx_pronouns(
                set_id=set_id,
                pronoun_code=pn_code, pronoun_text=pn_text, pronoun_system=pn_sys,
                effective_dt=_now
            )
        ); set_id += 1

    if add_spcu_obx:
        sp_code, sp_text, sp_sys = gh["spcu"]
        parts.append(
            seg_obx_spcu(
                set_id=set_id,
                spcu_code=sp_code, spcu_text=sp_text, spcu_system=sp_sys,
                effective_dt=_now,
                method=("endo", "Endocrinology assessment", "HL7")
            )
        ); set_id += 1

    # -------------------------------------------------------------------

    # Keep DG1 after the entire OBX group (your existing convention)
    if obs and obs.icd_code:
        dg1_dt = obs.completed_time or enc.admit_datetime
        parts.append(seg_dg1(enc, icd_code=obs.icd_code, desc=obs.icd_description, set_id=1, diag_type="A", diag_dt=dg1_dt))

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
            parts.append(seg_dg1(enc, icd_code=icd, desc=getattr(o, "icd_description", ""), set_id=set_id, diag_type="F", diag_dt=o.completed_time))
            seen.add(icd); set_id += 1

    return "\r".join(parts)


from .labs import predict_labs_for_patient, build_lab_orm as _build_lab_orm, build_lab_oru as _build_lab_oru

def build_orm_labs(p: Patient, enc: Encounter,
                    order_code: str = "SYN_LABS", order_text: str = "Synthetic Lab Panel") -> str:
    return _build_lab_orm(p, enc, order_code, order_text)

def build_oru_labs(p: Patient, enc: Encounter, start_set_id: int = 20,
                    order_code: str = "SYN_LABS", order_text: str = "Synthetic Lab Panel") -> str:
    labs = predict_labs_for_patient(p)
    return _build_lab_oru(p, enc, labs, order_code, order_text, start_set_id=start_set_id)
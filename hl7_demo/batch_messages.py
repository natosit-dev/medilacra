"""Network-free message builders used by MediLacra batch experiments.

These mirror the current ORU/DFT/lab projections without invoking legacy
SDOH API lookups.
"""

from __future__ import annotations

import random
from typing import Dict, List

from .labs import LABS_SPEC, build_lab_orm as _build_lab_orm, build_lab_oru as _build_lab_oru
from .models import Encounter, Observation, Patient, Transaction
from .segments import (
    seg_dg1,
    seg_evn,
    seg_ft1,
    seg_gt1,
    seg_in1,
    seg_msh,
    seg_obr,
    seg_obx_lines,
    seg_pid,
    seg_pv1,
)


def _predict_labs_offline() -> Dict[str, Dict]:
    """Generate the existing synthetic lab panel without SDOH API inputs.

    Poverty=0 and AQI=50 match the fallback values already used by the legacy
    predictor when enrichment is unavailable.
    """

    poverty = 0.0
    aqi = 50.0
    results: Dict[str, Dict] = {}

    for loinc, spec in LABS_SPEC.items():
        base = random.gauss(spec["mean"], spec["sd"])
        shift = poverty * spec["poverty_beta"] + aqi * spec["aqi_beta"]
        noisy = base + random.gauss(shift, spec["sd"] * 0.05)

        low, high = spec["ref"]
        value = max(low - (high - low), min(high + (high - low), noisy))
        flag = "L" if value < low else "H" if value > high else "N"

        results[loinc] = {
            "loinc": loinc,
            "name": spec["name"],
            "value": round(value, 2),
            "units": spec["units"],
            "ref_low": low,
            "ref_high": high,
            "abnormal_flag": flag,
            "status": "F",
        }

    return results


def build_oru_batch(
    p: Patient,
    enc: Encounter,
    obs_list: List[Observation],
) -> str:
    parts = [seg_msh("ORU^R01"), seg_pid(p), seg_pv1(enc)]
    parts.append(seg_obr(enc, obs_list[0]) if obs_list else "OBR|1")

    set_id = 1
    for obs in obs_list:
        obx_segments = seg_obx_lines(obs, start_set_id=set_id)
        parts.extend(obx_segments)
        set_id += len(obx_segments)

    return "\r".join(parts)


def build_dft_batch(
    p: Patient,
    enc: Encounter,
    txs: List[Transaction],
    obs_list: List[Observation],
) -> str:
    parts = [
        seg_msh("DFT^P03"),
        seg_evn(enc, "P03"),
        seg_pid(p),
        seg_pv1(enc),
    ]

    primary_observation = obs_list[0] if obs_list else None
    for tx in txs:
        parts.append(seg_ft1(tx, primary_observation))

    diagnosis_set_id = 1
    seen_diagnoses = set()
    for obs in obs_list:
        icd_code = (obs.icd_code or "").strip()
        if not icd_code or icd_code in seen_diagnoses:
            continue
        parts.append(
            seg_dg1(
                enc,
                icd_code=icd_code,
                desc=getattr(obs, "icd_description", ""),
                set_id=diagnosis_set_id,
                diag_type="F",
                diag_dt=obs.completed_time,
            )
        )
        seen_diagnoses.add(icd_code)
        diagnosis_set_id += 1

    if txs:
        parts.append(seg_gt1(txs[0], set_id=1))
        parts.append(seg_in1(txs[0], set_id=1))

    return "\r".join(parts)


def build_orm_labs_batch(
    p: Patient,
    enc: Encounter,
    order_code: str = "SYN_LABS",
    order_text: str = "Synthetic Lab Panel",
) -> str:
    return _build_lab_orm(p, enc, order_code, order_text)


def build_oru_labs_batch(
    p: Patient,
    enc: Encounter,
    start_set_id: int = 20,
    order_code: str = "SYN_LABS",
    order_text: str = "Synthetic Lab Panel",
) -> str:
    labs = _predict_labs_offline()
    return _build_lab_oru(
        p,
        enc,
        labs,
        order_code,
        order_text,
        start_set_id=start_set_id,
    )

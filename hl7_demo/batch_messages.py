"""Network-free message builders used by MediLacra batch experiments.

These mirror the current ORU/DFT/lab projections without importing
``hl7_demo.messages``, which imports the legacy SDOH API module.
"""

from __future__ import annotations

from typing import List

from .labs import (
    build_lab_orm as _build_lab_orm,
    build_lab_oru as _build_lab_oru,
    predict_labs_for_patient,
)
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
    labs = predict_labs_for_patient(p)
    return _build_lab_oru(
        p,
        enc,
        labs,
        order_code,
        order_text,
        start_set_id=start_set_id,
    )

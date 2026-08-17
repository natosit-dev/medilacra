"""Offline ADT builder for experiment/batch generation.

This module intentionally excludes external SDOH enrichment. It preserves the
core ADT structure, synthetic vitals, and Gender Harmony observations while
making batch generation deterministic with respect to local inputs only.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from .generators import choose_gender_harmony_values
from .models import Encounter, Observation, Patient, Transaction
from .segments import (
    seg_dg1,
    seg_evn,
    seg_gt1,
    seg_in1,
    seg_msh,
    seg_obx_gender_identity,
    seg_obx_pronouns,
    seg_obx_spcu,
    seg_pid,
    seg_pv1,
)
from .vitals import build_obx_vitals, predict_vitals


def build_adt_offline(
    p: Patient,
    enc: Encounter,
    tx: Optional[Transaction] = None,
    obs: Optional[Observation] = None,
    *,
    include_vitals: bool = True,
    include_gender_harmony: bool = True,
) -> str:
    """Build ADT^A01 without network/API enrichment.

    The existing vitals model historically falls back to poverty=0 and AQI=50
    when SDOH lookups return nothing. Batch mode uses those same fallback
    inputs directly, so no AirNow/Census/PLACES/BLS request can occur.
    """

    parts = [
        seg_msh("ADT^A01"),
        seg_evn(enc, "A01"),
        seg_pid(p),
        seg_pv1(enc),
    ]
    set_id = 1

    if include_vitals:
        try:
            age = datetime.now().year - datetime.strptime(
                p.date_of_birth, "%Y-%m-%d"
            ).year
            vital_values = predict_vitals(age, 0.0, 50.0)
            vital_obxs = build_obx_vitals(vital_values, start_set_id=set_id)
            parts.extend(vital_obxs)
            set_id += len(vital_obxs)
        except Exception as exc:
            print(f"[WARN] Failed to generate vitals for {p.patient_id}: {exc}")

    if include_gender_harmony:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        gender_values = choose_gender_harmony_values(
            getattr(p, "sex", ""),
            match_bias=0.95,
        )

        gi_code, gi_text, gi_system = gender_values["gi"]
        parts.append(
            seg_obx_gender_identity(
                set_id=set_id,
                gi_code=gi_code,
                gi_text=gi_text,
                gi_system=gi_system,
                effective_dt=now,
                method=("ptReport", "Patient-reported", "HL7"),
                performing_org="MEDILACRAHS",
            )
        )
        set_id += 1

        pronoun_code, pronoun_text, pronoun_system = gender_values["pro"]
        parts.append(
            seg_obx_pronouns(
                set_id=set_id,
                pronoun_code=pronoun_code,
                pronoun_text=pronoun_text,
                pronoun_system=pronoun_system,
                effective_dt=now,
            )
        )
        set_id += 1

        spcu_code, spcu_text, spcu_system = gender_values["spcu"]
        parts.append(
            seg_obx_spcu(
                set_id=set_id,
                spcu_code=spcu_code,
                spcu_text=spcu_text,
                spcu_system=spcu_system,
                effective_dt=now,
                method=("endo", "Endocrinology assessment", "HL7"),
            )
        )

    if obs is not None and getattr(obs, "icd_code", ""):
        parts.append(
            seg_dg1(
                enc,
                icd_code=obs.icd_code,
                desc=obs.icd_description,
                set_id=1,
                diag_type="A",
                diag_dt=obs.completed_time or enc.admit_datetime,
            )
        )

    if tx is not None:
        parts.append(seg_gt1(tx, set_id=1))
        parts.append(seg_in1(tx, set_id=1))

    return "\r".join(parts)

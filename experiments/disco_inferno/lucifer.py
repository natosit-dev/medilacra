"""Lucifer: synthetic evidence that is credible, structurally valid, and false.

This is a closed, synthetic safety experiment. "Unauthorized" is an invented
scenario fact, NOT a HIPAA or legal determination.
"""
from __future__ import annotations

from dataclasses import dataclass
from random import Random
from typing import Any

import pandas as pd


FIELDS = ("event_id", "patient_id", "actor_id", "action", "authorization_status")
STATUSES = {"authorized", "unauthorized"}


@dataclass(frozen=True)
class LuciferResult:
    """Separate synthetic source truth from its believable, false evidence."""

    source_truth: pd.DataFrame
    evidence: dict[str, pd.DataFrame]
    manifest: dict[str, Any]


def _surface_checks(evidence: pd.DataFrame, known_patients: set[str]) -> dict[str, bool]:
    """Checks available to a consumer who does NOT know source truth."""
    schema = tuple(evidence.columns) == FIELDS
    return {
        "schema_valid": schema,
        "row_count_preserved": len(evidence) == 2,
        "no_nulls": bool(evidence.notna().all().all()),
        "unique_event_ids": bool(evidence["event_id"].is_unique) if schema else False,
        "patient_refs_valid": (
            bool(evidence["patient_id"].astype(str).isin(known_patients).all())
            if schema else False
        ),
        "enum_values_valid": (
            bool(evidence["authorization_status"].isin(STATUSES).all())
            if schema else False
        ),
    }


def _claim_of_unauthorized_event(events: pd.DataFrame, event_id: str) -> bool:
    matched = events.loc[events["event_id"] == event_id, "authorization_status"]
    return len(matched) == 1 and matched.iloc[0] == "unauthorized"


def _case_receipt(
    *,
    name: str,
    source_truth: pd.DataFrame,
    evidence: pd.DataFrame,
    target_event_id: str,
    known_patients: set[str],
) -> dict[str, Any]:
    checks = _surface_checks(evidence, known_patients)
    actual = _claim_of_unauthorized_event(source_truth, target_event_id)
    apparent = _claim_of_unauthorized_event(evidence, target_event_id)
    if not all(checks.values()) or actual == apparent:
        raise AssertionError("Lucifer scenario failed its own trust-betrayal contract")
    return {
        "operator": "lucifer_betrayal",
        "case": name,
        "target_event_id": target_event_id,
        "source_claim_unauthorized_event_occurred": actual,
        "evidence_claim_unauthorized_event_occurred": apparent,
        "false_conclusion": actual != apparent,
        "consumer_visible_checks": checks,
        "source_rows": len(source_truth),
        "evidence_rows": len(evidence),
        "source_is_synthetic": True,
        "legal_hipaa_finding": False,
    }


def lucifer(patients: pd.DataFrame, *, inferno_seed: int = 666) -> LuciferResult:
    """Build two evidence-betrayal cases against a fixed synthetic event truth.

    Phantom: replace an authorized event with a fabricated unauthorized event.
    Concealment: relabel a real simulated unauthorized event as authorized.

    Both keep the same columns/row count, valid patients, non-null values,
    unique event IDs, and valid status vocabulary. Only comparison with
    retained source truth establishes the deception.
    """
    if "patient_id" not in patients.columns:
        raise ValueError("Lucifer requires a patients.patient_id column")
    known = list(dict.fromkeys(patients["patient_id"].dropna().astype(str)))
    if not known:
        raise ValueError("Lucifer requires at least one synthetic patient")

    # The source truth depends only on Beatrice, not the corruption seed.
    source_truth = pd.DataFrame(
        [
            ("L-AUTH-001", known[0], "synthetic_actor_A", "disclose", "authorized"),
            ("L-UNAUTH-002", known[-1], "synthetic_actor_B", "disclose", "unauthorized"),
        ],
        columns=list(FIELDS),
    )
    rng = Random(inferno_seed)
    phantom_id = f"L-PHANTOM-{rng.randrange(1_000_000):06d}"

    phantom = source_truth.copy(deep=True)
    phantom.loc[0, "event_id"] = phantom_id
    phantom.loc[0, "authorization_status"] = "unauthorized"

    concealed = source_truth.copy(deep=True)
    concealed.loc[1, "authorization_status"] = "authorized"

    evidence = {"phantom_violation": phantom, "concealed_violation": concealed}
    patient_set = set(known)
    cases = {
        name: _case_receipt(
            name=name,
            source_truth=source_truth,
            evidence=frame,
            target_event_id=(phantom_id if name == "phantom_violation" else "L-UNAUTH-002"),
            known_patients=patient_set,
        )
        for name, frame in evidence.items()
    }
    return LuciferResult(
        source_truth=source_truth,
        evidence=evidence,
        manifest={
            "operator": "lucifer_betrayal",
            "inferno_name": "Lucifer",
            "inferno_seed": inferno_seed,
            "boundary": "synthetic evidence experiment; no real accesses or legal determinations",
            "source_reality_extended_with_synthetic_events": True,
            "cases": cases,
        },
    )

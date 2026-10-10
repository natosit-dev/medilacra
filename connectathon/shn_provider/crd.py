from __future__ import annotations

from typing import Any

from connectathon.shn_medilacra_crd import (
    SHN_PAYER_IDENTIFIER_SYSTEM,
    build_crd_order_sign_request,
)

from .scenario import ScenarioConfig
from .scenario_registry import build_scenario_reality
from .summaries import summarize_crd


def build_request(
    scenario: ScenarioConfig,
    seed: int,
) -> dict[str, Any]:
    if scenario.payer_identifier_system != SHN_PAYER_IDENTIFIER_SYSTEM:
        raise ValueError(
            "current SHN provider adapter supports the documented NAIC-style "
            f"payer identifier system {SHN_PAYER_IDENTIFIER_SYSTEM!r}"
        )
    reality = build_scenario_reality(scenario, seed)
    return build_crd_order_sign_request(
        reality,
        payer_route=scenario.payer_route,
    )


def interpret_response(
    scenario: ScenarioConfig,
    body: dict[str, Any],
) -> dict[str, Any]:
    return summarize_crd(body, expected=scenario.expected_crd)


def should_enter_dtr(
    scenario: ScenarioConfig,
    summary: dict[str, Any],
) -> bool:
    return scenario.has_stage("dtr") and bool(summary.get("questionnaire"))

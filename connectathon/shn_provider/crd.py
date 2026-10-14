from __future__ import annotations

import re
from typing import Any

from connectathon.shn_medilacra_crd import (
    SHN_PAYER_IDENTIFIER_SYSTEM,
    build_crd_order_sign_request,
)

from .scenario import ScenarioConfig
from .scenario_registry import build_scenario_reality
from .summaries import summarize_crd


def validate_payer_route(value: str) -> str:
    """Keep the network payer identifier as a string, including leading zeros."""
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.-]{0,52}", value):
        raise ValueError("payer ID must be 1-53 letters, digits, periods or hyphens (no spaces)")
    return value


def build_request(
    scenario: ScenarioConfig,
    seed: int,
    payer_route: str | None = None,
) -> dict[str, Any]:
    if scenario.payer_identifier_system != SHN_PAYER_IDENTIFIER_SYSTEM:
        raise ValueError(
            "current SHN provider adapter supports the documented NAIC-style "
            f"payer identifier system {SHN_PAYER_IDENTIFIER_SYSTEM!r}"
        )
    reality = build_scenario_reality(scenario, seed)
    return build_crd_order_sign_request(
        reality,
        payer_route=validate_payer_route(payer_route if payer_route is not None else scenario.payer_route),
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

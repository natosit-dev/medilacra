from __future__ import annotations

from typing import Any

from connectathon.shn_lumbar_fusion_pas import build_documented_pas_bundle

from .scenario import ScenarioConfig
from .scenario_registry import build_scenario_reality
from .summaries import summarize_pas


def build_request(
    scenario: ScenarioConfig,
    seed: int,
    questionnaire_response: dict[str, Any],
) -> dict[str, Any]:
    if not scenario.has_stage("pas"):
        raise ValueError(f"scenario {scenario.id!r} has no PAS stage")

    reality = build_scenario_reality(scenario, seed)

    # Reuse the already-proven PAS bundle mechanics while the provider module
    # becomes the stable boundary. The config/reality checks above prevent the
    # scenario definition from silently drifting away from that implementation.
    #
    # When a second PAS-capable scenario is added, parameterize the proven
    # builder behind this function rather than branching in the UI.
    if scenario.id != "lumbar-fusion-auth":
        raise ValueError(
            f"no proven PAS request builder is registered for {scenario.id!r}"
        )

    bundle = build_documented_pas_bundle(seed, questionnaire_response)
    serialized = str(bundle)
    if reality.service_code not in serialized:
        raise ValueError("configured service code missing from PAS request")
    if reality.diagnosis_code and reality.diagnosis_code not in serialized:
        raise ValueError("configured diagnosis missing from PAS request")
    return bundle


def interpret_response(
    scenario: ScenarioConfig,
    body: dict[str, Any],
) -> dict[str, Any]:
    return summarize_pas(body, expected=scenario.expected_pas)

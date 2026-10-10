from __future__ import annotations

from typing import Callable

from connectathon.shn_lumbar_fusion import build_lumbar_fusion_reality
from connectathon.shn_mvp0 import SHNMVP0Reality, build_reality, reality_manifest
from connectathon.shn_rule_matrix import build_explicit_not_covered_reality

from .scenario import ScenarioConfig


REALITY_BUILDERS: dict[str, Callable[[int], SHNMVP0Reality]] = {
    "default": build_reality,
    "lumbar_fusion": build_lumbar_fusion_reality,
    "explicit_not_covered": build_explicit_not_covered_reality,
}


def build_scenario_reality(
    scenario: ScenarioConfig,
    seed: int,
) -> SHNMVP0Reality:
    try:
        builder = REALITY_BUILDERS[scenario.reality_builder]
    except KeyError as exc:
        raise ValueError(
            f"scenario {scenario.id!r} names unknown reality builder "
            f"{scenario.reality_builder!r}"
        ) from exc

    reality = builder(seed)
    expected_service = scenario.service
    if reality.service_code != expected_service["code"]:
        raise ValueError(
            f"scenario {scenario.id}: reality service code {reality.service_code!r} "
            f"does not match config {expected_service['code']!r}"
        )
    if reality.service_display != expected_service["display"]:
        raise ValueError(
            f"scenario {scenario.id}: reality service display does not match config"
        )

    diagnosis = scenario.diagnosis
    if diagnosis is not None:
        actual = (
            reality.diagnosis_system,
            reality.diagnosis_code,
            reality.diagnosis_display,
        )
        configured = (
            diagnosis["system"],
            diagnosis["code"],
            diagnosis["display"],
        )
        if actual != configured:
            raise ValueError(
                f"scenario {scenario.id}: reality diagnosis does not match config"
            )
    return reality


def scenario_reality_manifest(
    scenario: ScenarioConfig,
    seed: int,
) -> dict:
    manifest = reality_manifest(build_scenario_reality(scenario, seed))
    manifest["scenario"] = {
        "id": scenario.id,
        "label": scenario.label,
        "description": scenario.description,
        "notes": scenario.notes,
        "config": str(scenario.source_path),
    }
    return manifest

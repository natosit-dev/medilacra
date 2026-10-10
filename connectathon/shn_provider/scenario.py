from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


SCENARIO_DIR = Path(__file__).resolve().parents[1] / "shn_scenarios"
ALLOWED_STAGES = {"crd", "dtr", "pas"}
REQUIRED_TOP_LEVEL = {
    "schema_version",
    "id",
    "label",
    "description",
    "reality_builder",
    "payer",
    "workflow",
    "service",
    "expected",
}


@dataclass(frozen=True)
class ScenarioConfig:
    raw: dict[str, Any]
    source_path: Path

    @property
    def id(self) -> str:
        return self.raw["id"]

    @property
    def label(self) -> str:
        return self.raw["label"]

    @property
    def description(self) -> str:
        return self.raw.get("description", "")

    @property
    def notes(self) -> list[str]:
        return list(self.raw.get("notes", []))

    @property
    def reality_builder(self) -> str:
        return self.raw["reality_builder"]

    @property
    def payer_route(self) -> str:
        return self.raw["payer"]["route"]

    @property
    def payer_identifier_system(self) -> str:
        return self.raw["payer"]["identifier_system"]

    @property
    def stages(self) -> tuple[str, ...]:
        return tuple(self.raw["workflow"]["stages"])

    @property
    def service(self) -> dict[str, Any]:
        return self.raw["service"]

    @property
    def diagnosis(self) -> dict[str, Any] | None:
        return self.raw.get("diagnosis")

    @property
    def expected_crd(self) -> dict[str, Any]:
        return self.raw["expected"]["crd"]

    @property
    def expected_pas(self) -> dict[str, Any] | None:
        return self.raw["expected"].get("pas")

    @property
    def questionnaire_mappings(self) -> dict[str, Any]:
        return self.raw.get("questionnaire_mappings", {})

    def questionnaire_mapping(self, canonical: str) -> dict[str, Any] | None:
        return self.questionnaire_mappings.get(canonical)

    def has_stage(self, stage: str) -> bool:
        return stage in self.stages


def _require_string(value: Any, where: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{where} must be a non-empty string")
    return value


def validate_scenario_dict(data: dict[str, Any], source: str = "<memory>") -> None:
    missing = sorted(REQUIRED_TOP_LEVEL - set(data))
    if missing:
        raise ValueError(f"{source}: missing required scenario fields: {', '.join(missing)}")
    if data.get("schema_version") != "1.0":
        raise ValueError(f"{source}: unsupported schema_version {data.get('schema_version')!r}")

    _require_string(data["id"], f"{source}.id")
    _require_string(data["label"], f"{source}.label")
    _require_string(data["reality_builder"], f"{source}.reality_builder")

    payer = data["payer"]
    if not isinstance(payer, dict):
        raise ValueError(f"{source}.payer must be an object")
    _require_string(payer.get("route"), f"{source}.payer.route")
    _require_string(
        payer.get("identifier_system"),
        f"{source}.payer.identifier_system",
    )

    service = data["service"]
    if not isinstance(service, dict):
        raise ValueError(f"{source}.service must be an object")
    for key in ("system", "code", "display"):
        _require_string(service.get(key), f"{source}.service.{key}")

    workflow = data["workflow"]
    stages = workflow.get("stages") if isinstance(workflow, dict) else None
    if not isinstance(stages, list) or not stages:
        raise ValueError(f"{source}.workflow.stages must be a non-empty array")
    unknown = sorted(set(stages) - ALLOWED_STAGES)
    if unknown:
        raise ValueError(f"{source}: unknown workflow stages: {', '.join(unknown)}")
    if stages[0] != "crd":
        raise ValueError(f"{source}: provider workflow must begin with crd")
    if "pas" in stages and "dtr" not in stages:
        raise ValueError(f"{source}: pas currently requires dtr documentation")

    expected = data["expected"]
    if not isinstance(expected, dict) or not isinstance(expected.get("crd"), dict):
        raise ValueError(f"{source}.expected.crd must be an object")

    mappings = data.get("questionnaire_mappings", {})
    if not isinstance(mappings, dict):
        raise ValueError(f"{source}.questionnaire_mappings must be an object")
    for canonical, mapping in mappings.items():
        _require_string(canonical, f"{source}.questionnaire_mappings key")
        items = mapping.get("items") if isinstance(mapping, dict) else None
        if not isinstance(items, dict):
            raise ValueError(f"{source}: questionnaire {canonical} must define items")
        for link_id, item in items.items():
            _require_string(link_id, f"{source}.questionnaire linkId")
            if not isinstance(item, dict):
                raise ValueError(f"{source}: mapping {link_id} must be an object")
            for key in ("text", "type", "fact_path", "semantic_name"):
                _require_string(item.get(key), f"{source}.mapping.{link_id}.{key}")


def load_scenario(path: str | Path) -> ScenarioConfig:
    source_path = Path(path)
    data = json.loads(source_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{source_path}: scenario root must be an object")
    validate_scenario_dict(data, str(source_path))
    return ScenarioConfig(raw=data, source_path=source_path)


def list_scenarios() -> list[ScenarioConfig]:
    scenarios = [
        load_scenario(path)
        for path in sorted(SCENARIO_DIR.glob("*.json"))
        if path.name != "schema.json"
    ]
    scenarios.sort(key=lambda scenario: (scenario.raw.get("order", 999), scenario.id))
    ids = [scenario.id for scenario in scenarios]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate SHN scenario ids")
    return scenarios


def get_scenario(scenario_id: str) -> ScenarioConfig:
    for scenario in list_scenarios():
        if scenario.id == scenario_id:
            return scenario
    raise KeyError(f"unknown SHN scenario: {scenario_id}")

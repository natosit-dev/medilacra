from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


TEST_CASE_DIR = Path(__file__).resolve().parents[1] / "shn_test_cases"


@dataclass(frozen=True)
class ReferenceTestCase:
    raw: dict[str, Any]
    source_path: Path

    @property
    def id(self) -> str:
        return self.raw["id"]

    @property
    def label(self) -> str:
        return self.raw["label"]

    @property
    def kind(self) -> str:
        return self.raw["kind"]

    @property
    def description(self) -> str:
        return self.raw.get("description", "")

    @property
    def notes(self) -> list[str]:
        return list(self.raw.get("notes", []))

    @property
    def route(self) -> str | None:
        return self.raw.get("route")

    @property
    def member_id(self) -> str:
        return self.raw.get("member_id") or "MBR-COVERED"

    @property
    def service(self) -> dict[str, Any] | None:
        return self.raw.get("service")

    @property
    def operations(self) -> list[dict[str, Any]]:
        return list(self.raw["operations"])

    @property
    def manual(self) -> bool:
        return bool(self.raw.get("manual", False))


def validate_test_case_dict(data: dict[str, Any], source: str = "<memory>") -> None:
    required = {"schema_version", "id", "label", "kind", "description", "operations", "provenance"}
    missing = sorted(required - set(data))
    if missing:
        raise ValueError(f"{source}: missing fields: {', '.join(missing)}")
    if data["schema_version"] != "1.0":
        raise ValueError(f"{source}: unsupported schema_version")
    if data["kind"] not in {"positive", "negative"}:
        raise ValueError(f"{source}: invalid kind {data['kind']!r}")
    if not isinstance(data["operations"], list) or not data["operations"]:
        raise ValueError(f"{source}: operations must be a non-empty array")
    ids = []
    for operation in data["operations"]:
        if not isinstance(operation, dict):
            raise ValueError(f"{source}: operation must be an object")
        for key in ("id", "type", "expected"):
            if key not in operation:
                raise ValueError(f"{source}: operation missing {key}")
        ids.append(operation["id"])
    if len(ids) != len(set(ids)):
        raise ValueError(f"{source}: operation ids must be unique")


def load_test_case(path: str | Path) -> ReferenceTestCase:
    source_path = Path(path)
    data = json.loads(source_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{source_path}: test case root must be an object")
    validate_test_case_dict(data, str(source_path))
    return ReferenceTestCase(data, source_path)


def list_test_cases(kind: str | None = None) -> list[ReferenceTestCase]:
    paths = [
        path
        for path in TEST_CASE_DIR.rglob("*.json")
        if path.name != "schema.json"
    ]
    cases = [load_test_case(path) for path in paths]
    if kind is not None:
        cases = [case for case in cases if case.kind == kind]
    cases.sort(key=lambda case: (case.raw.get("order", 999), case.id))
    ids = [case.id for case in cases]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate SHN reference test ids")
    return cases


def get_test_case(test_id: str) -> ReferenceTestCase:
    for case in list_test_cases():
        if case.id == test_id:
            return case
    raise KeyError(f"unknown SHN reference test case: {test_id}")

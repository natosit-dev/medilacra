from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class StageState:
    request: dict[str, Any] | None = None
    response: dict[str, Any] | None = None
    summary: dict[str, Any] | None = None
    transport: dict[str, Any] | None = None
    error: str | None = None

    def manifest(self) -> dict[str, Any]:
        return {
            "built": self.request is not None,
            "responded": self.response is not None,
            "summary": self.summary,
            "transport": self.transport,
            "error": self.error,
        }


@dataclass
class ProviderCase:
    scenario_id: str
    scenario_label: str
    seed: int
    case_id: str
    reality: dict[str, Any]
    status: str = "created"
    stop_reason: str | None = None
    crd: StageState = field(default_factory=StageState)
    dtr: StageState = field(default_factory=StageState)
    pas: StageState = field(default_factory=StageState)
    questionnaire_response: dict[str, Any] | None = None
    materialization: dict[str, Any] | None = None
    artifact_dir: str | None = None

    def manifest(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "scenario_label": self.scenario_label,
            "seed": self.seed,
            "case_id": self.case_id,
            "status": self.status,
            "stop_reason": self.stop_reason,
            "artifact_dir": self.artifact_dir,
            "crd": self.crd.manifest(),
            "dtr": self.dtr.manifest(),
            "documentation": {
                "materialized": self.questionnaire_response is not None,
                "provenance": self.materialization,
            },
            "pas": self.pas.manifest(),
        }

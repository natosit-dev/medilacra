from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .state import ProviderCase


DEFAULT_ROOT = Path("connectathon/results/shn_provider")


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def write_case_artifacts(
    case: ProviderCase,
    root: str | Path = DEFAULT_ROOT,
) -> Path:
    case_dir = Path(root) / case.case_id
    case_dir.mkdir(parents=True, exist_ok=True)

    _write_json(case_dir / "reality.json", case.reality)

    for name, stage in (("crd", case.crd), ("dtr", case.dtr), ("pas", case.pas)):
        if stage.request is not None:
            _write_json(case_dir / name / "request.json", stage.request)
        if stage.response is not None:
            _write_json(case_dir / name / "response.json", stage.response)
        if stage.summary is not None:
            filename = "decision.json" if name == "pas" else "summary.json"
            _write_json(case_dir / name / filename, stage.summary)
        if stage.transport is not None:
            _write_json(case_dir / name / "transport.json", stage.transport)

    if case.questionnaire_response is not None:
        _write_json(
            case_dir / "dtr" / "questionnaire_response.json",
            case.questionnaire_response,
        )
    if case.materialization is not None:
        _write_json(
            case_dir / "dtr" / "materialization.json",
            case.materialization,
        )

    case.artifact_dir = str(case_dir)
    _write_json(case_dir / "manifest.json", case.manifest())
    return case_dir

from __future__ import annotations

import hashlib
import json
import platform
import subprocess
import sys
import uuid
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .log_schema import LOG_SCHEMA_VERSION, validate_event, validate_run_document


BLOCKED_KEYS = {
    "authorization_header",
    "authorization_value",
    "http_authorization",
    "client_secret",
    "access_token",
    "bearer_token",
    "basic_credential",
    "private_key",
    "client_assertion",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalized_key(key: Any) -> str:
    return str(key).strip().lower().replace("-", "_")


def assert_no_sensitive_keys(value: Any, path: str = "$") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = _normalized_key(key)
            if normalized in BLOCKED_KEYS:
                raise ValueError(
                    f"sensitive key {key!r} cannot be persisted at {path}"
                )
            assert_no_sensitive_keys(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            assert_no_sensitive_keys(child, f"{path}[{index}]")


def write_json(path: Path, value: Any) -> None:
    assert_no_sensitive_keys(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def write_jsonl(path: Path, events: list[dict[str, Any]]) -> None:
    assert_no_sensitive_keys(events)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for event in events:
            validate_event(event)
            handle.write(json.dumps(event, sort_keys=True) + "\n")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def artifact_record(path: Path, root: Path, role: str) -> dict[str, Any]:
    return {
        "role": role,
        "path": path.relative_to(root).as_posix(),
        "size_bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def _git_value(args: list[str]) -> str | None:
    try:
        completed = subprocess.run(
            ["git", *args],
            check=True,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except Exception:
        return None
    value = completed.stdout.strip()
    return value or None


def execution_context(execution_mode: str) -> dict[str, Any]:
    status = _git_value(["status", "--porcelain"])
    return {
        "execution_mode": execution_mode,
        "git_branch": _git_value(["rev-parse", "--abbrev-ref", "HEAD"]),
        "git_commit": _git_value(["rev-parse", "HEAD"]),
        "git_dirty": bool(status) if status is not None else None,
        "python_version": platform.python_version(),
        "python_implementation": platform.python_implementation(),
        "platform_system": platform.system(),
        "platform_release": platform.release(),
        "log_schema_version": LOG_SCHEMA_VERSION,
    }


def _join_path(base: str, token: str) -> str:
    if not base:
        return token
    if token.startswith("["):
        return f"{base}{token}"
    return f"{base}.{token}"


def json_diff(before: Any, after: Any, path: str = "$") -> list[dict[str, Any]]:
    changes: list[dict[str, Any]] = []
    if type(before) is not type(after):
        return [{"path": path, "before": deepcopy(before), "after": deepcopy(after)}]

    if isinstance(before, dict):
        keys = sorted(set(before) | set(after), key=str)
        for key in keys:
            child_path = _join_path(path, str(key))
            if key not in before:
                changes.append(
                    {"path": child_path, "before": None, "after": deepcopy(after[key])}
                )
            elif key not in after:
                changes.append(
                    {"path": child_path, "before": deepcopy(before[key]), "after": None}
                )
            else:
                changes.extend(json_diff(before[key], after[key], child_path))
        return changes

    if isinstance(before, list):
        length = max(len(before), len(after))
        for index in range(length):
            child_path = _join_path(path, f"[{index}]")
            if index >= len(before):
                changes.append(
                    {"path": child_path, "before": None, "after": deepcopy(after[index])}
                )
            elif index >= len(after):
                changes.append(
                    {"path": child_path, "before": deepcopy(before[index]), "after": None}
                )
            else:
                changes.extend(json_diff(before[index], after[index], child_path))
        return changes

    if before != after:
        changes.append({"path": path, "before": deepcopy(before), "after": deepcopy(after)})
    return changes


@dataclass
class RunLogger:
    run_id: str
    test_id: str
    execution_mode: str = "python"

    def __post_init__(self) -> None:
        self.events: list[dict[str, Any]] = []
        self.current_operation_id: str | None = None
        self._sequence = 0
        self.context = execution_context(self.execution_mode)

    def set_operation(self, operation_id: str | None) -> None:
        self.current_operation_id = operation_id

    def emit(
        self,
        event_type: str,
        phase: str,
        data: dict[str, Any] | None = None,
        *,
        artifact_refs: list[str] | None = None,
        operation_id: str | None = None,
    ) -> dict[str, Any]:
        self._sequence += 1
        event = {
            "schema_version": LOG_SCHEMA_VERSION,
            "event_id": str(uuid.uuid4()),
            "run_id": self.run_id,
            "sequence": self._sequence,
            "timestamp": utc_now(),
            "event_type": event_type,
            "test_id": self.test_id,
            "operation_id": (
                operation_id
                if operation_id is not None
                else self.current_operation_id
            ),
            "phase": phase,
            "data": deepcopy(data or {}),
            "artifact_refs": list(artifact_refs or []),
        }
        assert_no_sensitive_keys(event)
        validate_event(event)
        self.events.append(event)
        return event

    def build_run_document(
        self,
        *,
        run_manifest: dict[str, Any],
        test_contract: dict[str, Any],
        artifact_index: list[dict[str, Any]],
    ) -> dict[str, Any]:
        document = {
            "schema_version": LOG_SCHEMA_VERSION,
            "run": deepcopy(run_manifest),
            "execution_context": deepcopy(self.context),
            "test_contract": deepcopy(test_contract),
            "events": deepcopy(self.events),
            "artifact_index": deepcopy(artifact_index),
        }
        assert_no_sensitive_keys(document)
        validate_run_document(document)
        return document


def event_rows(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for event in events:
        data = event.get("data") or {}
        summary = (
            data.get("summary")
            or data.get("status")
            or data.get("path")
            or data.get("field")
            or data.get("builder")
            or data.get("mutation")
            or data.get("http_status")
            or data.get("result")
            or ""
        )
        rows.append(
            {
                "seq": event["sequence"],
                "time": event["timestamp"],
                "event": event["event_type"],
                "operation": event.get("operation_id"),
                "phase": event["phase"],
                "summary": summary,
            }
        )
    return rows

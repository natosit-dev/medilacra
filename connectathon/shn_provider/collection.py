from __future__ import annotations

import csv
import io
import json
import uuid
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .run_logging import assert_no_sensitive_keys


DEFAULT_REFERENCE_ROOT = Path("connectathon/results/shn_reference_suite")
COLLECTION_SCHEMA_VERSION = "1.0"

README = """MediLacra SHN Transaction Log Collection

This archive collects multiple recorded SHN reference-suite runs without sending
new traffic to SHN.

Top-level files:
- collection.json: collection manifest and run inventory.
- transactions.jsonl: one object per recorded network transaction.
- events.jsonl: all available full-log events, ordered across runs.
- transactions.csv: flattened human-friendly transaction index.
- README.txt: this file.
- runs/: original per-run evidence copied into the collection.

Run logging levels:
- full: run.json + events.jsonl were recorded by the full execution logger.
- legacy-artifacts: the run predates full event logging; existing result and
  operation artifacts are preserved, but missing chronology is not reconstructed.

Credential values are intentionally excluded by the MediLacra logging path.
This archive may contain synthetic member identifiers, request/response payloads,
correlation identifiers, SHN leg identifiers and operator-console trace links.

A FAIL means observed behavior differed from the recorded test contract. It is
not synonymous with transport failure.
"""


@dataclass(frozen=True)
class CollectedRun:
    path: Path
    result: dict[str, Any]
    run_document: dict[str, Any] | None
    events: list[dict[str, Any]]
    logging_level: str

    @property
    def run_id(self) -> str:
        return str(self.result.get("run_id") or self.path.name)

    @property
    def test_id(self) -> str:
        return str(self.result.get("test_id") or "unknown")

    @property
    def kind(self) -> str | None:
        value = self.result.get("kind")
        return str(value) if value is not None else None

    @property
    def started_at(self) -> str | None:
        value = self.result.get("started_at")
        return str(value) if value is not None else None


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected JSON object")
    assert_no_sensitive_keys(value)
    return value


def _load_events(path: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    if not path.is_file():
        return events
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(
                f"{path}:{line_number}: expected JSON object"
            )
        assert_no_sensitive_keys(value)
        events.append(value)
    return events


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.strip()
    if len(text) == 10:
        text += "T00:00:00+00:00"
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def discover_runs(
    root: str | Path = DEFAULT_REFERENCE_ROOT,
    *,
    since: str | None = None,
    test_ids: Iterable[str] | None = None,
    kind: str | None = None,
) -> list[CollectedRun]:
    root = Path(root)
    if not root.is_dir():
        return []

    wanted_tests = {
        str(test_id).upper()
        for test_id in (test_ids or [])
    }
    since_dt = _parse_time(since)
    runs: list[CollectedRun] = []

    for result_path in sorted(root.glob("*/result.json")):
        run_dir = result_path.parent
        if run_dir.name == "collections":
            continue

        result = _load_json(result_path)
        run_doc_path = run_dir / "run.json"
        events_path = run_dir / "events.jsonl"
        run_document = (
            _load_json(run_doc_path)
            if run_doc_path.is_file()
            else None
        )
        events = _load_events(events_path)
        logging_level = (
            "full"
            if run_document is not None and events
            else "legacy-artifacts"
        )
        collected = CollectedRun(
            path=run_dir,
            result=result,
            run_document=run_document,
            events=events,
            logging_level=logging_level,
        )

        if wanted_tests and collected.test_id.upper() not in wanted_tests:
            continue
        if kind and (collected.kind or "").lower() != kind.lower():
            continue
        if since_dt is not None:
            started = _parse_time(collected.started_at)
            if started is None or started < since_dt:
                continue
        runs.append(collected)

    runs.sort(
        key=lambda run: (
            _parse_time(run.started_at)
            or datetime.min.replace(tzinfo=timezone.utc),
            run.run_id,
        )
    )
    return runs


def _operation_map(run: CollectedRun) -> dict[str, dict[str, Any]]:
    operations = run.result.get("operations") or []
    return {
        str(operation.get("operation_id")): operation
        for operation in operations
        if isinstance(operation, dict)
        and operation.get("operation_id") is not None
    }


def _full_transactions(run: CollectedRun) -> list[dict[str, Any]]:
    operations = _operation_map(run)
    responses = [
        event
        for event in run.events
        if event.get("event_type") == "http.response.received"
    ]
    used_response_ids: set[str] = set()
    transactions: list[dict[str, Any]] = []

    for ordinal, request_event in enumerate(
        (
            event
            for event in run.events
            if event.get("event_type") == "http.request.sent"
        ),
        start=1,
    ):
        request_data = request_event.get("data") or {}
        operation_id = request_event.get("operation_id")
        correlation_id = request_data.get("correlation_id")
        request_label = request_data.get("request_label")
        response_event = None

        for candidate in responses:
            event_id = str(candidate.get("event_id"))
            if event_id in used_response_ids:
                continue
            if candidate.get("operation_id") != operation_id:
                continue
            candidate_data = candidate.get("data") or {}
            candidate_correlation = (
                candidate_data.get("sent_correlation_id")
                or candidate_data.get("correlation_id")
            )
            if (
                correlation_id is not None
                and candidate_correlation != correlation_id
            ):
                continue
            if candidate_data.get("request_label") != request_label:
                continue
            response_event = candidate
            used_response_ids.add(event_id)
            break

        operation = operations.get(str(operation_id), {})
        response_data = (
            response_event.get("data") or {}
            if response_event is not None
            else {}
        )
        transactions.append(
            {
                "collection_schema_version": COLLECTION_SCHEMA_VERSION,
                "transaction_id": (
                    f"{run.run_id}:{operation_id or 'unknown'}:{ordinal}"
                ),
                "run_id": run.run_id,
                "test_id": run.test_id,
                "kind": run.kind,
                "logging_level": run.logging_level,
                "operation_id": operation_id,
                "operation_type": operation.get("operation_type"),
                "request_label": request_label,
                "request_timestamp": request_event.get("timestamp"),
                "response_timestamp": (
                    response_event.get("timestamp")
                    if response_event is not None
                    else None
                ),
                "method": request_data.get("method"),
                "path": request_data.get("path"),
                "url": request_data.get("url"),
                "content_type": request_data.get("content_type"),
                "request_body": request_data.get("body"),
                "http_status": response_data.get("http_status"),
                "response_body": response_data.get("body"),
                "correlation_id": (
                    response_data.get("correlation_id")
                    or correlation_id
                ),
                "sent_correlation_id": (
                    response_data.get("sent_correlation_id")
                    or correlation_id
                ),
                "shn_leg_id": response_data.get("shn_leg_id"),
                "trace_url": response_data.get("trace_url"),
                "elapsed_ms": response_data.get("elapsed_ms"),
                "attempts": response_data.get("attempts"),
                "warning": response_data.get("warning"),
                "link": response_data.get("link"),
                "expected": operation.get("expected"),
                "observed": operation.get("observed"),
                "passed": operation.get("passed"),
            }
        )
    return transactions


def _legacy_transactions(run: CollectedRun) -> list[dict[str, Any]]:
    transactions: list[dict[str, Any]] = []
    for ordinal, operation in enumerate(
        run.result.get("operations") or [],
        start=1,
    ):
        if not isinstance(operation, dict):
            continue
        operation_id = operation.get("operation_id")
        transport = operation.get("transport")
        request = None
        response = None

        op_dirs = sorted(
            run.path.glob(f"operations/*-{operation_id}")
        )
        if op_dirs:
            request_path = op_dirs[0] / "request.json"
            response_path = op_dirs[0] / "response.json"
            if request_path.is_file():
                request = _load_json(request_path)
            if response_path.is_file():
                response = json.loads(
                    response_path.read_text(encoding="utf-8")
                )
                assert_no_sensitive_keys(response)

        legs: list[tuple[str | None, dict[str, Any], Any]] = []
        if isinstance(transport, dict) and any(
            key in transport for key in ("first", "second")
        ):
            for label in ("first", "second"):
                leg = transport.get(label)
                if isinstance(leg, dict):
                    leg_response = (
                        response.get(label)
                        if isinstance(response, dict)
                        else None
                    )
                    legs.append((label, leg, leg_response))
        elif isinstance(transport, dict):
            legs.append((None, transport, response))
        else:
            legs.append((None, {}, response))

        for leg_number, (label, leg, leg_response) in enumerate(
            legs,
            start=1,
        ):
            transactions.append(
                {
                    "collection_schema_version": COLLECTION_SCHEMA_VERSION,
                    "transaction_id": (
                        f"{run.run_id}:{operation_id or ordinal}:"
                        f"{label or leg_number}"
                    ),
                    "run_id": run.run_id,
                    "test_id": run.test_id,
                    "kind": run.kind,
                    "logging_level": run.logging_level,
                    "operation_id": operation_id,
                    "operation_type": operation.get("operation_type"),
                    "request_label": label,
                    "request_timestamp": None,
                    "response_timestamp": None,
                    "method": "POST",
                    "path": None,
                    "url": None,
                    "content_type": None,
                    "request_body": request,
                    "http_status": leg.get("status_code"),
                    "response_body": leg_response,
                    "correlation_id": leg.get("correlation_id"),
                    "sent_correlation_id": leg.get(
                        "sent_correlation_id"
                    ),
                    "shn_leg_id": leg.get("leg_id"),
                    "trace_url": leg.get("trace_url"),
                    "elapsed_ms": leg.get("elapsed_ms"),
                    "attempts": leg.get("attempts"),
                    "warning": leg.get("warning"),
                    "link": leg.get("link"),
                    "expected": operation.get("expected"),
                    "observed": operation.get("observed"),
                    "passed": operation.get("passed"),
                }
            )
    return transactions


def transactions_for_run(run: CollectedRun) -> list[dict[str, Any]]:
    transactions = (
        _full_transactions(run)
        if run.logging_level == "full"
        else _legacy_transactions(run)
    )
    assert_no_sensitive_keys(transactions)
    return transactions


def combined_events(
    runs: list[CollectedRun],
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for run in runs:
        for event in run.events:
            entries.append(dict(event))

    entries.sort(
        key=lambda event: (
            _parse_time(event.get("timestamp"))
            or datetime.min.replace(tzinfo=timezone.utc),
            str(event.get("run_id") or ""),
            int(event.get("sequence") or 0),
        )
    )
    for collection_sequence, event in enumerate(
        entries,
        start=1,
    ):
        event["collection_sequence"] = collection_sequence
    assert_no_sensitive_keys(entries)
    return entries


def _run_manifest(
    run: CollectedRun,
    transaction_count: int,
) -> dict[str, Any]:
    return {
        "run_id": run.run_id,
        "test_id": run.test_id,
        "kind": run.kind,
        "started_at": run.started_at,
        "completed_at": run.result.get("completed_at"),
        "passed": run.result.get("passed"),
        "manual": run.result.get("manual"),
        "logging_level": run.logging_level,
        "event_count": len(run.events),
        "transaction_count": transaction_count,
        "source_directory": run.path.name,
    }


def build_collection_data(
    runs: list[CollectedRun],
) -> tuple[
    dict[str, Any],
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    transactions: list[dict[str, Any]] = []
    run_entries: list[dict[str, Any]] = []
    for run in runs:
        run_transactions = transactions_for_run(run)
        transactions.extend(run_transactions)
        run_entries.append(
            _run_manifest(run, len(run_transactions))
        )

    events = combined_events(runs)
    passed = sum(entry.get("passed") is True for entry in run_entries)
    failed = sum(entry.get("passed") is False for entry in run_entries)
    manual = sum(entry.get("passed") is None for entry in run_entries)
    full = sum(
        entry["logging_level"] == "full"
        for entry in run_entries
    )
    legacy = len(run_entries) - full

    manifest = {
        "schema_version": COLLECTION_SCHEMA_VERSION,
        "collection_id": (
            "shn-transaction-logs-"
            + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            + "-"
            + uuid.uuid4().hex[:8]
        ),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "connectathon/results/shn_reference_suite",
        "summary": {
            "run_count": len(run_entries),
            "transaction_count": len(transactions),
            "event_count": len(events),
            "full_log_runs": full,
            "legacy_artifact_runs": legacy,
            "passed_runs": passed,
            "failed_runs": failed,
            "manual_runs": manual,
            "test_ids": sorted(
                {entry["test_id"] for entry in run_entries}
            ),
        },
        "runs": run_entries,
    }
    assert_no_sensitive_keys(manifest)
    assert_no_sensitive_keys(transactions)
    assert_no_sensitive_keys(events)
    return manifest, transactions, events


CSV_COLUMNS = [
    "run_id",
    "test_id",
    "kind",
    "logging_level",
    "operation_id",
    "operation_type",
    "request_label",
    "request_timestamp",
    "response_timestamp",
    "method",
    "path",
    "http_status",
    "correlation_id",
    "shn_leg_id",
    "trace_url",
    "elapsed_ms",
    "attempts",
    "passed",
    "expected_json",
    "observed_json",
]


def transactions_csv(
    transactions: list[dict[str, Any]],
) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(
        buffer,
        fieldnames=CSV_COLUMNS,
        extrasaction="ignore",
    )
    writer.writeheader()
    for transaction in transactions:
        row = dict(transaction)
        row["expected_json"] = json.dumps(
            transaction.get("expected"),
            sort_keys=True,
        )
        row["observed_json"] = json.dumps(
            transaction.get("observed"),
            sort_keys=True,
        )
        writer.writerow(row)
    return buffer.getvalue()


def _jsonl_bytes(rows: list[dict[str, Any]]) -> bytes:
    return (
        "".join(
            json.dumps(row, sort_keys=True) + "\n"
            for row in rows
        )
    ).encode("utf-8")


def _safe_run_files(run: CollectedRun) -> list[Path]:
    files: list[Path] = []
    for name in ("run.json", "events.jsonl", "result.json"):
        path = run.path / name
        if path.is_file():
            files.append(path)

    operations = run.path / "operations"
    if operations.is_dir():
        files.extend(
            path
            for path in sorted(operations.rglob("*"))
            if path.is_file()
        )
    return files


def collection_zip_bytes(
    runs: list[CollectedRun],
) -> tuple[bytes, dict[str, Any]]:
    manifest, transactions, events = build_collection_data(
        runs
    )
    csv_text = transactions_csv(transactions)

    buffer = io.BytesIO()
    with zipfile.ZipFile(
        buffer,
        "w",
        compression=zipfile.ZIP_DEFLATED,
    ) as archive:
        archive.writestr("README.txt", README)
        archive.writestr(
            "collection.json",
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        )
        archive.writestr(
            "transactions.jsonl",
            _jsonl_bytes(transactions),
        )
        archive.writestr(
            "events.jsonl",
            _jsonl_bytes(events),
        )
        archive.writestr(
            "transactions.csv",
            csv_text,
        )

        for run in runs:
            prefix = Path("runs") / run.run_id
            for path in _safe_run_files(run):
                relative = path.relative_to(run.path)
                archive.write(
                    path,
                    (prefix / relative).as_posix(),
                )

    payload = buffer.getvalue()
    return payload, manifest


def build_collection_zip(
    runs: list[CollectedRun],
    *,
    root: str | Path = DEFAULT_REFERENCE_ROOT,
    output_path: str | Path | None = None,
) -> tuple[Path, dict[str, Any]]:
    payload, manifest = collection_zip_bytes(runs)
    root = Path(root)
    target = (
        Path(output_path)
        if output_path is not None
        else (
            root
            / "collections"
            / f"{manifest['collection_id']}.zip"
        )
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(payload)
    return target, manifest

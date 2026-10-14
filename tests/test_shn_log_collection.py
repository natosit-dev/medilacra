from __future__ import annotations

import csv
import io
import json
import zipfile
from pathlib import Path

import pytest

from connectathon.shn_provider.collection import (
    build_collection_data,
    collection_zip_bytes,
    discover_runs,
    transactions_csv,
)


def _write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, values) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(value) + "\n" for value in values),
        encoding="utf-8",
    )


def _full_run(root: Path) -> Path:
    run_id = "tp01-20261014T120000Z-full"
    run = root / run_id
    result = {
        "test_id": "TP-01",
        "label": "Full round trip",
        "kind": "positive",
        "run_id": run_id,
        "started_at": "2026-10-14T12:00:00+00:00",
        "completed_at": "2026-10-14T12:00:02+00:00",
        "passed": True,
        "manual": False,
        "operations": [
            {
                "operation_id": "crd",
                "operation_type": "crd",
                "expected": {"http_status": 200},
                "observed": {"http_status": 200, "covered": "conditional"},
                "passed": True,
                "transport": {
                    "status_code": 200,
                    "correlation_id": "corr-full-1",
                    "sent_correlation_id": "corr-full-1",
                    "leg_id": "leg-full-1",
                    "trace_url": "https://example.invalid/trace/corr-full-1",
                    "elapsed_ms": 12.3,
                    "attempts": 1,
                },
            }
        ],
    }
    events = [
        {
            "schema_version": "1.0",
            "event_id": "event-1",
            "run_id": run_id,
            "sequence": 1,
            "timestamp": "2026-10-14T12:00:00+00:00",
            "event_type": "run.started",
            "test_id": "TP-01",
            "operation_id": None,
            "phase": "run",
            "data": {},
            "artifact_refs": [],
        },
        {
            "schema_version": "1.0",
            "event_id": "event-2",
            "run_id": run_id,
            "sequence": 2,
            "timestamp": "2026-10-14T12:00:00.100000+00:00",
            "event_type": "http.request.sent",
            "test_id": "TP-01",
            "operation_id": "crd",
            "phase": "transport",
            "data": {
                "method": "POST",
                "path": "/cds-services/shn-order-sign",
                "url": "https://example.invalid/cds-services/shn-order-sign",
                "content_type": "application/json",
                "correlation_id": "corr-full-1",
                "request_label": None,
                "authorization_header_present": True,
                "authorization_scheme": "Bearer",
                "body": {"hook": "order-sign"},
            },
            "artifact_refs": [],
        },
        {
            "schema_version": "1.0",
            "event_id": "event-3",
            "run_id": run_id,
            "sequence": 3,
            "timestamp": "2026-10-14T12:00:00.200000+00:00",
            "event_type": "http.response.received",
            "test_id": "TP-01",
            "operation_id": "crd",
            "phase": "transport",
            "data": {
                "path": "/cds-services/shn-order-sign",
                "request_label": None,
                "http_status": 200,
                "correlation_id": "corr-full-1",
                "sent_correlation_id": "corr-full-1",
                "shn_leg_id": "leg-full-1",
                "elapsed_ms": 12.3,
                "trace_url": "https://example.invalid/trace/corr-full-1",
                "attempts": 1,
                "body": {"cards": []},
            },
            "artifact_refs": [],
        },
        {
            "schema_version": "1.0",
            "event_id": "event-4",
            "run_id": run_id,
            "sequence": 4,
            "timestamp": "2026-10-14T12:00:02+00:00",
            "event_type": "run.completed",
            "test_id": "TP-01",
            "operation_id": None,
            "phase": "run",
            "data": {"result": "PASS"},
            "artifact_refs": [],
        },
    ]
    _write_json(run / "result.json", result)
    _write_json(
        run / "run.json",
        {
            "schema_version": "1.0",
            "run": result,
            "execution_context": {"execution_mode": "pytest"},
            "test_contract": {"id": "TP-01"},
            "events": events,
            "artifact_index": [],
        },
    )
    _write_jsonl(run / "events.jsonl", events)
    _write_json(
        run / "operations" / "01-crd" / "request.json",
        {"hook": "order-sign"},
    )
    _write_json(
        run / "operations" / "01-crd" / "response.json",
        {"cards": []},
    )
    _write_json(
        run / "operations" / "01-crd" / "summary.json",
        result["operations"][0],
    )
    _write_json(
        run / "operations" / "01-crd" / "transport.json",
        result["operations"][0]["transport"],
    )
    return run


def _legacy_run(root: Path) -> Path:
    run_id = "tn05-20261013T120000Z-legacy"
    run = root / run_id
    operation = {
        "operation_id": "negative",
        "operation_type": "negative",
        "expected": {"http_status": 500},
        "observed": {
            "http_status": 400,
            "error_text": "PAS bundle missing Claim.patient",
        },
        "passed": False,
        "transport": {
            "status_code": 400,
            "correlation_id": "corr-legacy-1",
            "sent_correlation_id": "corr-legacy-1",
            "leg_id": "leg-legacy-1",
            "trace_url": "https://example.invalid/trace/corr-legacy-1",
            "elapsed_ms": 8.1,
            "attempts": 1,
        },
    }
    _write_json(
        run / "result.json",
        {
            "test_id": "TN-05",
            "label": "Identifier-only Claim.patient",
            "kind": "negative",
            "run_id": run_id,
            "started_at": "2026-10-13T12:00:00+00:00",
            "passed": False,
            "manual": False,
            "operations": [operation],
        },
    )
    _write_json(
        run / "operations" / "01-negative" / "request.json",
        {"resourceType": "Bundle"},
    )
    _write_json(
        run / "operations" / "01-negative" / "response.json",
        {
            "resourceType": "OperationOutcome",
            "issue": [{"diagnostics": "PAS bundle missing Claim.patient"}],
        },
    )
    _write_json(
        run / "operations" / "01-negative" / "summary.json",
        operation,
    )
    _write_json(
        run / "operations" / "01-negative" / "transport.json",
        operation["transport"],
    )
    return run


def test_discover_runs_classifies_full_and_legacy_and_filters(tmp_path):
    _full_run(tmp_path)
    _legacy_run(tmp_path)

    runs = discover_runs(tmp_path)
    assert [run.test_id for run in runs] == ["TN-05", "TP-01"]
    assert [run.logging_level for run in runs] == [
        "legacy-artifacts",
        "full",
    ]

    since = discover_runs(tmp_path, since="2026-10-14")
    assert [run.test_id for run in since] == ["TP-01"]

    positives = discover_runs(tmp_path, kind="positive")
    assert [run.test_id for run in positives] == ["TP-01"]

    selected = discover_runs(tmp_path, test_ids=["TN-05"])
    assert [run.test_id for run in selected] == ["TN-05"]


def test_collection_contains_full_and_legacy_transactions(tmp_path):
    _full_run(tmp_path)
    _legacy_run(tmp_path)
    runs = discover_runs(tmp_path)

    manifest, transactions, events = build_collection_data(runs)

    assert manifest["summary"]["run_count"] == 2
    assert manifest["summary"]["transaction_count"] == 2
    assert manifest["summary"]["full_log_runs"] == 1
    assert manifest["summary"]["legacy_artifact_runs"] == 1
    assert manifest["summary"]["passed_runs"] == 1
    assert manifest["summary"]["failed_runs"] == 1

    by_test = {transaction["test_id"]: transaction for transaction in transactions}
    assert by_test["TP-01"]["path"] == "/cds-services/shn-order-sign"
    assert by_test["TP-01"]["http_status"] == 200
    assert by_test["TP-01"]["request_body"] == {"hook": "order-sign"}
    assert by_test["TP-01"]["response_body"] == {"cards": []}

    assert by_test["TN-05"]["logging_level"] == "legacy-artifacts"
    assert by_test["TN-05"]["path"] is None
    assert by_test["TN-05"]["http_status"] == 400
    assert by_test["TN-05"]["request_body"] == {"resourceType": "Bundle"}

    assert len(events) == 4
    assert [event["collection_sequence"] for event in events] == [1, 2, 3, 4]


def test_collection_zip_has_flat_indexes_and_original_run_evidence(tmp_path):
    full = _full_run(tmp_path)
    legacy = _legacy_run(tmp_path)
    runs = discover_runs(tmp_path)

    payload, manifest = collection_zip_bytes(runs)

    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        names = set(archive.namelist())
        assert "README.txt" in names
        assert "collection.json" in names
        assert "transactions.jsonl" in names
        assert "events.jsonl" in names
        assert "transactions.csv" in names
        assert f"runs/{full.name}/run.json" in names
        assert f"runs/{full.name}/events.jsonl" in names
        assert f"runs/{legacy.name}/result.json" in names
        assert (
            f"runs/{legacy.name}/operations/01-negative/request.json"
            in names
        )

        collection = json.loads(archive.read("collection.json"))
        assert collection["collection_id"] == manifest["collection_id"]

        transaction_lines = [
            json.loads(line)
            for line in archive.read("transactions.jsonl")
            .decode()
            .splitlines()
            if line.strip()
        ]
        assert len(transaction_lines) == 2

        rows = list(
            csv.DictReader(
                io.StringIO(archive.read("transactions.csv").decode())
            )
        )
        assert len(rows) == 2
        assert {row["test_id"] for row in rows} == {"TP-01", "TN-05"}


def test_collection_csv_carries_expected_and_observed_json(tmp_path):
    _full_run(tmp_path)
    runs = discover_runs(tmp_path)
    _manifest, transactions, _events = build_collection_data(runs)

    rows = list(csv.DictReader(io.StringIO(transactions_csv(transactions))))
    assert len(rows) == 1
    assert json.loads(rows[0]["expected_json"]) == {"http_status": 200}
    assert json.loads(rows[0]["observed_json"])["covered"] == "conditional"


def test_collection_refuses_sensitive_keys_in_legacy_artifacts(tmp_path):
    run = _legacy_run(tmp_path)
    _write_json(
        run / "operations" / "01-negative" / "request.json",
        {
            "resourceType": "Bundle",
            "client_secret": "DO-NOT-COLLECT",
        },
    )
    runs = discover_runs(tmp_path)

    with pytest.raises(ValueError, match="sensitive key"):
        build_collection_data(runs)

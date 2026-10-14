from __future__ import annotations

from typing import Any


LOG_SCHEMA_VERSION = "1.0"

EVENT_REQUIRED_FIELDS = {
    "schema_version",
    "event_id",
    "run_id",
    "sequence",
    "timestamp",
    "event_type",
    "test_id",
    "operation_id",
    "phase",
    "data",
    "artifact_refs",
}

RUN_REQUIRED_FIELDS = {
    "schema_version",
    "run",
    "execution_context",
    "test_contract",
    "events",
    "artifact_index",
}


def validate_event(event: dict[str, Any]) -> None:
    missing = EVENT_REQUIRED_FIELDS - set(event)
    if missing:
        raise ValueError(f"log event missing fields: {sorted(missing)}")
    if event["schema_version"] != LOG_SCHEMA_VERSION:
        raise ValueError(
            f"unsupported log schema version: {event['schema_version']!r}"
        )
    if not isinstance(event["sequence"], int) or event["sequence"] < 1:
        raise ValueError("event sequence must be a positive integer")
    if not isinstance(event["data"], dict):
        raise ValueError("event data must be an object")
    if not isinstance(event["artifact_refs"], list):
        raise ValueError("event artifact_refs must be an array")


def validate_run_document(document: dict[str, Any]) -> None:
    missing = RUN_REQUIRED_FIELDS - set(document)
    if missing:
        raise ValueError(f"run log missing fields: {sorted(missing)}")
    if document["schema_version"] != LOG_SCHEMA_VERSION:
        raise ValueError(
            f"unsupported log schema version: {document['schema_version']!r}"
        )
    events = document["events"]
    if not isinstance(events, list):
        raise ValueError("run events must be an array")
    for event in events:
        validate_event(event)
    sequences = [event["sequence"] for event in events]
    if sequences != list(range(1, len(events) + 1)):
        raise ValueError("event sequence is not contiguous and ordered")
    if events and events[0]["event_type"] != "run.started":
        raise ValueError("first event must be run.started")
    if events and events[-1]["event_type"] != "run.completed":
        raise ValueError("last event must be run.completed")

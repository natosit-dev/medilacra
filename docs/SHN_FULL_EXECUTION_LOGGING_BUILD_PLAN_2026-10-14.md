# SHN Full Execution Logging — Build Plan

**Date:** 2026-10-14  
**Branch:** `experiment/shn-mvp0`  
**Initial scope:** SHN Reference Suite TP/TN execution  
**Goal:** Capture the experiment before trimming it for presentation.

## Principle

The existing reference suite remains the system under test. Logging is an append-only observation layer around it.

```text
JSON test contract
       ↓
ReferenceSuiteRunner
       ↓
payload construction / mutation / transport / interpretation / evaluation
       ↓
SHN

       │
       └──────────────→ RunLogger
                           ↓
                    chronological events
                    + execution context
                    + evidence inventory
                           ↓
                    run.json
                    events.jsonl
                    export ZIP
```

## What is logged

- Run identity and execution context: test id, run id, timestamps, execution mode, Git branch/commit/dirty state, Python/platform.
- Full test contract and provenance.
- Operation start/completion and durations.
- Payload builder identity, inputs and produced payload.
- Derived values between legs, including questionnaire canonical and CommunicationRequest trace.
- Negative-test mutation name, full before/after payload and structural JSON diff.
- Safe authentication lifecycle metadata: token requested/acquired/reused, token endpoint, status, expiry metadata and credential source path.
- Outbound transaction metadata and body.
- Inbound status, latency, SHN correlation/leg ids, Warning/Link, trace URL and full response body.
- Normalized semantic interpretation.
- One event per expected-vs-observed assertion.
- Exceptions including traceback.
- Persisted evidence artifact path, size and SHA-256.

## Explicit exclusions

Never persist:

- client secret,
- bearer/access token,
- Basic credential,
- Authorization header value,
- private key,
- client assertion.

Authentication facts may be logged without credential values.

## Event envelope

Every event uses a common envelope:

```json
{
  "schema_version": "1.0",
  "event_id": "<uuid>",
  "run_id": "<run>",
  "sequence": 12,
  "timestamp": "<UTC ISO-8601>",
  "event_type": "http.response.received",
  "test_id": "TP-01",
  "operation_id": "dtr",
  "phase": "transport",
  "data": {},
  "artifact_refs": []
}
```

Sequence is authoritative for execution order.

## Export

Each persisted run gains:

```text
<run-id>/
  result.json
  run.json
  events.jsonl
  operations/
    ...
  export/
    medilacra-test-log-<run-id>.zip
```

The ZIP presents operation evidence under `artifacts/` and contains a short README.

`run.json` is the complete nested human-readable record.
`events.jsonl` is the append-order machine-readable event stream.

## UI

The Reference Suite tab gains:

- chronological log table,
- expandable raw event stream,
- **Export Full Test Log** download.

No test logic moves into Streamlit.

## CLI

Existing invocation remains valid:

```bash
python -m connectathon.shn_provider.reference_run TP-01
```

Optional export:

```bash
python -m connectathon.shn_provider.reference_run TP-01 --export
```

## Validation

Tests must establish:

- sequence is monotonic,
- `run.started` is first,
- `run.completed` is last,
- operation lifecycle events are paired,
- transport request/response events exist,
- assertions preserve expected/observed/pass,
- mutation events include structural diffs,
- artifact hashes match,
- JSONL is parseable,
- ZIP contains complete evidence,
- fake secrets/tokens/Authorization values do not occur anywhere in exported bytes.

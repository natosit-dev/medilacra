# Reality Provenance Refactor — Build History

**Version:** 0.1
**Date:** 2026-10-08 America/New_York
**Branch:** `refactor/reality-provenance`
**Baseline:** `8858cd60933ac5b42f0a78af591f1f32c3e2df4f` on `checkpoint/pre-reality-provenance-refactor-20261008`
**Status:** IMPLEMENTATION IN PROGRESS — several stages built and CI-tested, full audit closure and external conformance outstanding

## User-origin prompt log (chronological)

> "I noticed there's a synthetic address in Lowell in certain X12 messages. Where'd that come from?"

> "Do a press to find all the places you're inventing reality downstream. We'll want to fix them all at once"

> "Let's see a refactor plan"

> "Yeah, let's include legacy v2 and FHIR. I think we should also audit what's being written to duckdb to make sure all the synthetic reality is there. New fields look good. Freeze the current working code and let's see a gap analysis/build plan"

> "That's OK. If we ever do heavy lab testing we'll build a synthetic lab"

> "Ok, are you ready to build? Don't start yet"

> "Go build it."

## Decisions respected

1. All work isolated to `refactor/reality-provenance`; frozen branch remains unchanged.
2. Source facts originate before projection; X12/HL7/FHIR serializers may format, not invent.
3. Clinical and payer representations keep distinct ownership, including coverage periods.
4. Preserve existing optional lab demonstration behavior and exempt message-local lab test results from DuckDB core completeness.
5. Additive DuckDB schema only, with a verified backup guard for preexisting DB files. No live local DB was touched during remote-only development.
6. Preserve raw HL7 messages in existing `messages` table; X12 and FHIR remain separate, with a general artifact index.

## Commit and implementation chronology

### Checkpoint A — core persistence

- `storage_duckdb_entities.py`: additive migration for all **31 previously omitted scalar fields** across Patient, Encounter, Observation, Transaction; payer service assertions become persisted JSON when established.
- `reality/persistence.py`: `simulation_runs`, `simulation_cases`, `semantic_records`, `artifact_index`, stable JSON snapshots, owner checks, SHA-256 and immutable case ID collision checks.
- `hl7_demo/pipeline.py`: save core reality and independent payer/claim/authorization facts *before* output rendering; mark completed cases; use actual encounter IDs and insertion timestamps in the HL7 log.
- `reality/migration.py`: verify a one-time backup of an existing DuckDB file before additive migrations, fail when a read-only open fails; no destructive schema change.
- `scripts/audit_reality_duckdb.py`: read-only metadata/NULL-count audit CLI; does not expose raw patient records.
- `tests/test_reality_persistence.py`, `tests/test_reality_audit_migration.py`.

### Checkpoint B — faithful X12 projections

- 278: published 005010X217 service-level loop 2000F; actual requested CPT/quantity/date in `HL*5*4*SS*0`, `DTP*472`, `SV1*HC:...`. Grounded in X12's published Example 6a (https://x12.org/examples/005010x217/example-6a-request-medical-services-reservation).
- 837P: patient N3/N4 now from clinical Patient source; provider billing address, submitter identity, contact and tax ID come from a distinct, seeded synthetic site fixture captured in `ClaimSubmission.routing`; POS from Encounter.
- 835: contact generated upstream and carried in `SemanticCase.payer_contact`, with new `ClaimDecision.remittance` for explicit payment method, payee, trace and adjustment reason. Retain previously IRIS-accepted 1000A N1/N3/N4/PER segment order; **new values still need IRIS retest**.
- 271: no longer asserts a hardcoded list of ten active services just from an active plan. `BenefitPlan.active_service_types` is now the payer-owned source; service-specific EB is emitted only if populated.
- Tests deliberately vary patient/provider address, payee/payment trace/adjustment and 278 procedure/date/quantity.

### Checkpoint C — FHIR and legacy

- Direct FHIR Claims/ePA `Coverage.period` represents independent clinical and payer effective periods instead of silently dropping them. `Coverage.status=active` remains a FHIR resource lifecycle assertion, **not** a guarantee of benefit in-force.
- Legacy HL7v2→FHIR converter: admission A01 is `Encounter.in-progress`, discharge A03 is `Encounter.finished`; otherwise unknown instead of inventing completion. Observation/DiagnosticReport result status derives from OBX-11/OBR-25; ORU without OBR does not invent a final report.
- Tests: `test_legacy_fhir_reality_status.py`, new FHIR Coverage divergence assertions.

### Checkpoint D — DuckDB-only reproduction and artifact inventory

- `reality/replay.py` reconstructs nested Claims/ePA dataclasses from persisted source JSON plus original run timestamp. This generates X12 and direct FHIR with **no new Faker calls, no incoming X12 conversion, no original in-memory objects**.
- Main pipeline registers generated HL7 v2, eligibility X12/FHIR and Claims/ePA files against their case. Raw X12/FHIR are **not mislabeled** as HL7 in `messages`.
- Integration test compares replayed 837P, 835, 278 and FHIR case against original outputs. `artifact_index.payload_sha256` is per-message/payload, not necessarily an entire appended bulk file hash.

## CLI and local reviewer instructions

```bash
git fetch origin
git switch refactor/reality-provenance
git pull --ff-only

# Tests on the working branch
python -m pytest -q

# Read-only inventory of a local DB (NO migration)
python -m scripts.audit_reality_duckdb --db ./data/medilacra.duckdb --out ./output/reality_db_audit.json

# Inspect a generated case ID
python -c "import duckdb; c=duckdb.connect('data/medilacra.duckdb', read_only=True); print(c.sql('select case_id,status from simulation_cases limit 5').fetchall())"

# Regenerate a persisted case from DuckDB (no synthetic generation)
python -m reality.replay --db ./data/medilacra.duckdb \
    --case-id 'YOUR-CASE-ID' --out ./output/replayed
```

**Migration safety:** The first `init_db()` on an *existing* DuckDB creates a sibling `*.pre-reality-refactor.bak` copy. Close any other connections first. Do **not** commit or upload the data file. To avoid touching an existing database during review, set `MEDILACRA_DB_PATH` to a disposable new path or use the page's DB path selector.

## Test and verification boundary

- First refactor CI caught unsupported `SimpleNamespace` in snapshots; fixed without accepting arbitrary unknown object classes.
- CI on commit `77ec50bbf0f1a78df539cd63a50bd3c1f1b46a6d` had **7 focused tests passed, 143 full suite passed, 2 warnings**, plus a two-case CLI X12/FHIR smoke run: https://github.com/natosit-dev/medilacra/actions/runs/37867430741.
- Commits after that run include migration guard and extra audit tests; their latest CI results must be consulted independently. Do not extend the previous passing verdict beyond its exact commit.
- The old IRIS 835 schema acceptance applies to the frozen prior code only. New 837P/835/278/271 outputs require new IRIS checks; FHIR R4/PAS profile validation was **not run here**.
- The user's actual live DuckDB file is not accessible from the GitHub build environment: row-level audit still requires a local `--db` run.

## Known remaining work (not declared complete)

- Replace synthetic prior-authorization request created by copying the completed observation and offsetting date by 14 days with an **independent, explicit clinical RequestedService source event**.
- Formalize/version payer adjudication and authorization policy rather than relying on the example 80%-of-charge rule and canned reasons.
- Add per-case atomicity across existing flat entity upserts (currently separate transactions); the new immutable case snapshot is atomic, **not** the entire old write sequence.
- Finish normalizing parties, routing, orders, benefit details and monetary exactness across all active pipelines; `pipeline_duckdb.py` remains a legacy parallel writer.
- Audit HL7 v2 optional ADT demographic/vital assertions and message-level methods, FHIR payer identity attribution and lifecycle status; optional lab persists as allowed demo-only behavior.
- Run complete X12 IRIS TR3-level testing and FHIR official R4/PAS validation on changed messages.
- Conduct the **actual local DuckDB** read-only audit and reconcile existing historical records; run scale and interrupted-case recovery tests.
- Reconcile all 28 previous provenance findings and D01-D08 against evidence, with statuses, in the final completion audit.

**This document is not a final signoff.** It is an evidence-backed build history for a substantial but incomplete refactor.

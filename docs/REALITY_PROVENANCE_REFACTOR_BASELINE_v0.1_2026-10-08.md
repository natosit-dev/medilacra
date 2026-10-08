# Reality Provenance Refactor — Frozen Baseline and Recovery Record

**Version:** 0.1  
**Date:** 2026-10-08 (America/New_York)  
**Status:** Frozen code checkpoint recorded; no refactor implementation begun  
**Repository:** `natosit-dev/medilacra`  
**Frozen baseline commit:** `8858cd60933ac5b42f0a78af591f1f32c3e2df4f`  
**Frozen checkpoint branch:** `checkpoint/pre-reality-provenance-refactor-20261008`  
**New planning/implementation branch:** `refactor/reality-provenance` (branched from the same exact SHA)  
**Existing experiment branch:** `experiment/claims-epa` remains untouched by the new refactor plan  
**Last verified baseline CI:** https://github.com/natosit-dev/medilacra/actions/runs/37854630342 (successful for frozen SHA)

---

## 1. Reason for the freeze

The user found synthetic Lowell addresses inserted into X12 generation. The resulting audit revealed message builders inventing factual assertions, omitting actual service details, and generating clinical observations while serializing. The user now explicitly extends the repair to legacy HL7 v2 and legacy FHIR conversion, and requires DuckDB to preserve all materialized synthetic reality.

The freeze creates a concrete rollback point before any schema migration or serializer behavior change.

## 2. Exact user-origin scope

> "Do a press to find all the places you're inventing reality downstream. We'll want to fix them all at once"

> "Let's see a refactor plan"

> "Yeah, let's include legacy v2 and FHIR. I think we should also audit what's being written to duckdb to make sure all the synthetic reality is there. New fields look good. Freeze the current working code and let's see a gap analysis/build plan"

These are scope decisions, not post-hoc assistant interpretations: **X12 + FHIR R4 eligibility/Claims/ePA + legacy HL7 v2 and conversion + DuckDB + explicit party/service/payment/benefit/event fields**, before committing to the build.

## 3. Baseline evidence

- Source inspected on `checkpoint/pre-reality-provenance-refactor-20261008`.
- Last successful CI on the exact frozen SHA (no new pytest run initiated as part of the design freeze).
- Existing user-operated IRIS testing confirmed 270/271 parsing and, after an 835 1000A N3/N4/PER repair, IRIS schema acceptance for the updated 835.
- 837P and 278 request/response have **not** been independently confirmed in IRIS.
- External FHIR R4/PAS profile validation is not claimed.
- Existing generated message files and DuckDB **data files** have **not** been copied or inspected in this checkpoint. Git freeze covers repository code, *not a snapshot of the user's machine*, local DuckDB contents, or uncommitted changes.

## 4. Source entry points and dependencies

- Generator: `hl7_demo/pipeline.py`; optional compatibility path: `pipeline_duckdb.py`.
- Data: `hl7_demo/models.py`, `reality/models.py`, `payer/models.py`, `claims_epa/models.py`.
- Persistence: `storage_duckdb_entities.py`, `utils/db.py`, `storage_duckdb_labels.py`.
- HL7 v2 serialization: `hl7_demo/messages.py`, `hl7_demo/segments.py`, `hl7_demo/labs.py`.
- X12: `x12/eligibility_270.py`, `x12/eligibility_271.py`, `x12/generation.py`, `claims_epa/x12_projection.py`.
- FHIR: `fhir/eligibility_r4.py`, `fhir/eligibility_generation.py`, `claims_epa/fhir_projection.py`, legacy `fhir/fhir_convert_backend.py`.
- Test baselines: `tests/test_storage_duckdb_entities.py`, `tests/test_claims_epa_pipeline.py`, `tests/test_fhir_pipeline_integration.py`, `tests/test_fhir_x12_semantic_equivalence.py`, and prior X12 tests.
- Previous audit: `docs/DOWNSTREAM_REALITY_PROVENANCE_AUDIT_v0.1_2026-10-08.md`.

## 5. Recovery instructions

To inspect the unchanged frozen tree:

```bash
git fetch origin
git switch checkpoint/pre-reality-provenance-refactor-20261008
git rev-parse HEAD
# expected: 8858cd60933ac5b42f0a78af591f1f32c3e2df4f
```

For the new work, switch to `refactor/reality-provenance`; do **not** reset or overwrite the freeze branch. A branch is not mechanically immutable: the exact SHA is the source of truth for rollback. Do not force push or change this checkpoint ref.

Prior to modifying DuckDB schema or writer code, separately back up the local `MEDILACRA_DB_PATH` (default `./data/medilacra.duckdb` relative to the process working directory). The note-labeling store defaults to `data/labels.duckdb` and is separate.

## 6. Phase-zero golden fixtures still to capture

For one deterministic complete scenario capture:
- a source reality snapshot and seed/profile/input references;
- DuckDB schema/version, table counts and field null/completeness inventory;
- ADT / narrative ORU / DFT / lab ORM+ORU;
- 270/271, 837P/835, 278 request+response;
- direct FHIR eligibility and Claims/ePA Bundles, plus relevant legacy v2→FHIR outputs;
- hashes, case/exchange IDs, original X12/HL7 headers and parser results.

Golden fixtures are **future acceptance evidence**; this file does not claim they are already captured.

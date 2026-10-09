# Reality Provenance Refactor — Post-Checkpoint Addendum

**Version:** 0.2
**Date:** 2026-10-08 America/New_York
**Branch:** `refactor/reality-provenance`
**Status:** Additional implementation commits; not a full architecture signoff.
**Supersedes these statuses in the v0.1 test/audit document only:** C07, C08, H02.

## User design lineage

The user explicitly requested a single cohesive refactor, DuckDB completeness, legacy HL7 v2/FHIR coverage, a frozen working baseline, and preservation of the optional lab generator. This addendum records further implementation beyond the first 145-test checkpoint.

## C07 — Separate prospective service: FIXED IN SOURCE MODEL

- Added `RequestedService`, with an independent service-request ID, requesting provider identity, proposed date, procedure, diagnosis, quantity, status and provenance.
- `synthetic_followup_service()` explicitly constructs the **example** proposed service (CPT 99213) using named `synthetic-followup-v1` scenario policy. The historical claim still uses its original Observation/CPT (e.g. 72148 MRI).
- Caller may pass an independently authored `RequestedService` to `build_case()`; incorrect patient identity is rejected.
- AuthorizationRequest and X12 278/FHIR preauthorization consume the requested service's actual code, date and quantity. The semantic case, DuckDB records and replay preserve the independent source.
- **Remaining:** actual clinical order/medical-necessity simulations and provider-driven configuration are future extensions. CPT 99213 is a declared synthetic scenario, not evidence that an actual payer requires prior authorization for that visit.

## C08 — Synthetic payer adjudication: FIXED AS EXPLICIT VERSIONED POLICY

- Added `SyntheticAdjudicationPolicy` and named default `example-payer-flat80-v1`.
- The 80% allowed fraction, 0% patient share, CHK payment method, and paid/denied adjustment group/reason are now transparent policy attributes rather than hidden calculations or X12 serializer defaults.
- `build_case(adjudication_policy=...)` accepts an alternative payer policy; charge/allowed/patient/paid/adjusted amounts are derived and reconciled in integer cents.
- Case snapshots/replay record the policy. Regression tests vary allowance, patient share and CARC, asserting both X12 835 and FHIR ClaimResponse values.
- **Remaining:** real payer contracts, benefit terms, fee schedules and medical-necessity logic are explicitly not represented.

## H02 — Gender Harmony generation: PARTIALLY FIXED

- The main `hl7_demo/pipeline.py` path now samples a single `gender_values` set before DuckDB writes and stores it with a synthetic source label and effective time in the per-case snapshot.
- `build_adt()` accepts those pre-materialized values and timestamp. Direct legacy standalone callers still use the old fallback sampler for backward compatibility; this is explicitly outside the strict persisted pipeline contract.
- Removed two unsourced assertions from the Gender Harmony OBX projection: fabricated `Patient-reported` and `Endocrinology assessment` methods (and the invented performing organization). Missing assessment facts remain absent.
- **Remaining:** model author/method and native demographic observation status for any future durable clinical data, rather than treating synthetic demo assertions as medically authoritative.

## Remaining original limitations unchanged

- X12 278 UM review category/trading partner defaults; 270/271 routing defaults.
- Broader HL7 MSH/ORC/OBX/GT1/FT1 business-state defaults and legacy conversion statuses still requiring source evidence.
- Old flat-table entity upserts are not yet a single whole-case atomic transaction, although the new case snapshot write is atomic and immutable.
- Hidden oracle correspondence is not persistently isolated in an independent test-only namespace yet.
- Old `pipeline_duckdb.py` compatibility path remains.
- Local DuckDB row-level audit and external IRIS X12/FHIR/PAS checks have not been run in this agent's environment.

## Acceptance boundary

The earlier 145-test CI result (https://github.com/natosit-dev/medilacra/actions/runs/37867517526) pertains to commit `f7b1913320f6a4767d1e369dca33752c575e024b`. Later commits require their own CI result before being declared passing. Do not equate test success with full TR3/PAS profile conformance. Preserve the frozen checkpoint.

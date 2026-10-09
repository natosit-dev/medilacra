# Reality Provenance Refactor — CLI Test Results and Acceptance Audit

**Version:** 0.1
**Date:** 2026-10-08 America/New_York (GitHub CI log UTC 2026-10-09)
**Branch:** `refactor/reality-provenance`
**Tested SHA:** `f7b1913320f6a4767d1e369dca33752c575e024b`
**CI:** https://github.com/natosit-dev/medilacra/actions/runs/37867517526
**CI result:** SUCCESS (exact SHA above)
**Current disposition:** major implementation checkpoint passed; **overall seven-phase plan is not signed off**

## Exact CI transcript summary

```text
Core persistence and provenance:
  python -m pytest -q tests/test_reality_persistence.py \
    tests/test_storage_duckdb_entities.py tests/test_claims_epa_pipeline.py
  7 passed in 2.96s

Complete repository test suite:
  python -m pytest -q
  145 passed, 2 warnings in 6.72s

Claims/ePA CLI smoke:
  python -m claims_epa --seed 43 --count 2 \
    --at 2026-10-07T23:00:00 --out /tmp/reality-provenance-cli
  2 cases generated; 10 artifacts per case
  required 835 and ePA output files present
```

Warnings in the full suite were not promoted to failures. This log summarizes test output; do not construe it as an external X12/FHIR certification.

## Original 28-finding audit — implementation disposition

| ID | Current disposition | Evidence / remaining limitation |
|---|---|---|
| C01 | FIXED for 837P core party fields | Explicit `ClaimRouting`, source patient address, independent seeded provider site, submitter and billing EIN. External 837P validation still pending. |
| C02 | PARTIAL | Payer contact now seeded upstream as payer-owned `PayerContact` rather than a universal Lowell default; still a synthetic fixture if caller does not supply payer-directory data. |
| C03 | FIXED for 835 named fields | `RemittanceInstructions` names payee, payment method/trace and CAS reason; serializer refuses missing instructions. Policy assumptions still synthetic. |
| C04 | PARTIAL | SBR relationship/filing and CLM flags carried in routing source; source fixture still defaults to a single commercial/self/first-policy scenario. |
| C05 | FIXED IN GENERATOR / IRIS OPEN | 278 service-level 2000F HL/DTP/SV1 now conveys requested code, date and quantity, following X12 public example 6a; awaiting IRIS parser. |
| C06 | OPEN | 278 UM review category and tracking company still partially hardcoded. |
| C07 | OPEN | Future authorization service still copied from historical observation CPT and +14-day scenario offset. Needs independent RequestedService. |
| C08 | OPEN | 80% payer allowed rule and synthetic default authorization outcome need explicit versioned payer policy. |
| C09 | PARTIAL | FHIR Claim/ePA now include distinct clinical/payer Coverage periods. Separate payer Organization name/status provenance still needs review. |
| C10 | PARTIAL | Professional, normal priority, one-line/focal and resource-active scenario restrictions need explicit scenario contract and stronger profiles. |
| C11 | OPEN | Unmapped administrative sex still projects as unknown without preserving raw mapping reason. |
| C12 | ACCEPTED SYNTHETIC FIXTURE | Original demo patient location is established upstream; automated scenario-generated provider/payer sites now independently owned. |
| E01 | FIXED / IRIS RECHECK | 271 only emits per-service active EB assertions when `BenefitPlan.active_service_types` explicitly lists them. |
| E02 | OPEN | Eligibility X12 sender/receiver/requester still use hardcoded transport defaults. |
| E03 | OPEN | Eligibility FHIR self subscriber/focal/status/purpose constraints need scenario documentation/source-specific handling. |
| E04 | OPEN | FHIR eligibility requester identity default remains. |
| E05 | ACCEPTED SYNTHETIC ASSUMPTION | Payer enrollment ACTIVE originates in payer materialization, not serializer; scenario must own non-active cases. |
| H01 | DEFERRED / CONSTRAINED | Optional ADT vitals currently predicted at output time. Core pre-ADT persistence ordering explicitly accepted by user. Need clarify demo enrichment vs durable clinical source. |
| H02 | OPEN | ADT Gender Harmony values/method/time generated inside builder; should be explicit if meant to be durable/clinically asserted. |
| H03 | USER-APPROVED DEFERRAL | Optional lab generator remains message-local; dedicated synthetic lab and result persistence out of scope. |
| H04 | OPEN | HL7 ORC/OBX status and producer defaults remain source-independent. |
| H05 | OPEN | GT1 self-guarantor/employment logic needs one consistent institutional source. |
| H06 | OPEN | FT1 source-unestablished CHARGE/type/currency defaults remain. |
| H07 | OPEN | HL7 MSH sender/receiver defaults remain scenario/transport configuration work. |
| H08 | OPEN | Missing PLACES measurement emits final N/A text; absence/provenance still to clarify. |
| F01 | PARTIAL | A01/A03 encounter and OBX/OBR status correction implemented; Coverage and Claim resource statuses need lifecycle-semantic review. |
| F02 | PARTIAL | Missing OBR no longer causes final generic DiagnosticReport; fallback MessageHeader identity/time still outstanding. |
| F03 | OPEN | Legacy HL7→FHIR stable source IDs/assigning authority registry remains. |

Legend: **FIXED** means an identified local generator/representation behavior is corrected and internally tested, not certified by IRIS. **OPEN** is not omitted from scope. **PARTIAL** has a named missing acceptance item. **DEFERRED** needs explicit scope acceptance (lab only).

## DuckDB D01–D08 gap disposition

| Gap | Status | Evidence |
|---|---|---|
| D01 | USER-ACCEPTED ORDER + CORE COVERAGE | Core facts persisted before output; optional lab content may remain ephemeral. |
| D02 | PARTIAL | Immutable snapshot is one transaction; existing entity upserts still use separate delete/insert transactions, so whole-case atomicity remains open. |
| D03 | PARTIAL | `simulation_runs`, `simulation_cases`, `semantic_records`, owner fields; legacy flat entity tables still lack run/case foreign keys. |
| D04 | FIXED IN MAIN PIPELINE | `messages` now gets explicit encounter_id and ingest_ts instead of filename-derived values / NULL. |
| D05 | FIXED IN MAIN PIPELINE | Per-case artifact index for v2, eligibility X12/FHIR, Claims/ePA; content hashes are per payload rather than entire appended bulk files. |
| D06 | OPEN | Hidden oracle GroundTruthLink is not yet persisted in an isolated test namespace. |
| D07 | PARTIAL | Model fields preserved, still needs exact monetary type conversion on legacy transaction DOUBLE and missingness tracking. |
| D08 | OPEN | `pipeline_duckdb.py` remains a parallel compatibility writer. |

## Test evidence / risk inventory

**Covered by automated tests:**
- 31 original field insert/read-back with source-field aliases;
- snapshot owner mapping, immutability collision and integrity hashes;
- missing/unknown record rejection and read-only DB auditor with no row-value exposure;
- pre-migration backup copy readability;
- X12 envelope and service-level CPT/date/quantity survival;
- 837 independent patient/provider address and submitter changes;
- 835 independent payee, trace, payment method/adjustment source;
- FHIR clinical vs payer Coverage periods;
- ADT A01/A03 legacy FHIR status, preliminary/unknown results and missing-OBR behavior;
- real pipeline DB case completion, artifact catalog and exact output replay.

**Not tested / not proven:**
- a local user-provided persistent DuckDB data file or historical migration;
- automatic recovery of all flat entities after mid-case failure;
- full X12 837/835/278/271 trading-partner TR3 compliance or new IRIS acceptance;
- official FHIR R4 and Da Vinci PAS profile validation;
- preservation of every field in broader historical/experimental modules;
- large-scale replay and run uniqueness under concurrent processes.

## Next implementation checkpoint

1. Design a standalone clinical RequestedService, explicit future date and independent plan/medical-necessity context; stop extrapolating from a completed Observation.
2. Resolve remaining v2/legacy FHIR source/status/method defaults with field-provenance tests.
3. Consolidate the old write path with the new case-atomic storage service; test failure injection and historical migration.
4. Run the local read-only DB census; independently re-run IRIS/FHIR validators; attach their exact outputs.
5. Sign off original C01–F03 and D01–D08 crosswalk with no unlabeled exceptions.

**Do not merge this branch as a finished refactor based on the current CI alone.**

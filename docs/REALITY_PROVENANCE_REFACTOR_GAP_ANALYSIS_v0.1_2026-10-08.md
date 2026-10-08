# Reality Provenance Refactor — Gap Analysis

**Version:** 0.1  
**Date:** 2026-10-08 (America/New_York)  
**Branch:** `refactor/reality-provenance`  
**Frozen source commit:** `8858cd60933ac5b42f0a78af591f1f32c3e2df4f`  
**Status:** Source-code and schema/write-path audit complete; **runtime DuckDB rows not yet inspected**  
**Prior provenance audit:** [DOWNSTREAM_REALITY_PROVENANCE_AUDIT_v0.1_2026-10-08.md](DOWNSTREAM_REALITY_PROVENANCE_AUDIT_v0.1_2026-10-08.md)

---

## 1. Question being answered

Is **all materialized synthetic reality** written durably to DuckDB, with enough identity, institutional ownership, lineage and history to regenerate / inspect equivalent HL7 v2, X12 and FHIR representations later?

**Answer from code inspection: no.** Several classes of generated facts have no structured persistence; a substantial number of scalar attributes are dropped when Python dataclasses become DuckDB table rows. Clinical phenomena are generated *after* persistence in message-builder code. Not even all generated message outputs are indexed in the DB.

This is **not** an inspection of the user's actual local DuckDB file. Code proves what writer functions can store and how the main pipeline calls them; actual on-disk row counts, historical schema, corrupt data, null rates, and previous-run differences require a separate read-only runtime audit.

## 2. Existing persisted table inventory — source verified

`storage_duckdb_entities.py` defines **10 tables**:

| Table | Main-pipeline write? | Grain / baseline |
|---|---|---|
| `patients` | Yes | Patient ID, demographics and address subset; see omissions below |
| `encounters` | Yes | Encounter ID and selected visit/provider fields |
| `observations` | Yes | Encounter + observation ID; selected results/codes |
| `transactions` | Yes | Transaction ID; selected charge and provider info |
| `coverage_profiles` | Yes | Instantiated clinical coverage; core declared fields preserved |
| `payer_members` | Conditional | Payer-held identity when **any** eligibility/Claims-ePA toggle triggers payer materialization |
| `payer_enrollments` | Conditional | Payer-held enrollment status and effective dates |
| `payer_plans` | Conditional | Payer-held plan identity/name/type |
| `orders` | **No call from main `run_pipeline()`** | Table + `upsert_order()` exist, but main pipeline does not use them |
| `messages` | Yes, for HL7 v2 only | Raw ADT/ORU/DFT/optional ORM and lab ORU, path, control metadata |

The labels/coding path is a **separate** `data/labels.duckdb` database via `storage_duckdb_labels.py`, not part of the main simulation. The compatibility `pipeline_duckdb.py` uses a different, older pipeline and likewise omits `upsert_order()` and the optional payer/X12/FHIR/Claims-ePA flows. Migration must not leave this alternate entry point silently out of sync.

`storage_duckdb_entities.py` makes `upsert_order()` available; individual storage tests invoke it directly. That proves the table's API works, **not** that live generation writes orders.

## 3. Source model vs persistence projection: field-loss inventory

Compared frozen dataclass declarations in `hl7_demo/models.py` to exact `INSERT INTO` column lists in `storage_duckdb_entities.py`. Alias columns (e.g., `zip_code → zip`, `admit_datetime → admit_ts`) are **not** counted as data loss; the nested `Patient.coverage_profile` is separately persisted and is **not** itself a scalar omission.

| Source entity | Persisted | Confirmed generated scalar attributes not stored | Severity |
|---|---|---|---|
| `Patient` | ID, name, birth date, sex, race, SSN, phone, street, city/state/ZIP; `mrn` defaults to patient ID | `gender`, `ethnicity`, `marital_status`, `language`, `employer`, `email` | HIGH |
| `Encounter` | ID, patient, visit/account, class, location, admit/discharge timestamps, hospital service, ordering/attending identity, order numbers | `admit_source`, `discharge_disposition`, `attending_provider_taxonomy`, `attending_provider_specialty`, `mid_level_provider_id/name`, `referring_provider_id/name`, `place_of_service_code/description` | HIGH |
| `Observation` | Identity, CPT/ICD **codes**, procedure description, report text, sub-ID, result status/time, order numbers | `cpt_description`, `icd_description`, `diagnosis_type`, `diagnosis_rank`, `performing_provider_id/name` | HIGH |
| `Transaction` | Identity, encounter, date, amount/unit cost/units, fee schedule, plan ID, billing provider ID/name | `insurance_plan_name`, `member_id`, `group_number`, `plan_type`, `subscriber_relationship`, `authorization_number`, `billing_provider_npi`, `guarantor_name/relationship` | HIGH |
| `CoverageProfile` | Declared scalar attributes including payer, employer, plan, dates, provenance and seed | No direct scalar omission in the current `INSERT` mapping | NONE KNOWN |
| `MemberRecord`, `EnrollmentRecord`, `BenefitPlan` | All current declared scalar attributes | No direct scalar omission in current writes, **but table semantics don't include contacts/benefit details needed by new workflows** | MODEL GAP |

Across `Patient`, `Encounter`, `Observation`, `Transaction` there are **31 confirmed omitted scalar attributes** (6 + 10 + 6 + 9), independent of the larger set of entirely unmodeled events. These are code-level counts, **not observed row null counts**.

The existing schema also stores money as `DOUBLE` in `transactions` although Claims/ePA semantic adjudication already uses exact integer cents. That is an explicit type/rounding decision for the migration.

## 4. Generated reality with no first-class persistence

| Concept created or implied today | Generator / owner | Current storage | Why it matters |
|---|---|---|---|
| `PersonTruth`, `CoverageTruth`, `GroundTruthLink` | `reality/models.py`, payer materialization | No oracle/truth record persisted | Cannot reconstruct cross-institution ground truth vs local assertions for audit or semantic-loss experiments; **must never leak oracle into payer decisioning** |
| Actual parties and contact info | `claims_epa/models.py` and X12 serializers | Patient subset, but no payer/provider/submitter/payee parties or addresses as linked records | Address provenance and institutional accountability impossible to inspect |
| Request for a **future** service | `claims_epa/models.py:build_case()` | No `RequestedService` / prospective order record | Current future ePA case is derived from completed Observation plus 14 days and cannot be replayed from DB |
| Claims, service line, adjudication and adjustments | `claims_epa/models.py` / `generation.py` | No structured DB rows | DB transaction charge alone cannot reconstruct 837P, 835 or FHIR ClaimResponse |
| ePA requests, decisions and reasons | `claims_epa/models.py` | No structured DB rows | Approval/denial/pending status not queryable or durable as payer event |
| Eligibility inquiry, decision and trace | `eligibility/generation.py`, `payer/system.py` | Underlying payer records stored; exchange/decision not | Later cannot determine why a specific 271 or FHIR eligibility answer was issued |
| Benefit service assertions | Hardcoded X12 271 service types | No benefit-detail source | Cannot support the generated `EB` service claims from payer records |
| Predicted vitals, Gender Harmony assertions / methods | `hl7_demo/messages.py:build_adt()` | Embedded only in `raw_hl7`, not structured entities | Message author effectively generates unseen reality after DB persistence |
| Predicted laboratory results | `hl7_demo/messages.py:build_oru_labs()` | Embedded only in lab `raw_hl7` | Cannot query/compare source laboratory Observations; generator may change between renders |
| Routing and trading partners | HL7 MSH and X12 defaults | Only emitted fields inside output | No independent sender/receiver/facility/role provenance |
| X12/FHIR files & content hashes | `x12/`, `fhir/`, `claims_epa/generation.py` | **Filesystem only** | No DB correlation, validation status or durable manifest of representations |
| Seed, scenario profile, generator/terminology revisions | Pipeline run options | Some seed on `coverage_profiles`, main messages have run_id, no comprehensive `simulation_runs` | Cannot recreate identical institutional reality from one persisted run record |

## 5. Sequencing and consistency problems

**D01 — Persist-before-generate:** `hl7_demo/pipeline.py` upserts core entities and payer records (approx. 399–425) **before** constructing ADT/ORU/DFT/lab messages (approx. 428–461). ADT predicts vitals and chooses gender-related observations, and lab ORU predicts test results, while constructing message content. Persisted structured state therefore does **not** contain the exact facts later asserted by those messages.

**D02 — Delete+insert upserts:** entity upserts execute `DELETE WHERE key` followed by `INSERT` per table in separate short-lived connections/transactions. They preserve one current row by key but **not prior revisions, scenario history or atomicity across the whole patient/encounter/exchange**. An error partway through a case can leave a partially persisted world even if the generation call raises.

**D03 — No run FK on structured entities:** `run_id` appears on `messages`, but not `patients`, `encounters`, `observations`, `transactions`, or institutional payer tables. Source seed, scenario variant and case identity aren't first-class run-linked metadata.

**D04 — Incomplete message metadata:** `_collect_msg_row()` derives encounter ID from filename pattern rather than receiving the source encounter ID, and does not populate an `ingest_ts` field even though `append_message()` attempts to write one. For this main path the appended `messages.ingest_ts`/`dt` are therefore **NULL**, not actual ingestion timestamps. ID extraction may work for default `_VN...` filenames but is brittle for custom scenarios.

**D05 — Independent raw artifacts unindexed:** X12 270/271, 837P/835, 278 and direct FHIR eligibility/Claims/ePA outputs are intentionally kept **out of `messages.raw_hl7`** (correct). But there is no suitable general artifact registry / validation-results store; the current `Claims/ePA manifest.json` is only a filesystem artifact.

**D06 — Cross-stream consistency:** `payer/materialize.py` creates payer-held records from truth, but those records lose their oracle correspondence if it isn't persisted separately. Later materialization/overwrite could change institutional state without preserving what the user actually tested.

**D07 — Incomplete precision and null semantics:** transactions use floating amounts, whereas newer Claims/ePA uses integer cents; defaults for empty clinical/coverage data can become `active/final/finished` in adapters. A DB `NULL` or absent field must not silently become a fabricated real-world assertion.

**D08 — Dual pipeline divergence:** `pipeline_duckdb.py` and the current `hl7_demo/pipeline.py` are distinct writers; `storage_duckdb_labels.py` is another DB. A refactor that changes only one path cannot honestly claim holistic persistence.

## 6. Prior downstream-invention audit still applies

All 28 classified findings from `DOWNSTREAM_REALITY_PROVENANCE_AUDIT_v0.1_2026-10-08.md` remain in scope, including:

- 837P invented patient/provider addresses, submitter and tax identifier;
- 835 automatic payer address/contact, CHK, payee, adjustment reason;
- 278 requested CPT/service omitted while fixed classification asserted (**critical semantic loss**);
- 271 fixed service-benefit categories with no payer-owned benefit data;
- Claims/ePA FHIR Coverage always `active` and omits payer plan/period facts;
- ADT/lab builder-time stochastic clinical observations and methods;
- legacy HL7 v2→FHIR converter forcing `finished`/`final`/`active`.

Keep protocol constants separate from factual claims, and distinguish request/resource lifecycle status from actual clinical/coverage status.

## 7. Priority-ranked gap matrix

| Gap | Priority | Existing asset to reuse | Required fix | Evidence expected |
|---|---|---|---|---|
| Durable source-before-projection | P0 | `hl7_demo/pipeline.py` | Materialize all generated clinical/payer/financial facts before DuckDB and before serializers | Snapshots match DB and messages |
| Missing scalar columns | P0 | `storage_duckdb_entities.py` | Additive migration and typed upserts for 31 omitted scalar fields | Round-trip equality per declared source field |
| Missing semantic entities/events | P0 | `reality/`, `payer/`, `claims_epa/` | Thin Party/Contact, ServiceRequest, Decision/Payment, Benefit, ClinicalEvent and routing records | All generated facts are persisted, queryable and owned |
| Claims/ePA and eligibility decision storage | P0 | semantic case models | Explicit request, response and payer decision rows | Query by case/exchange ID |
| 278 requested service semantic loss | P0 | authorization model | Profile-grounded X12 278 service-level CPT and date representation | Source vs FHIR vs 278 tests and IRIS validation |
| Run linkage / reproducibility | P0 | `run_id`, deterministic generation | `simulation_runs`, `case_id`, source revision and case/hash history | Deterministic replay from DB only |
| No artifact registry | P1 | existing filesystem output/manifest | Unified `artifact_index` for HL7v2/X12/FHIR and parser results | Every emitted file has DB metadata/hash |
| Delete/insert and case atomicity | P1 | `utils/db.py` writer | Transaction per case/batch; immutable case snapshot and schema migration/rollback | Interrupted run has no published partial case |
| Incomplete messages metadata | P1 | `messages` | Source IDs + explicit timestamps, not filename derivation | Correct timestamp & encounter joins |
| No provenance assertion | P1 | existing cross-format tests | Field map: output → source owner/field or protocol rule | No orphan facts or silent field drops |
| Legacy converter state invention | P1 | `fhir/fhir_convert_backend.py` | Map or explicitly represent missing state | Admission not forced finished; lab unknown not final |
| Legacy pipeline drift | P2 | `pipeline_duckdb.py` | Delegate into main entry point or deprecate compat path | One codepath, one persistence contract |
| Field-level external validation | P2 | CI + IRIS, HL7 validator | Maintain standards-acceptance workstream | Separate parser/profile outcomes, never conflate green pytest with TR3/PAS certification |

## 8. What is known vs not yet proven

**Established from source:** table DDL, insert fields, caller ordering, absence of new entity tables and relevant write calls in main pipeline; source-level omitted data; incomplete representation inventory.

**Inferred:** the missing structured facts prevent full reproduction of all messages, even when the raw HL7 is logged; a snapshot/replay model is the appropriate architectural repair.

**Still uncertain until runtime audit:** actual schema of the user's existing DuckDB file, prior migration state, null rates, historical message accumulation, how many rows from which entry point, whether data is incomplete from previous runs, and local output path retention. These must be measured **without modifying the user's DB**.

## 9. Read-only runtime audit contract (next build step)

Against a *copy* or read-only connection to the user's chosen database:
1. enumerate schemas/tables, `information_schema.columns`, row counts and PK/null rates;
2. cross-check persisted entity IDs against generated scenario IDs and file manifests;
3. reconcile HL7 message count and payload control IDs to source encounters; report missing timestamps/invalid encounter IDs;
4. compare one deterministic in-memory case `dataclasses.asdict()` against persisted DB rows by field, tagging `aliased`, `lost`, `unmodeled`, `intentional-only-in-artifact`;
5. verify snapshot/oracle separation so payer logic never sees hidden truth;
6. write a versioned local report with no real PHI or hardcoded credentials.

**Do not treat source-code analysis as a completed row-level audit.**

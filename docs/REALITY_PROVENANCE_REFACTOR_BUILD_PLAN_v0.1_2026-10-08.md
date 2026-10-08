# MediLacra Reality Provenance Refactor — Build Plan

**Version:** 0.1  
**Date:** 2026-10-08 (America/New_York)  
**Branch:** `refactor/reality-provenance`  
**Frozen baseline:** `8858cd60933ac5b42f0a78af591f1f32c3e2df4f` on `checkpoint/pre-reality-provenance-refactor-20261008`  
**Status:** PLAN FOR REVIEW — **NO REFACTOR CODE IMPLEMENTED**  
**Related:** [Frozen Baseline](REALITY_PROVENANCE_REFACTOR_BASELINE_v0.1_2026-10-08.md), [Gap Analysis](REALITY_PROVENANCE_REFACTOR_GAP_ANALYSIS_v0.1_2026-10-08.md), [Prior Downstream Audit](DOWNSTREAM_REALITY_PROVENANCE_AUDIT_v0.1_2026-10-08.md)

---

## 1. Objective and constraints

Ensure **every materialized synthetic-world fact** (clinical, financial, payer, institutional, demographic, observation, service, decision, and provenance) is recoverable from durable storage and can be projected without invention or silent loss into **HL7 v2, X12, FHIR R4, and legacy HL7 v2→FHIR conversion**.

Maintain the established MediLacra distinction between hidden synthetic ground truth, clinical-source representations, and independent payer-local representations. Generate synthetic events **once**, then persist and project them independently. Preserve provenance across differing institutional accounts rather than forcing clinical and payer records to agree.

**Not goals:** abolishing Faker; replacing canonical A/B with an elaborate new universal ontology; rewriting the entire application; inferring absent medical necessity rules; claiming full HIPAA 5010 TR3 or PAS conformance from in-house tests; writing live PHI; using a mutable Git branch alone as a hard immutable tag.

## 2. Raw prompt history and decision log

User-origin prompts, in order:

> "I noticed there's a synthetic address in Lowell in certain X12 messages. Where'd that come from?"

> "Do a press to find all the places you're inventing reality downstream. We'll want to fix them all at once"

> "Let's see a refactor plan"

> "Yeah, let's include legacy v2 and FHIR. I think we should also audit what's being written to duckdb to make sure all the synthetic reality is there. New fields look good. Freeze the current working code and let's see a gap analysis/build plan"

Confirmed decisions:
1. Keep one cohesive refactor with phased, individually testable commits.
2. Scope explicitly includes **HL7 v2 builders, legacy v2→FHIR converter, all active X12 and direct FHIR projections, and DuckDB**.
3. Add minimal typed `Party/Contact`, `RequestedService`, `Adjudication/Payment`, `BenefitDetails`, `ClinicalEvent`, and `TransportProfile` facts while reusing existing `Patient`, `Encounter`, `Observation`, `Transaction`, `CoverageProfile`, payer and ground-truth families.
4. Preserve generated historical cases and keep a known-good code checkpoint.
5. Document any intentional protocol constant separately from domain/business data.

## 3. Data ownership and persistence architecture

```text
Scenario inputs (seed, source-version, profile, domain decisions)
                   |
             [SYNTHETIC ORACLE]
             PersonTruth / CoverageTruth / GroundTruthLink
                   |         (test-only, never passed to payer matcher)
          +--------+--------+
          |                 |
   Clinical materialization   Payer materialization
  Patient, Encounter, Order,   Member, Enrollment, Benefit,
  Observation, Charge, Party   Claim/PA decision, Remittance
          |                 |
          +--------+--------+
                   |
          Explicit semantic case / events
                   |
       [persist FULL case + run provenance]
                   |
          [reload same facts from DB]
                   |
       +-----------+------------+-------------+
       |                        |             |
    HL7 v2                    X12 270/271   Direct FHIR R4
    ADT/ORU/DFT/ORM            837P/835      Elig./Claims/PAS
                              278 req/resp
       +------------+-----------+-------------+
                    |
            artifact index + hashes
                    |
         external IRIS/FHIR validation results

   Legacy HL7 v2→FHIR converter:
   consume SOURCE-EVIDENCED HL7 v2 status/fields only.
   It may emit a limitation/error, not invent source facts.
```

**Ownership / source-of-truth rule:** typed institutional event/entity records are authoritative for queries and rendering. A read-only **immutable per-case snapshot** is captured as a derived audit record from the same materialization, with a hash and schema version; it is not a separately edited source of truth. Oracle correspondence stays isolated from operational payer evaluation, in a separate test-only store/namespace with explicit interface boundaries.

An exact snapshot **must include the values actually materialized**, not only a seed that could produce different data after generator upgrades.

## 4. Minimal schema plan — additive, not destructive

**Keep and extend** the existing 10 tables; do not drop/rename them in one migration.

| Table/object family | Planned storage | Grain / requirement |
|---|---|---|
| `simulation_runs` | NEW | One run: UUID/id, seed, timestamp, scenario/profile version, source commit, generator version, data/reference-source version, options, status |
| `simulation_cases` | NEW | One case: run ID, case ID, institution IDs, patient/encounter keys, serialized immutable snapshot, schema version, checksum, committed status |
| `patients`, `encounters`, `observations`, `transactions` | EXTEND | Preserve **all** existing scalar model fields; add run/case lineage where appropriate; track ownership and provenance |
| `coverage_profiles`, `payer_members`, `payer_enrollments`, `payer_plans` | EXTEND | Preserve institution-owned state; explicit validity/coverage/benefit facts; link run/case without conflating patient and payer IDs |
| `orders` / `service_requests` | EXISTING + NEW | Actual order/proposed service identity, requester, requested date, CPT/ICD, quantity, status, effective time; populate in main pipeline |
| `organizations`, `parties`, `party_contacts`, `party_roles` | NEW thin structures (can consolidate if appropriate) | Separate patient, provider, submitter, payer, payee, guarantor, facility; address/name/contact/EIN/NPI as sourced |
| `clinical_events` (or extend `observations` with event grain) | NEW thin event store | Vitals, labs, gender/sexuality-related assertions where explicitly generated, authorship, method, status, occurrence/effective time; no render-time fabrication |
| `benefit_assertions` | NEW | Payer-owned service/category, status/effective period, source plan, decision provenance |
| `eligibility_exchanges` | NEW | Original inquiry + payer decision + request/response IDs and timestamps |
| `claims`, `claim_lines`, `claim_decisions`, `adjustments` | NEW | Clinical submission vs payer adjudication separately, charge/allowed/paid/patient amounts in **integer cents / DECIMAL**, reason codes |
| `authorization_requests`, `authorization_decisions` | NEW | Prospective service identity vs payer decision, state (approved/pended/denied), code, date, reasons, authority |
| `remittances`, `payments` | NEW thin | Payee, method, trace, payment timestamp, adjustment reason/source; don't assume provider=payee |
| `transport_profiles` | NEW | Message sender/receiver/trading-partner roles/contacts and protocol configuration |
| `artifact_index` / `validation_results` | NEW | Run/case ID, representation, format/version, writer version, path/object URI, SHA-256, outcome, external parser/profile evidence |
| Oracle/test-only truth store | SEPARATE | Retain PersonTruth/CoverageTruth/GroundTruthLink for synthetic audit with explicit non-access from payer matching/normal serializers |
| `messages` | EXTEND or bridge to artifact_index | Keep old HL7 raw-body semantics, correct source encounter id and timestamps, add run/case join; **do not insert X12/FHIR as HL7 v2** |

Use a migration manifest/version table. Monetary migration must be reversible/tested before changing type semantics. Protect existing rows from accidental destructive rewrites.

**Explicit design checkpoint:** assess whether separate `organizations`/`parties` tables truly improve modeling vs thin dataclasses linked to one organization table; do not duplicate names/addresses in six independently maintained places. Similarly prefer a common clinical event representation to a second inconsistent observation table.

## 5. Work packages and commit checkpoints

### Phase 0 — capture baseline, runtime DuckDB inventory, provenance fixture (NO schema changes)

- Record baseline SHA/CI/working IRIS parser evidence and a deterministic complete 1-case artifact set.
- Implement a **read-only DuckDB audit CLI**: table and column introspection, row/NULL counts, inferred key relationships, artifact-to-case comparisons and field-loss classification.
- Capture the user's real `MEDILACRA_DB_PATH` **only locally and only on a read-only handle or a copy**; do not upload data or guess its path.
- Compare one generated `dataclasses.asdict()` snapshot to columns persisted by `run_pipeline()`.
- Establish minimum golden fixtures for 270/271, 835 (IRIS already accepted), 837P, 278 request/response, ADT/ORU/DFT/ORM+lab ORU, direct FHIR and legacy conversion.
- Backup local DuckDB file before migrations; use an isolated test DB by default.

**Gate G0:** baseline artifacts, existing schema report, and exact known-good frozen SHA documented. Old code untouched.

### Phase 1 — source facts, owner fields, and explicit scenario policy

- Add or extend thin typed models: `Party/Contact`, `RequestedService`, `Adjudication/Payment`, `BenefitDetails`, `ClinicalEvent`, `TransportProfile`.
- Explicitly model clinical event/order status and modality, source clinical results, payer-local organization/contact, separate payee/submitter/provider, payment method/adjustment, benefit-by-service, and the future service needed by ePA.
- Version explicitly synthetic payer adjudication/authorization policies (e.g. existing 80% example) rather than treating them as universal payer facts.
- Derive payer identity from payer-local records; maintain two accounts of the same synthetic person with separate owner IDs.
- Do not derive future ServiceRequest by copying an already completed Observation and appending 14 days as serializer behavior.

**Gate G1:** one complete synthetic case is constructible, self-consistent, and serializable as pure source data **before any adapter**. Institutional divergence survives.

### Phase 2 — DuckDB completeness, migrations, case-atomic persistence

- Write additive migrations for all 31 omitted existing scalar attributes, the missing semantic event/decision families and provenance fields; preserve old tables and historical rows.
- Persist **every** source fact and completed semantic exchange before rendering any messages.
- Use per-case transaction boundaries; on failure do not publish partial case as committed. Maintain a case status and artifact lifecycle.
- Store the immutable derived case snapshot/hash alongside normalized typed records; implement read-back comparison.
- Keep oracle outside normal clinical/payer adapter access; optional separate test-only file if oracle retention is requested.
- Deprecate `pipeline_duckdb.py` or make it delegate to the same canonical persistence service.
- Correct missing `ingest_ts` and filename-based `encounter_id` in `messages`.
- Add full model-to-table field mappings and schema-version tests; separate `null/unknown/not collected` when clinically or semantically relevant.

**Gate G2:** `reality_in == load_from_duckdb(case_id)` (after defined alias/precision normalization) for **every** materialized field. Forced failure rolls back incomplete case. Read-back works without Faker/random or source CSV.

### Phase 3 — relocate generation from HL7 v2 and legacy conversion

- Move ADT synthetic vitals, Gender Harmony facts/methods, and laboratory stochastic values upstream into `ClinicalEvent`/Observation facts, with seed/run/provenance.
- Make `build_adt`, `build_orm_labs`, `build_oru_labs` and segment builders pure projections from completed facts; preserve ADT/ORU/DFT structures and currently accepted field order.
- Remove fixed producer, guarantor, order result/status, SDOH unknown-as-value and business-meaning defaults unless scenario explicitly supplies them.
- Refactor legacy `fhir/fhir_convert_backend.py` to retain source statuses and times and use explicitly mapped unknowns. No admission-to-finished or missing-OBR-to-final-report inventions.
- Write tests for source statuses: active/inactive/pending, final/preliminary, in-progress/finished where standards permit.

**Gate G3:** calling a serializer twice on a persisted case creates no new clinical fact or source-side database changes. No builder imports Faker/predictors or consumes wall-clock time for domain events.

### Phase 4 — refactor X12 and direct FHIR serializers

- X12 837P: render explicit patient/provider/submitter addresses, payer routing/identities, subscriber/POS/filing/assignment facts.
- X12 835: preserve **already IRIS-accepted** N1 PR → N3 → N4 → PER → N1 PE; source address/contact, payee, method, payment trace and CAS reason from payer records.
- X12 278: serialize the actual requested CPT/proposed date/service and decision from `RequestedService`; validate precise service-level qualifiers/loops against IRIS/licensed TR3; no guessing segments.
- X12 270/271: use declared trading-partner routing and only payer-established per-service benefit assertions.
- Direct FHIR Claims/ePA/Eligibility: reuse `fhir/eligibility_r4.py` and preserve institution-owned Coverage period/plan/status; correct claim/payment semantics with separate remittance where needed.
- Keep protocol-defined constants, message-specific controls, code-system URIs, IDs and legal FHIR defaults where they **do not invent business meaning**.
- No X12→FHIR derivation for direct-sibling generation; legacy v2→FHIR converter remains an intentionally distinct conversion path with evidence-preservation rules.

**Gate G4:** each X12, HL7 v2 and FHIR field maps to an explicit source path/derivation/protocol constant; no source CPT/date/payment/benefit/status loss. The 278 CPT/date check is mandatory.

### Phase 5 — robust provenance/replay quality gates

- Build source-field mapping ledger: `output format/field → semantic concept → owner/source instance → transform rule → case/run ID`.
- Round-trip tests for all 31 omitted scalar attributes and all new typed event families.
- Institutional divergence: change patient, payer, billing provider, submitter and payee contact details independently; verify all relevant outputs change only in appropriate places.
- Missing-data tests: required data fails with precise field/loop/resource error; optional unknown remains explicit/omitted, not silently replaced with `LOWELL`, `ACTIVE`, `FINAL`, `CHECK`, or another default.
- Payer policy tests: denial/approved/pended states, coverage dates, financial reconciliation, benefit-by-service, explicit trace/method.
- **Persistence replay**: in process A generate + persist case; in fresh process B reload from DuckDB and generate all formats with synthetic generation disabled, then compare normalized semantic contents and hashes (transport clocks/control numbers handled as explicit inputs).
- Uniqueness/control census, NULL-rate and source completeness report.
- Enforce static guardrails against hardcoded addresses, pseudo-tax IDs, `random`/`Faker` or `predict_*` in renderers, and business-fact defaults.

**Gate G5:** pristine DB + replay passes; parity is *truth ↔ DuckDB ↔ each representation*, not merely X12 ↔ FHIR equality.

### Phase 6 — external validation, migration audit, handoff

- CLI `python -m pytest -q` focused + full suite; run larger multi-case census and a failure-injection case; capture exact counts, runtime, warnings and failures.
- Re-run all X12 messages in IRIS HIPAA 5010 parser; record verified/failed/unrun separately for each variant.
- Validate FHIR R4 using official HL7 validator; apply version-pinned PAS profiles to ePA; preserve operation outcomes.
- Confirm clinical event/status fidelity for HL7 v2 and legacy FHIR path with representative scenario fixtures.
- Re-audit each of the prior 28 findings as **fixed/justified/deferred**, plus each new DuckDB finding D01–D08; record direct source evidence and any external acceptance blockers.
- Version `docs/REALITY_PROVENANCE_REFACTOR_BUILD_HISTORY_*.md`, `...TEST_RESULTS_*.md`, `...AUDIT_*.md`; update README architecture and handoff CLI.
- Do not merge into base/main without review; keep the checkpoint usable.

**Gate G6:** all required internal correctness conditions pass, every exception is documented, and external standards statuses accurately say what validators established.

## 6. Data contract & field-level acceptance

For each materialized source fact, classify as:
- **S** — institution-owned source value;
- **E** — explicitly generated scenario fact;
- **D** — transparent, versioned derivation;
- **P** — protocol-defined constant;
- **U** — explicitly unknown or missing;
- **O** — output omission with reason and declared optionality.

No unclassified semantic field is permitted in a committed case or outgoing message. Persist per-case provenance where practical, and retain the transformation registry as versioned code rather than repeating it inside every row.

**Example (not schema legislation):**

```text
case_001 / party(PAYER-1) / contact_7
    address.city = WORCESTER
    owner = payer
    provenance = explicit_synthetic_party_fixture

X12 835 / Loop 1000A / N4-01
    value = WORCESTER
    source = party(PAYER-1).contact_7.address.city
    transformation = upper/escaped X12 AN
    scenario = case_001

FHIR ClaimResponse / insurer
    references organization(PAYER-1)
    no new invented geographic fact
```

The exact X12 loop/required-field mapping follows the appropriate implementation guide, not inferred generic X12 grammar.

## 7. Acceptance matrix

| Invariant | Test | Passing evidence |
|---|---|---|
| Current regression preserved | baseline frozen SHA + full pytest suite | No baseline test regression without explicit migration |
| Complete structured reality | declared model/typed table field diff | No dropped scalar or event facts, all 31 omissions covered |
| Durable and retrievable | case persisted and loaded in new process | Semantically identical snapshot/version/hash |
| Institutional independence | conflicting clinical/payer records | Both survive and render from correct owner |
| Serializer purity | instrument/random/time guards | No source facts created after persistence |
| Correct service semantics | vary prospective CPT/date | X12 278 and FHIR ePA both convey the requested service |
| Clinical statuses preserved | vary active/preliminary/final etc. | HL7 v2 and legacy FHIR use actual source statuses |
| Financial fidelity | vary payee/method/adjustment/amount | 835/FHIR retain payer decisions, cents reconcile |
| Missingness honesty | explicit null/unknown cases | No fictitious addresses, phones or benefits |
| Case atomicity | induced failure between writes | No incomplete case marked committed |
| Artifact provenance | file index + SHA256 + case/run IDs | Every written HL7v2/X12/FHIR file traceable |
| External validation | IRIS and FHIR validator runs | Status captured per artifact; claims limited to actual evidence |
| Reviewable handoff | build/test/audit versioned docs | Audit crosswalk and reproducible CLI |

## 8. Open technical decisions at implementation time

1. **Typed tables vs event JSON:** choose the smallest queryable relational core plus immutable snapshots; avoid writing two independently editable truths.
2. **Oracle retention:** store separately from operational clinical/payer DB; test-only path and explicit access barrier. Decide whether snapshots include hidden ground truth or only institutional materializations.
3. **Migrating local DuckDB:** additive forward migration with backup and explicit restore procedure, or new versioned database path; never mutate a user's unbacked-up file.
4. **Legacy compatibility:** whether to turn `pipeline_duckdb.run_and_persist()` into a thin delegating wrapper or mark it deprecated with a compatibility error.
5. **FHIR and X12 conformity:** choose TR3/PAS package versions and acceptance tooling; no silent promotion from syntactic parse to certification.
6. **Missing required source facts:** prefer explicit schema rejection and a scenario-fix message over fabricated city, payer identity, clinical result, reason code, or payment method.

## 9. Immediate next steps after approval

1. Inspect the frozen baseline source and generate golden fixtures from the frozen SHA into a disposable output folder.
2. Run the **read-only** DuckDB inventory; capture schema, row counts and mapping gaps; avoid modifying the user's live DB.
3. Define the minimal new typed models and the `simulation_cases`/run provenance contract.
4. Implement first additive migration and a persisted-case round trip, **before touching any message serializer**.
5. Then advance through phases and gates, documenting the build and test results as in previous MediLacra branches.

**Current disposition: design only.** This commit must not be mistaken for tested or completed implementation. The prior running generator remains unchanged and recoverable by frozen SHA.

# Claims + ePA Dual-Representation MVP — Build Plan and Gap Analysis

**Version:** 0.1  
**Date:** 2026-10-07 (America/New_York)  
**Branch:** `experiment/claims-epa`  
**Base:** `experiment/employer-coverage`  
**Status:** Implemented / CLI regression tested; external TR3/PAS conformance pending

---

## 1. Purpose

Extend the *existing* MediLacra dual-projection architecture to the two remaining message groups requested for SHN: **Claims** and **electronic Prior Authorization (ePA)**. Produce **both** X12 and FHIR directly from shared synthetic semantic exchanges, preserving independent clinical and payer institutional authorship. Avoid a new generalized ontology, converting X12 into FHIR, or putting message grammar inside `hl7_demo/pipeline.py`.

## 2. Conversation / Raw Prompt History

The following are user-origin signals, retained in chronological order. Assistant findings are not represented as user prompts.

> "Gonna give you a test of agency. What are the 2 x12 message groups left to do?"

> "Claims and EPA"

> "What are the message types in x12 and FHIR?"

> "We want both. Go look at how we did 270/271"

> "I'm going to bed. Create that branch. Document our conversation. Do a gap analysis. Create a build plan, add it to docs. Same format as previous builds. Build it. Pytest CLI. Document build and testing results. Audit from build plan. I'll review in the morning"

**Decision lineage:** scope is Claims and ePA, **both wire representations**, branch from the existing eligibility work, reuse before invention, retain a dated plan/history/test/audit trail, and deliver implementation for review without merging.

## 3. Archaeology / Existing Work

Verified in `experiment/employer-coverage`:

- `reality/models.py` has `PersonTruth`, `CoverageTruth`, and oracle-only `GroundTruthLink`.
- `payer/models.py`, `payer/materialize.py`, `payer/system.py` separate member/enrollment/plan and payer adjudication from clinical records.
- `eligibility/generation.py` creates semantic `EligibilityInquiry`, shared `EligibilityExchangeIdentity`, and run-scoped identity.
- `x12/envelope.py` provides reusable ISA/GS/ST/SE/GE/IEA wrapping with configurable functional ID and TR3 version.
- `x12/generation.py` projects semantic inquiry/response into 270/271, without deciding eligibility in a serializer.
- `fhir/eligibility_generation.py` and `fhir/eligibility_r4.py` independently create FHIR R4 4.0.1 bundles, not X12 translations.
- `hl7_demo/pipeline.py` has independently selectable `include_x12` and `include_fhir_eligibility`.
- Tests include `test_fhir_x12_semantic_equivalence.py` and pipeline/scale tests.
- Recorded eligibility testing: 113 full-suite passed, 25 dual-representation exchanges, 0 X12 control collisions, and IRIS parsing of X12 270/271. External FHIR IRIS validation was outstanding at that checkpoint.

Reference designs: `docs/X12_SCALED_PIPELINE_BUILD_PLAN_v0.1_2026-10-07.md`, `docs/FHIR_R4_ELIGIBILITY_PROJECTION_BUILD_PLAN_v0.1_2026-10-07.md`.

## 4. Gap Analysis

| Concern | Existing capability | Needed in this branch |
|---|---|---|
| Core clinical data | Patient, Encounter, Transaction, CoverageProfile | Explicit financial service/diagnosis and requested authorization facts |
| Payer state | Member, Enrollment, BenefitPlan, eligibility adjudicator | Limited claim/payment outcome and authorization outcome, both modeled separately from serializer |
| Semantic exchange | EligibilityInquiry/Response | ClaimSubmission/ClaimDecision; AuthorizationRequest/AuthorizationDecision |
| Shared identity | EligibilityExchangeIdentity | One transport-neutral identity per claims/ePA exchange, independent X12 control values |
| X12 | 270/271 writer, envelope/parser | 837P / 835 test fixtures and 278 request/response; specialized ST/SE, GS functional IDs, and TR3s |
| FHIR | Eligibility R4 4.0.1 projection | Separate `Claim(use=claim)`, `ClaimResponse(use=claim)`; `Claim(use=preauthorization)`, `ClaimResponse(use=preauthorization)` |
| Institutional fidelity | Clinical vs payer patient/coverage | Payer decides from explicit simulated payer-side status, not the submitted X12 |
| Workflow | Scaled primary pipeline & CLI | Optional synthetic generation controls and independent outputs for new workflows |
| Verification | Pytest; semantic parity; IRIS X12 | Case identity, amount/state parity, controls, full artifacts, CLI pytest, manual IRIS validation backlog |
| Artifacts | Dated X12/FHIR files, DuckDB primitives | Versioned scenario files; no raw representation persistence into `messages.raw_hl7` |

## 5. Standards Target and Honest Boundary

- Claims: 005010X222A1 **837 Professional** claim; 005010X221A1 **835** payment/advice as a minimal synthetic adjudicated/payment example. FHIR R4 4.0.1 `Claim` + `ClaimResponse` (not an assertion that X12 835 equals ClaimResponse).
- ePA: 005010X217 **278** review request/response; FHIR R4 `Claim` and `ClaimResponse` with `use=preauthorization`, informed by Da Vinci PAS.
- Reference materials: https://x12.org/examples/005010x217 ; https://x12.org/examples/005010x221 ; https://www.hl7.org/fhir/R4/claim.html ; https://www.hl7.org/fhir/R4/claimresponse.html ; https://hl7.org/fhir/us/davinci-pas/en/specification.html
- **Explicit limitation:** an initial generator can demonstrate semantic, envelope, and reference consistency. It cannot assert complete TR3/PAS profile conformance without licensed IG access, validator and external interoperability checks. Label such artifacts **synthetic / test-only**.
- The ePA synthetic authorization response MUST support at least approved, denied, and pended to avoid reproducing eligibility's ACTIVE-only limitation.
- Use no real PHI or live payer transmission.

## 6. Minimum Data Grain

`ClaimSubmission`: claim ID, patient/member, payer, provider, encounter, service date, one or more service lines (procedure, units, charge), diagnosis code, submission timestamp.

`ClaimDecision`: submitted claim ID, payer-authored disposition, charge total, allowed total, paid total, patient responsibility and adjustment; amounts must reconcile.

`AuthorizationRequest`: authorization request ID, member/payer/provider, proposed service, quantity, requested date, diagnosis, available clinical fact.

`AuthorizationDecision`: request ID, payer-authored status (approved/pended/denied), authorization number only if approved, optional reason.

For first MVP: one professional service line, subscriber = patient, single primary coverage, no COB, one claim payment, no dependents, no partial line approval. The actual field values come from existing synthetic `Patient`, `CoverageProfile`, `Encounter`, and `Transaction` where available. Explicit test defaults (e.g., CPT/ICD) may be supplied only as declared scenario parameters, never invented silently in serialization.

## 7. Target Architecture

```text
Synthetic clinical + payer realities
          |
          +--> ClaimSubmission ------------> ClaimDecision (simulated payer)
          |         |                            |
          |         +-- X12 837P                 +-- X12 835
          |         +-- FHIR Claim               +-- FHIR ClaimResponse
          |
          +--> AuthorizationRequest -------> AuthorizationDecision (simulated payer)
                    |                            |
                    +-- X12 278 request           +-- X12 278 response
                    +-- FHIR Claim (PA)           +-- FHIR ClaimResponse (PA)

one shared exchange ID each; representations are siblings, not converters.
```

Reusable X12 envelope from `x12/envelope.py`; new semantic and serializer modules keep the same dependency direction as eligibility. FHIR self-contained bundles use clinical-side references on submissions; payer response reflects decision separately.

## 8. Implementation Stages and Acceptance

1. **Checkpoint** branch + this plan and gap inventory before code. Evidence: branch and commit.
2. **Semantic model** explicit immutable dataclasses, coherent fixture builder, independent deterministic decision rules; negative validation for invalid amounts/states.
3. **X12 serializers** 837P, 835, 278 request/response, correct declared transaction IDs and envelope functional/version settings, deterministic control allocation; structurally parseable ISA..IEA and ST..SE counts.
4. **FHIR R4 serializers** `Claim`/`ClaimResponse` per workflow, deterministic resource IDs, resolved bundle references, distinguish claim vs preauthorization.
5. **Orchestration/CLI** one API renders both siblings from one model; optional output controls, timestamped per-case artifacts and machine-readable manifest.
6. **Tests** CLI `pytest -q`; include amount/state parity, shared identity, 278 decision state, stable IDs, independent projections, CLI generation, envelope consistency, backwards eligibility regression where executable.
7. **Build history and audit** date/commit, files, commands and exact results, satisfied/deferred/failed plan requirements, external validation follow-ups.

## 9. Explicit Non-Goals

No FHIR R5, no institutional/dental 837, no bulk transaction batching into a shared GS envelope, no real claim pricing engine, no complex claim adjustments/secondary coverage, no 275 attachments, no 277CA acknowledgments, no PAS production compliance claim, no SHN deployment, no PHI, no IRIS endpoint reconfiguration.

## 10. Definition of Done

- [x] New branch from `experiment/employer-coverage`.
- [x] Prompt history, gap analysis and plan committed **before** implementation.
- [x] Semantic requests/responses separate from X12/FHIR rendering.
- [x] Claims X12 837P + 835 and FHIR Claim/ClaimResponse examples.
- [x] ePA X12 278 request/response and FHIR Claim/ClaimResponse examples.
- [x] Same exchange identity and same clinical/payer facts across representations.
- [x] Reuses existing envelope and clinical/coverage data models where practical.
- [x] Executable CLI, dated outputs, test-only warnings.
- [x] Pytest CLI results recorded; no fabricated test outcomes.
- [x] Audited against all rows above; explicit deferred external validation.
- [x] Branch left unmerged for human review.

## 11. Implementation Outcome (post-build annotation)

The original versioned design was committed **before** implementation in `1c3a12e`. Subsequent code and corrective commits are recorded in [Build History](CLAIMS_EPA_MVP_BUILD_HISTORY_v0.1_2026-10-07.md). The plan-to-code crosswalk, exact pytest CLI results and unresolved external acceptance requirements are recorded in [Test Results and Audit](CLAIMS_EPA_MVP_TEST_RESULTS_AND_AUDIT_v0.1_2026-10-07.md).

Final **code-bearing** test head: `0097fc1287e3d23673c086878fc18c6c066a8e46`. Successful CI: https://github.com/natosit-dev/medilacra/actions/runs/37722418933. Results: 15 focused pass; 130 full-suite pass (2 preexisting model-version warnings); five CLI cases, 10 output artifacts per case. The code includes audit fixes for independent payer member authorship and separate clinical-claim/prospective-authorization dates.

**Acceptance boundary:** all scoped MVP build tasks are complete. X12 837P/835/278 licensed-guide conformance, Da Vinci PAS profile validation, production traffic, live SHN integration and external IRIS ingestion **remain unverified**, not implicitly checked off.

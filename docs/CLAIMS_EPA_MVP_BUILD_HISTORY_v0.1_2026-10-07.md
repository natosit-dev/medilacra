# Claims + ePA Dual-Representation MVP — Build History

**Version:** 0.1  
**Date:** 2026-10-07 (America/New_York)  
**Branch:** `experiment/claims-epa`  
**Base:** `experiment/employer-coverage`  
**Design:** [CLAIMS_EPA_MVP_BUILD_PLAN_v0.1_2026-10-07.md](CLAIMS_EPA_MVP_BUILD_PLAN_v0.1_2026-10-07.md)  
**Audit/results:** [CLAIMS_EPA_MVP_TEST_RESULTS_AND_AUDIT_v0.1_2026-10-07.md](CLAIMS_EPA_MVP_TEST_RESULTS_AND_AUDIT_v0.1_2026-10-07.md)  
**Scope:** Synthetic, test-only; no licensed-IG certification, no live SHN/IRIS submission.

---

## 1. User-origin Prompt History

Preserved verbatim and in order in the design checkpoint, Section 2. Central requirements:

> "Claims and EPA"

> "We want both. Go look at how we did 270/271"

> "I'm going to bed. Create that branch. Document our conversation. Do a gap analysis. Create a build plan, add it to docs. Same format as previous builds. Build it. Pytest CLI. Document build and testing results. Audit from build plan. I'll review in the morning"

The user's requirement is **two institutional workflows in two representations each**, with durable history and reviewable verification, not an X12→FHIR converter.

## 2. First checkpoint, before coding

1. Created `experiment/claims-epa` directly from `experiment/employer-coverage`; no default-branch changes.
2. Committed `docs/CLAIMS_EPA_MVP_BUILD_PLAN_v0.1_2026-10-07.md` (initial checkpoint `1c3a12e`) before writing implementation.
3. Read prior branch's semantic/eligibility/X12/FHIR generator, payer materialization, models, pipeline, UI, tests and validation records.
4. Checked public X12 837P, 835, 278 examples and HL7 R4/PAS reference docs; chose a modest test fixture with explicit non-goals.

## 3. Implementation log

### A. Semantic model

Added `claims_epa/models.py`:

- immutable `ServiceLine`, `ClaimSubmission`, `ClaimDecision`, `AuthorizationRequest`, `AuthorizationDecision`, `PayerSubject`, `SemanticCase`;
- integer-cent money and exact claim decision reconciliation;
- shared run/case identities;
- stable source linkage across Patient, CoverageProfile, Encounter, Transaction and Observation;
- payer-local membership/enrollment eligibility checks (not GroundTruthLink);
- explicit test policy (80% allowance for paid claim) and explicit authorization scenarios (approved, pended, denied).

**Important design note:** the 80% amount is a declared synthetic test schedule, *not* a payer-negotiated fee or a real eligibility/medical-necessity rule.

### B. X12 projection

Added `claims_epa/x12_projection.py`, reusing **`x12.envelope.wrap_interchange()`** and **`x12.parser.tokenize_x12()`**, not creating a second envelope implementation:

- `build_837p`: professional one-line claim, `GS01=HC`, `005010X222A1`;
- `build_835`: payment/remittance response, `GS01=HP`, `005010X221A1`;
- `build_278`: request and response, `GS01=HI`, `005010X217`, `HCR=A1/A3/A4` depending on outcome;
- deterministic independent ISA/GS/ST controls for each artifact;
- lightweight interchange, group and ST/SE envelope checks.

Corrected the field renderer after the initial implementation to preserve empty X12 elements and allow valid colon-separated composites (`HC:...`, `11:B:1`) without accepting X12 element and segment separator injection.

### C. FHIR R4 projection

Added `claims_epa/fhir_projection.py`:

- direct R4 4.0.1 `Claim` / `ClaimResponse` for both `use=claim` and `use=preauthorization`;
- distinct clinical request Patient/Coverage versus payer response Patient/Coverage, matching the prior eligibility approach;
- deterministic resource identity, clinical diagnosis/procedure and claim amount;
- response adjudication/payment amount, approved reference, pended `queued` response;
- request/response self-contained collection Bundles, with referenced resources and a local-reference validator.

FHIR here is a **resource-level baseline**. It is not labelled PAS-conformant, does not set a PAS profile claim, and is not yet a Da Vinci `Claim/$submit` integration.

### D. Orchestration and CLI

Added `claims_epa/generation.py` and `claims_epa/__main__.py`:

- scenario composition uses **existing MediLacra `Patient`, `CoverageProfile`, `Encounter`, `Transaction`, `Observation` dataclasses** and the existing payer materializer;
- one semantic case materialized once; four X12 and four FHIR representations projected from it, no X12-to-FHIR conversion;
- timestamped case folders; 4 `.x12` files, 4 `.fhir.json` Bundles, `semantic_reality.json`, `manifest.json`;
- parameterized seed, batch count, approved/pended/denied authorization decision, paid/denied claim result, fixed run timestamp;
- output explicitly marked **synthetic test only**.

Reproducible CLI:

```sh
python -m claims_epa --seed 43 --count 5 --at 2026-10-07T23:00:00 --out /tmp/claims-epa-mvp
python -m claims_epa --seed 44 --authorization-status pended --claim-status denied
```

### E. Primary MediLacra pipeline and UI

Modified `hl7_demo/pipeline.py`:

- optional `include_claims_epa=False` to preserve previous behavior;
- one case per generated encounter from existing synthetic patient/coverage/encounter/transaction/observation and payer-local materialization;
- adds eight message counters only when enabled;
- writes separately from HL7 `messages.raw_hl7`, including in DuckDB mode;
- CLI flag `--include-claims-epa`; backwards-compatible `run_and_persist()` accepts the option.

Modified `medi_lacra_app.py` and `pages/2_Generate_and_Persist.py` to add **Include Claims + ePA (X12 and FHIR R4)** and show nested generated artifacts.

### F. Institutional separation correction during audit

Initial FHIR and X12 response serializers reused the clinical request name when projecting payer responses. This passed basic semantic tests but violated the design's independent institutional authorship.

Corrective changes:

- added `PayerSubject` to the *semantic case* from independent payer `MemberRecord`;
- made 835 / 278 response and FHIR ClaimResponse payer Patient use that payer-local identity;
- required matching payer/member routing keys, failing closed on mismatch;
- added a deliberate clinical/payer name divergence test.

This is a substantive architectural correction, not formatting cleanup.

### G. Temporal separation correction during audit

The initial fixture used the same service date for a billed claim and a prospective authorization for the same CPT. That created a misleading implied workflow relationship. The synthetic case now represents **two distinct events**:

- claim date from the existing clinical Encounter (demo: 2026-10-03);
- ePA proposed service date at least 14 days later than both the encounter date and run date (demo: 2026-10-21);
- payer coverage evaluated **separately** at each date.

A regression case terminates coverage between the dates, producing a paid existing claim and a denied future authorization. This demonstrates independent decisions rather than making ePA approval a prerequisite of an unrelated billed service. There is still no true clinical order lifecycle or multi-service history; that remains out of scope.

## 4. New verification and CI

Added:

- `tests/test_claims_epa_mvp.py`: scalar monetary/state constraints, X12 controls and envelopes, FHIR references, semantic parity, 100-case collision census, CLI artifacts, negative cases and institutional divergence.
- `tests/test_claims_epa_pipeline.py`: real `run_pipeline()` output and DuckDB boundary, main UI/CLI wiring.
- `.github/workflows/claims-epa-ci.yml`: Python 3.11, requirements, `python -m pytest -q tests/test_claims_epa_mvp.py`, `python -m pytest -q`, and five-case CLI smoke generation.

See test-results audit for exact workflow head SHA, passing/failing counts, and unexecuted acceptance tests.

## 5. Decision log

| Decision | Rationale | Limit |
|---|---|---|
| Reuse existing eligibility branch | Shared clinical/payer semantics and X12 envelope already exist | No merge into main |
| Both FHIR and X12 | Explicit user instruction | No conversion path |
| 837P/835 + 278 req/resp | Narrowest useful claim/payment + authorization test | 837I/D, 277CA, 275 deferred |
| FHIR Claim/ClaimResponse both uses | FHIR R4 standard uses same types for separate business uses | Not yet PAS profile-conformant |
| One service line, patient=subscriber | Avoid fabricating full finance/benefit ontology | No COB, dependents, multiple lines |
| Separate payer subject in responses | Institutional meaning survives disagreement | Demo payer data still seeded from same hidden truth |
| CLI plus main pipeline toggles | Match eligibility workflow and allow scale | Not yet live wire exchange |
| Raw files outside `messages.raw_hl7` | Do not misclassify X12/FHIR as HL7 v2 | Generalized artifact persistence deferred |
| Control/rendering validations | Fast regression against serialization errors | Not equivalent to external TR3/PAS validators |

## 6. Review and handoff

Review code in `claims_epa/`, run `python -m pytest -q`, inspect generated bundles and X12 interchanges, and then perform **external IRIS X12 and FHIR validator tests**. Do not use the files in production, represent them as complete licensed TR3/PAS conformance, or transmit them as PHI. Branch remains unmerged.

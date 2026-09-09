# MediLacra — Caregiver Health Baseline Phase 1 Build History

**Document type:** Build history / decision log / implementation receipt  
**Project:** MediLacra — Gravity Caregiver Health Baseline  
**Phase:** Phase 1  
**Document version:** v0.1  
**Project date:** 2026-09-08  
**GitHub CI timestamps:** UTC, therefore late-session runs appear as 2026-09-09  
**Branch:** `feature/gravity-caregiver-baseline-v0.1`  
**Branch base:** `connectathon/piqi-43`  
**Base commit:** `d2809c37a326d1c66b563f693dd65157d475602c`  
**Last implementation commit before this receipt:** `db8bf9f4c4571346e39f3227df5a41594b05de60`  
**Status at receipt creation:** PHASE 1 IMPLEMENTED — CI GREEN  
**Latest verified test result:** 12 passed, 1 warning  
**Primary plan:** `docs/gravity/CAREGIVER_HEALTH_BASELINE_PHASE_1_PLAN_v0.1_2026-09-08.md`

---

## 1. Purpose of this document

This file is the durable record of what Phase 1 actually became after implementation.

The project plan records intended scope. This build history records:

- what was reused;
- what was added;
- the sequence in which the implementation converged;
- decisions made during the build;
- alternatives explicitly rejected;
- test evidence;
- known limitations;
- deferred work;
- the state a future maintainer should inherit.

The goal is not to reconstruct intent from commit archaeology later.

---

## 2. Build thesis

Phase 1 was implemented under one primary rule:

> **Reuse existing MediLacra machinery before creating new machinery.**

The feature is therefore not a parallel application bolted onto MediLacra. It is a thin caregiver-health path built on top of the project's existing patient generation, DuckDB persistence, Streamlit patterns, FHIR normalization, and Connectathon quality infrastructure.

The resulting flow is:

```text
existing MediLacra synthetic Patient
                ↓
caregiver-facing Streamlit questionnaire
                ↓
FHIR QuestionnaireResponse
                ↓
small deterministic materialization layer
                ↓
Observation / MedicationStatement
                ↓
existing Connectathon Bundle normalization
                ↓
local quality / plausibility checks
                ↓
DuckDB + inspectable FHIR artifacts
```

The important boundary is that the person supplies human facts; terminology and representation work happen downstream.

---

## 3. Branch lineage and build footprint

The feature branch was created from the existing PIQI Connectathon branch rather than from `main` so it could reuse the Connectathon FHIR control layer directly.

At implementation head `db8bf9f4c4571346e39f3227df5a41594b05de60`, the branch was:

- **18 commits ahead** of `connectathon/piqi-43`;
- **0 commits behind**;
- composed of **11 new implementation/test/documentation files** relative to that base;
- approximately **2,895 added lines** before this build-history document was added.

No existing base-branch file was deleted to create Phase 1.

---

## 4. Reuse ledger

### 4.1 Existing patient ontology

Reused:

- `hl7_demo.models.Patient`
- `hl7_demo.generators.gen_patient()`
- existing synthetic demographic generation
- existing MediLacra patient identifiers and patient persistence

Decision: do not create a separate `Caregiver` domain class in Phase 1.

Rationale: the current experiment concerns a person answering a caregiver-health questionnaire. A separate caregiver-specific entity would introduce a new ontology before the relationship model actually requires one.

### 4.2 Existing persistence infrastructure

Reused:

- `utils.db.reader`
- `utils.db.writer`
- existing `MEDILACRA_DB_PATH` behavior
- existing DuckDB file lifecycle
- existing `storage_duckdb_entities.init_db()` and patient upsert path

New questionnaire persistence was added beside this infrastructure instead of introducing another database layer.

### 4.3 Existing Streamlit application pattern

Reused:

- MediLacra's multipage Streamlit organization
- existing local DuckDB selection pattern
- existing synthetic-patient generation workflow
- existing artifact-preview/download conventions

The caregiver questionnaire is a new page, not a second UI application.

### 4.4 Existing Connectathon FHIR normalization

Reused:

- `connectathon.fhir_control.prepare_control_bundle()`
- stable `fullUrl` generation
- internal reference rewriting
- collection-Bundle normalization
- null cleanup and existing representation cleanup behavior

This prevented the caregiver feature from quietly inventing a second FHIR reference policy.

### 4.5 Existing quality philosophy

Reused conceptually:

- Connectathon local preflight
- PIQITT-style structural checks
- explicit distinction between a malformed representation and an unusual clinical value
- inspectable checks instead of opaque composite scoring

The caregiver quality layer remains deliberately boring and local.

---

## 5. Files added in Phase 1

### Application / public surface

`pages/10_Gravity_Caregiver_Health.py`

- caregiver-facing Streamlit questionnaire;
- existing synthetic patient selection/generation;
- explicit decline controls;
- repeatable medication rows;
- artifact materialization and display;
- download of Questionnaire, QuestionnaireResponse, and Bundle;
- recent persisted response display.

`connectathon/gravity_caregiver.py`

- thin façade for the Phase 1 caregiver functionality;
- avoids forcing callers to know every implementation module.

### Questionnaire and response representation

`connectathon/gravity_questionnaire.py`

- FHIR R4 `Questionnaire` definition;
- version `0.1`;
- sleep, pain, PHQ-2, heart rate, medication status, and repeatable medication group;
- standard terminology where verified;
- local coding only where the Phase 1 concept is intentionally project-defined.

`connectathon/gravity_response.py`

- creates a FHIR `QuestionnaireResponse` from UI state;
- preserves explicit declines using FHIR DataAbsentReason;
- preserves parse failures as data-quality facts rather than silently coercing them;
- preserves medication text as supplied by the person.

### Materialization

`connectathon/gravity_materialize.py`

- materializes selected questionnaire facts into FHIR `Observation` resources;
- computes PHQ-2 total only when both source answers are present and valid;
- materializes medication reconciliation into `MedicationStatement`;
- performs only a tiny verified RxNorm normalization fixture in v0.1;
- uses existing Connectathon Bundle normalization.

### Quality

`connectathon/gravity_quality.py`

- structural preflight;
- response parse-error checks;
- sleep plausibility;
- pain plausibility;
- heart-rate plausibility;
- PHQ-2 component/total consistency;
- terminology/materialization checks;
- medication representation checks.

The quality gate is not a clinical decision support system.

### Storage

`connectathon/gravity_storage.py`

- dedicated QuestionnaireResponse persistence;
- raw input JSON;
- complete FHIR QuestionnaireResponse JSON;
- complete output Bundle JSON;
- nested item projection using DuckDB structures;
- retrieval of recent responses.

The storage design keeps both materialized structure and original serialized evidence.

### Tests

`tests/test_gravity_caregiver.py`

Covers:

- Questionnaire structure;
- standard FHIR resource types;
- expected LOINC/UCUM/RxNorm systems;
- happy-path materialization;
- PHQ-2 computation;
- explicit decline behavior;
- corrupted numeric input;
- plausibility boundaries;
- reference normalization;
- DuckDB persistence;
- medication-text-to-verified-RxNorm normalization behavior.

`tests/test_gravity_caregiver_streamlit.py`

- verifies the actual Streamlit caregiver page renders against an existing synthetic patient.

### CI

`.github/workflows/gravity-caregiver-smoke.yml`

- Python 3.11;
- installs the small test/runtime dependency set needed by the feature;
- compiles all caregiver modules and the Streamlit page;
- runs backend and Streamlit tests on pushes to the feature branch.

### Documentation

`docs/gravity/CAREGIVER_HEALTH_BASELINE_PHASE_1_PLAN_v0.1_2026-09-08.md`

- initial implementation plan and scope contract.

`docs/gravity/CAREGIVER_HEALTH_BASELINE_PHASE_1_BUILD_HISTORY_v0.1_2026-09-08.md`

- this implementation receipt and decision log.

---

## 6. Build sequence

This section records the conceptual build order rather than pretending the branch appeared fully formed.

### Stage A — establish the boundary

The first step was not writing UI code. The implementation boundary was fixed:

- caregiver health baseline only;
- Phase 1 only;
- local MediLacra execution;
- no IRIS round trip yet;
- no generalized caregiver ontology;
- no new quality engine;
- no product-wide UI redesign.

The dated v0.1 plan was committed first so implementation could be judged against a materialized scope rather than conversational memory.

### Stage B — use standard FHIR objects

The first representation decision was to use standard resources:

- `Questionnaire`
- `QuestionnaireResponse`
- `Patient`
- `Observation`
- `MedicationStatement`
- `Bundle`

Potential project-specific classes such as `CaregiverAssessment` or `AssessmentResponse` were not introduced.

This kept the experiment about semantic preservation rather than creating a new local schema and then proving that the new local schema can map back to FHIR.

### Stage C — build the questionnaire contract

The v0.1 questionnaire was constrained to a small baseline:

- sleep hours in the prior 24 hours;
- current pain score;
- PHQ-2;
- current heart rate;
- medication status;
- repeatable medication reconciliation details.

Questions are optional. Refusal is represented distinctly from absence and parse error.

### Stage D — preserve the response before interpretation

UI state is converted directly to `QuestionnaireResponse` before downstream extraction.

This preserves the person's response object independently of the later clinical materialization.

A downstream `Observation` is therefore not treated as the only surviving account of what the person entered.

### Stage E — materialize only recognizable clinical facts

The implementation then projects the small set of baseline responses into standard clinical resources.

Examples:

- heart rate → coded `Observation` with UCUM `/min`;
- pain score → LOINC-coded `Observation`;
- PHQ-2 questions → component `Observation`s;
- PHQ-2 total → derived `Observation` only when both components permit valid computation;
- medications → `MedicationStatement`.

The materialization layer is intentionally smaller than the QuestionnaireResponse.

### Stage F — reuse existing Bundle normalization

The resulting resources are placed into a collection Bundle and passed through the existing Connectathon control normalization.

That layer supplies stable UUID `fullUrl`s and rewrites local references so the Bundle remains self-contained.

### Stage G — add local quality gates

The quality layer was built to answer narrow questions:

- Is the FHIR structure self-contained?
- Did the response parse cleanly?
- Are values representationally plausible?
- Was a known response materialized into the expected resource shape?
- Did the terminology system survive?

It does not attempt to score the caregiver or infer clinical meaning from abnormal values.

### Stage H — persist both source and projection

DuckDB storage was added for:

- raw UI input;
- QuestionnaireResponse JSON;
- materialized Bundle JSON;
- nested response-item projection.

This creates enough durable evidence to compare source response against later transformations.

### Stage I — add the real UI and test it

The Streamlit page was added to the existing MediLacra application and then included in automated smoke testing.

The page uses existing synthetic patients instead of generating a parallel population model.

### Stage J — fix the medication interaction grain

During implementation, an early version exposed an **RxNorm code field to the caregiver**.

That was removed.

The corrected model is:

```text
person supplies medication name / dose / route / frequency
                    ↓
QuestionnaireResponse preserves human-supplied text
                    ↓
terminology normalization occurs downstream
```

This is now an explicit design rule, not merely a UI cleanup.

### Stage K — add a deliberately tiny terminology fixture

After removing the patient-facing code field, Phase 1 still needed one deterministic example proving that downstream terminology normalization can occur.

A tiny verified fixture was added for:

- `lisinopril 10 MG oral tablet`
- RxNorm `314076`

The fixture is explicitly not presented as a medication knowledge base.

Unknown medication names remain text rather than receiving fabricated codes.

### Stage L — final CI closure

The medication-grain change caused an intermediate test mismatch while implementation and tests were being brought back into alignment.

The branch was then corrected and the final implementation head completed successfully:

- workflow: `Gravity caregiver baseline smoke tests`;
- workflow run: `34306028167`;
- head commit: `db8bf9f4c4571346e39f3227df5a41594b05de60`;
- compile step: PASS;
- test step: PASS;
- final result: **12 passed, 1 warning in 1.19s**.

The remaining warning is an existing Python deprecation warning in `hl7_demo/utils.py` concerning an invalid escape sequence. It is not a caregiver Phase 1 test failure.

---

## 7. Decision log

### D-001 — Build on `connectathon/piqi-43`

**Decision:** branch from the Connectathon work instead of `main`.

**Reason:** the caregiver feature needs self-contained FHIR Bundle handling already solved by the Connectathon control layer.

**Rejected alternative:** duplicate the reference/fullUrl logic locally.

**Status:** accepted.

---

### D-002 — Reuse MediLacra `Patient`

**Decision:** a synthetic caregiver is represented by the existing MediLacra Patient object in Phase 1.

**Reason:** Phase 1 tests a person's health response and transformation path. A separate caregiver entity would add ontology without adding experimental value yet.

**Important limitation:** this does **not** claim that caregiver and patient are universally the same role. Relationship modeling is deferred until the experiment requires it.

**Status:** accepted for v0.1.

---

### D-003 — Use standard FHIR resources instead of bespoke assessment classes

**Decision:** use `Questionnaire` and `QuestionnaireResponse` as the source representation.

**Reason:** they already express the interaction being modeled and preserve compatibility with Gravity/SDC work.

**Rejected alternative:** local `CaregiverAssessment` / `AssessmentResponse` classes.

**Status:** accepted.

---

### D-004 — Preserve source response separately from extracted clinical resources

**Decision:** retain the complete QuestionnaireResponse even when selected answers are materialized into Observations or MedicationStatements.

**Reason:** extraction is a transformation. The transformed representation must not erase the source representation if semantic-preservation analysis is the purpose of the project.

**Status:** accepted.

---

### D-005 — Optional questions remain genuinely optional

**Decision:** the baseline questionnaire does not force answers solely to make downstream data cleaner.

**Reason:** missingness, refusal, parse failure, and true absence are different information states.

**Status:** accepted.

---

### D-006 — Explicit refusal uses FHIR DataAbsentReason

**Decision:** explicit decline is represented using standard FHIR DataAbsentReason `asked-declined`.

**Reason:** an explicit refusal is information and should not collapse into a blank field.

**Rejected alternative:** `null`, empty string, sentinel text, or local boolean flags as the only surviving representation.

**Status:** accepted.

---

### D-007 — Parse errors remain visible

**Decision:** malformed numeric input produces a data-absent/error representation and fails the local quality gate rather than being coerced.

**Reason:** the system should distinguish "person gave an unusual value" from "the representation could not parse what was supplied."

**Status:** accepted.

---

### D-008 — Plausibility is not normality

**Decision:** unusual but possible values are not rejected merely because they are clinically abnormal.

Example: a heart rate of 190 may be clinically important but is still a plausible human measurement and therefore can remain representationally valid.

Negative heart rate is not plausible and fails the local quality check.

**Reason:** data-quality logic must not silently become clinical-decision logic.

**Status:** accepted.

---

### D-009 — PHQ-2 total is derived only from complete valid components

**Decision:** no PHQ-2 total is emitted unless both component answers are present and recognized.

**Reason:** derived facts should retain the dependency structure of their source data.

**Rejected alternative:** treating missing component values as zero.

**Status:** accepted.

---

### D-010 — The caregiver is not a terminology server

**Decision:** remove the RxNorm code entry field from the caregiver-facing questionnaire.

**Reason:** the person knows the medication they take. They are not responsible for supplying a normalized vocabulary identifier.

The interaction grain is:

> human report first; terminology normalization downstream.

**Rejected alternative:** require or invite the caregiver to enter RxNorm codes.

**Status:** accepted and implemented.

---

### D-011 — Never fabricate medication coding

**Decision:** medication text that cannot be normalized with verified v0.1 knowledge remains uncoded text.

**Reason:** an uncoded truthful value is better evidence than a confidently wrong code.

**Status:** accepted.

---

### D-012 — Keep the RxNorm resolver tiny in Phase 1

**Decision:** include one deterministic verified lisinopril mapping rather than build or call a terminology service.

**Reason:** Phase 1 needs to prove the transformation boundary, not implement medication terminology infrastructure.

**Deferred:** real terminology-server integration and broader normalization.

**Status:** accepted.

---

### D-013 — Use UCUM for quantities where standard representation is known

**Decision:** heart rate and supported medication dose quantities use UCUM systems/codes.

**Reason:** units are part of meaning, not decorative metadata.

**Status:** accepted.

---

### D-014 — Keep sleep coding local in v0.1 where the exact baseline concept is project-defined

**Decision:** preserve the sleep-hours question using a MediLacra local code rather than force a questionable external code match.

**Reason:** greater specificity is not greater correctness. A local truthful concept is preferable to misrepresenting a standard terminology concept as equivalent.

**Status:** accepted pending later terminology review.

---

### D-015 — No composite caregiver quality score

**Decision:** expose specific checks and evidence instead of collapsing them into a single score.

**Reason:** a single number hides which relationship failed and encourages false precision.

**Rejected alternative:** generalized quality percentage / semantic score for Phase 1.

**Status:** accepted.

---

### D-016 — Reuse Connectathon reference normalization

**Decision:** caregiver Bundles pass through `prepare_control_bundle()`.

**Reason:** reference materialization is already solved and tested elsewhere in MediLacra.

**Status:** accepted.

---

### D-017 — Keep full serialized evidence in DuckDB

**Decision:** persist raw input JSON, QuestionnaireResponse JSON, and final Bundle JSON in addition to structured projections.

**Reason:** future transformations must remain auditable against source material.

**Status:** accepted.

---

### D-018 — IRIS is Phase 2

**Decision:** do not add fake IRIS scaffolding to make Phase 1 look more integrated than it is.

**Reason:** the new machine does not yet have the intended server path restored, and endpoint infrastructure is not required to prove local materialization.

**Status:** deferred.

---

## 8. Quality invariants

Phase 1 is built around several invariants.

### Invariant 1 — source survives projection

A clinical Observation or MedicationStatement must not become the only surviving account of the original questionnaire interaction.

### Invariant 2 — missingness states remain distinguishable

At minimum, Phase 1 distinguishes:

- unanswered;
- explicitly declined;
- parse/error state;
- answered value.

### Invariant 3 — unusual values are not automatically bad data

Clinical abnormality and representational invalidity are separate questions.

### Invariant 4 — terminology is not invented

If a standard code is not known and verified, the system does not manufacture one to make the Bundle look more complete.

### Invariant 5 — derived facts require their dependencies

PHQ-2 total is an example: no complete inputs, no derived total.

### Invariant 6 — internal FHIR references resolve

The final collection Bundle uses the existing deterministic fullUrl/reference normalization contract.

---

## 9. Test history

### Initial backend closure

The first complete backend implementation reached:

- **10 passed**.

This established the initial questionnaire, response, materialization, quality, and storage path.

### UI smoke coverage added

After the actual Streamlit page was included in CI:

- **11 passed, 1 warning**.

This established that the implementation was not merely importable backend code; the MediLacra page itself could render against an existing synthetic patient.

### Medication-grain correction

The RxNorm input was removed from the caregiver-facing interaction and tests were updated to reflect downstream normalization.

There was an intermediate failed workflow while the test contract and implementation were temporarily out of alignment.

This failure is part of the build history and is not erased from the record.

### Final verified implementation state

Workflow run `34306028167` on commit `db8bf9f4c4571346e39f3227df5a41594b05de60` completed successfully.

Final result:

```text
............                                                             [100%]
12 passed, 1 warning in 1.19s
```

The compile step also passed for:

- `connectathon/gravity_caregiver.py`
- `connectathon/gravity_questionnaire.py`
- `connectathon/gravity_response.py`
- `connectathon/gravity_materialize.py`
- `connectathon/gravity_quality.py`
- `connectathon/gravity_storage.py`
- `pages/10_Gravity_Caregiver_Health.py`
- `tests/test_gravity_caregiver.py`
- `tests/test_gravity_caregiver_streamlit.py`

---

## 10. Current Phase 1 behavior

A user can now:

1. run the existing MediLacra Streamlit application;
2. open the Gravity caregiver-health page;
3. select an existing synthetic patient or generate one using the existing generator;
4. enter or decline baseline caregiver-health questions;
5. enter medication reconciliation as human-readable information;
6. submit the assessment;
7. receive a standard FHIR QuestionnaireResponse;
8. materialize recognizable clinical resources;
9. receive a self-contained FHIR collection Bundle;
10. inspect local quality/plausibility checks;
11. download the generated artifacts;
12. preserve the response and Bundle in DuckDB;
13. inspect recently persisted QuestionnaireResponses.

No remote endpoint is required for Phase 1.

---

## 11. What Phase 1 does not claim

Phase 1 does **not** establish:

- full Gravity implementation-guide conformance;
- full SDC implementation-guide conformance;
- US Core conformance;
- production medication reconciliation;
- production terminology normalization;
- a clinical assessment of the caregiver;
- a validated screening application;
- identity proofing;
- patient/caregiver relationship authorization;
- consent or segmentation enforcement;
- IRIS persistence or round-trip behavior;
- endpoint interoperability;
- a generalized caregiver ontology;
- a generalized data-quality score.

Those claims would exceed what the implementation and tests currently establish.

---

## 12. Known limitations

### Medication terminology

The v0.1 RxNorm resolver is intentionally tiny. The verified lisinopril fixture demonstrates the boundary; it does not provide general medication normalization.

### Caregiver relationship semantics

A Phase 1 synthetic caregiver is represented by the existing Patient model. A future phase will need explicit relationship modeling if the caregiver must be represented as a distinct person acting with respect to another patient's record.

### Sleep terminology

The exact "hours slept in past 24 hours" baseline concept remains locally coded in v0.1 pending terminology review.

### Persistence scope

The DuckDB storage path is local experimental persistence, not a production clinical repository.

### CI warning

The current successful workflow includes one deprecation warning in existing `hl7_demo/utils.py` for an invalid Python escape sequence. The caregiver tests themselves pass.

---

## 13. Deferred Phase 2 work

The next phase should begin from the artifacts already materialized here rather than rebuilding the questionnaire.

Primary deferred work:

- restore / configure IRIS on the new machine;
- define the IRIS persistence boundary;
- send the Phase 1 artifact set through IRIS;
- retrieve or re-materialize it after the round trip;
- compare source QuestionnaireResponse, local FHIR materialization, stored representation, and retrieved representation;
- record exactly what relationships survive each transformation;
- evaluate consent / segmentation implications once the relationship graph becomes real rather than hypothetical;
- decide whether a distinct caregiver/person/related-person model is required at that boundary;
- replace or extend tiny terminology fixtures only when the experiment requires broader terminology behavior.

The guiding question remains:

> **What relationships survive transformation?**

---

## 14. Handoff notes

A maintainer picking up this branch should not start by redesigning the questionnaire.

First verify the current contract:

```text
Questionnaire
    ↓
QuestionnaireResponse
    ↓
materialized clinical resources
    ↓
normalized collection Bundle
    ↓
quality evidence
    ↓
DuckDB evidence
```

Then preserve these rules unless there is a conscious decision to change them:

- source response is durable;
- decline is not null;
- parse error is not clinical abnormality;
- abnormal is not automatically implausible;
- caregiver-facing UI does not ask for terminology identifiers;
- unknown medication text stays honest;
- standard FHIR is preferred over bespoke local objects;
- existing MediLacra infrastructure is reused before adding parallel infrastructure;
- Phase 2 should extend the transformation chain, not rebuild Phase 1.

---

## 15. Build receipt

**Branch:** `feature/gravity-caregiver-baseline-v0.1`  
**Implementation head verified by CI:** `db8bf9f4c4571346e39f3227df5a41594b05de60`  
**Workflow run:** `34306028167`  
**Compile:** PASS  
**Tests:** 12 PASS  
**Warnings:** 1 existing deprecation warning  
**IRIS:** deferred to Phase 2  
**Phase 1 disposition:** implemented and locally testable through the MediLacra Streamlit UI.

---

## 16. Version history

### v0.1 — 2026-09-08

Initial build-history and decision-log materialization for Caregiver Health Baseline Phase 1.

Captures:

- branch lineage;
- reuse decisions;
- implementation sequence;
- medication interaction correction;
- final CI evidence;
- explicit limitations;
- Phase 2 handoff boundary.

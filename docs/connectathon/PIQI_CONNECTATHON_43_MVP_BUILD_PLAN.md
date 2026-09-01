# PIQI Connectathon 43 — MediLacra / PIQITT MVP Build Plan

**Project:** MediLacra + PIQITT  
**Event:** HL7 FHIR Connectathon 43 — Patient Information Quality Improvement (PIQI) Framework Track  
**Connectathon dates:** September 19–20, 2026  
**Branch:** `connectathon/piqi-43`  
**Branch base:** `experiment/disco-inferno`  
**Plan created:** September 1, 2026  
**Status:** ACTIVE — MVP GAP-CLOSURE PLAN

---

## 1. Purpose

The purpose of this branch is to make MediLacra and PIQITT useful participants in the PIQI Framework track at HL7 FHIR Connectathon 43 without turning the Connectathon into a general platform rewrite.

The target experiment is deliberately narrow:

> Generate a known synthetic FHIR case, introduce one known information-quality defect, submit the baseline and mutant to multiple PIQI-enabled endpoints, preserve the raw evaluation evidence, and compare both endpoint-to-endpoint agreement and endpoint results against known synthetic ground truth.

This branch exists to close only the gap required to perform that experiment reproducibly.

---

## 2. Track Alignment

The PIQI Connectathon track defines three system roles:

1. **Data Source / Provider** — generates or supplies FHIR and/or C-CDA content.
2. **PIQI Enabled Endpoint** — applies PIQI Framework evaluation rubrics and returns evaluation reports.
3. **Terminology / Knowledge Provider** — provides terminology or advanced knowledge used by the PIQI endpoint.

For MVP, MediLacra / PIQITT participates as a **Data Source / Provider**.

The branch does **not** attempt to make PIQITT a standards-conformant independent PIQI Enabled Endpoint.

The primary Connectathon target is Scenario 2:

> Independent PIQI Enabled Endpoints evaluate the same payload using common PIQI framework components and should produce the same rubric results.

Our contribution adds a second comparison axis:

```text
TRACK QUESTION

same payload
    ↓
PIQI Endpoint A ↔ PIQI Endpoint B
    ↓
do the implementations agree?


MEDILACRA ADDITION

known synthetic ground truth
    ↓
controlled mutation
    ↓
PIQI result
    ↓
did the assessment detect the defect we knowingly introduced?
```

This creates two useful measurements:

- **implementation agreement** — endpoint A versus endpoint B;
- **assessment correspondence** — endpoint result versus known injected defect.

---

## 3. Existing Assets

This is not a greenfield build.

### MediLacra already provides

- deterministic synthetic patient-centered healthcare data;
- patients, encounters, observations, transactions, providers, and order identifiers;
- HL7 v2.5-style ADT, ORU, DFT, ORM, and lab ORU messages;
- Streamlit and CLI generation paths;
- DuckDB persistence;
- offline-capable generation boundaries;
- deterministic scenario seeds;
- structured experimental output.

### PIQITT already provides

- HL7 v2 parsing;
- HL7 → simplified FHIR Bundle conversion;
- Patient, Encounter, Observation, DiagnosticReport, and financial-resource mapping;
- local SAM evaluation;
- local profile evaluation;
- scorecard output;
- JSON / NDJSON export.

### Disco Inferno already provides

- immutable baseline representation (`Beatrice`);
- deterministic corruption selection;
- mutation operators;
- separate reality seed (`42`) and Inferno seed (`666`);
- exact corruption manifests;
- control runs;
- timestamped experiment bundles;
- artifact hashes / evidence conventions;
- comparison and reporting infrastructure;
- offline-by-default experiment execution.

The major missing capability is that Disco Inferno currently corrupts its tabular representation while FHIR/HL7 exports are projected from the untouched generated case. Direct FHIR corruption was intentionally deferred. The Connectathon is now the experiment that requires it.

---

## 4. MVP Boundary

### In scope

1. Stable non-UI PIQITT FHIR export.
2. Controlled FHIR mutation.
3. Machine-readable mutation manifest using official PIQI vocabulary where known.
4. Tiny deterministic Connectathon scenario pack.
5. Track-ingestion preflight.
6. PIQI endpoint submission and raw response capture.
7. Minimal response normalization.
8. Endpoint-to-endpoint comparison.
9. Ground-truth-to-endpoint comparison.
10. Reproducible one-command experiment orchestration.
11. Durable evidence bundle and report.

### Explicitly out of scope

- making PIQITT an independent standards-conformant PIQI endpoint;
- building a new PIQI engine;
- C-CDA support for this experiment;
- generalized FHIR generation inside MediLacra;
- full US Core implementation;
- full USCDI implementation;
- terminology-server implementation;
- advanced knowledge-server SAMs;
- generalized entropy scoring;
- broad clinical inference;
- large synthetic cohorts;
- UI redesign;
- Reality Model architectural work unrelated to the Connectathon experiment;
- graph databases;
- generalized healthcare ontology work;
- direct productization.

If an item does not improve the ability to execute and inspect the Connectathon experiment, it should not block MVP.

---

## 5. Architectural Contract

```text
MEDILACRA
creates synthetic reality
        ↓
HL7 v2
        ↓
PIQITT
projects HL7 → FHIR
        ↓
FHIR BASELINE
        ↓
CONNECTATHON DISCO LAYER
introduces one declared information-quality defect
        ↓
FHIR MUTANT + MUTATION MANIFEST
        ↓
PIQI ENDPOINT A         PIQI ENDPOINT B
        ↓                       ↓
raw Evaluation/Audit Reports
        ↓
NORMALIZATION
        ↓
COMPARATOR
        ↓
A ↔ B
A ↔ known ground truth
B ↔ known ground truth
```

### Core epistemic invariant

> **A mutant must differ from its baseline only by the declared mutation.**

That invariant is more important than any aggregate score.

### Secondary invariant

> **Raw endpoint evidence is preserved before normalization or interpretation.**

We never want the comparison layer to become the only surviving account of what an endpoint actually returned.

---

## 6. Core Artifact Ontology

The MVP experiment uses four primary objects.

### Baseline

An untouched FHIR Bundle projected from a known MediLacra synthetic case.

### Mutation

Exactly one deliberate change applied to the baseline FHIR representation.

### Manifest

A machine-readable receipt declaring:

- case identifier;
- baseline artifact hash;
- mutant artifact hash;
- operator;
- resource type;
- resource identifier;
- FHIR path;
- prior value;
- mutated value;
- expected PIQI SAM;
- expected PIQI dimension when known;
- reality seed;
- mutation seed;
- code revision.

### Observation

What an external PIQI endpoint reported about the submitted baseline or mutant.

---

## 7. Proposed Mutation Manifest Shape

This is intentionally small and may change after the September 2 kickoff call.

```json
{
  "case_id": "PIQI-0042",
  "baseline_sha256": "...",
  "mutant_sha256": "...",
  "reality_seed": 42,
  "mutation_seed": 666,
  "mutation": {
    "operator": "remove_element",
    "resource": "Observation",
    "resource_id": "obs-001",
    "path": "code.coding[0].system",
    "before": "http://loinc.org",
    "after": null
  },
  "expected": {
    "sam": "CONCEPT_HASCODESYSTEM",
    "dimension": "AV_UNPOP"
  }
}
```

The official track SAM mnemonic should be used verbatim whenever the target is known.

---

# 8. Build Phases

## Phase 0 — Freeze the experiment contract

### Goal

Create a stable definition of what counts as evidence before adding code.

### Work

- Use this document as the project operating contract.
- Define Baseline, Mutation, Manifest, and Observation.
- Preserve the one-declared-mutation invariant.
- Preserve raw endpoint responses.
- Record all unresolved track-dependent assumptions explicitly rather than guessing.

### Acceptance criteria

- A person unfamiliar with the implementation can inspect a case directory and understand what was deliberately changed.
- Ground truth is represented independently of PIQI endpoint output.

---

## Phase 1 — Stable PIQITT FHIR export

### Goal

Make PIQITT usable as a deterministic-enough command-line transformation boundary rather than requiring the Streamlit UI.

### Proposed interface

```bash
python -m scripts.fhir_convert \
  --input medilacra.hl7 \
  --output baseline.fhir.json
```

Exact module naming may differ based on the existing repo layout.

### Work

- Reuse existing PIQITT conversion functions.
- Add a thin CLI wrapper.
- Do not rewrite mapping logic.
- Preserve FHIR output for later hashing and inspection.

### Required tests

- known ADT produces Patient + Encounter;
- known ORU produces Observation;
- known DFT produces the expected financial representation;
- output is valid JSON;
- output is a FHIR Bundle recognized by existing PIQITT code.

### Acceptance criteria

One command converts a known MediLacra HL7 fixture into an inspectable FHIR Bundle without manual UI interaction.

---

## Phase 2 — FHIR mutation layer

### Goal

Extend Disco Inferno's existing controlled-corruption model to FHIR.

### Proposed location

```text
experiments/disco_inferno/fhir_corruptions.py
```

### Minimum mutation primitives

```text
remove_element(bundle, resource, path)
replace_value(bundle, resource, path, value)
remove_coding_component(bundle, resource, path)
```

Do not build a generalized FHIR mutation DSL unless the experiment actually demands one.

### Initial PIQI-shaped mutations

Candidate targets pending track confirmation:

```text
ATTR_ISPOPULATED
    remove a populated target element

CONCEPT_HASCODESYSTEM
    remove coding.system

CONCEPT_ISVALIDMEMBER
    replace a code with a known non-member

ATTR_ISPASTDATE
    replace a past date with a future date
```

The final three defects used in the scenario pack should be selected after the September 2 kickoff call.

### Required tests

- baseline object is never mutated in place;
- mutant differs from baseline;
- only the intended path changes;
- manifest reports the exact before/after state;
- identical input + seed selects the same target/change;
- control mutation produces zero semantic delta.

### Acceptance criteria

We can prove exactly what was damaged rather than merely assert that a mutant is bad.

---

## Phase 3 — Tiny deterministic scenario pack

### Goal

Create a manually inspectable PIQI challenge corpus.

### Initial structure

```text
connectathon/scenarios/piqi43_mvp/
├── case_000_control/
├── case_001_availability/
├── case_002_conformity/
└── case_003_value_or_format/
```

Each case contains:

```text
baseline.fhir.json
mutant.fhir.json
manifest.json
```

### Case-selection criteria

A mutation belongs in the MVP only if it is:

1. tied to an official/common PIQI SAM;
2. clearly expressible in FHIR;
3. deterministic;
4. still ingestible through the track tooling;
5. expected to produce an unambiguous result.

### Scale

Use one control plus approximately three mutant cases.

Do not use a large cohort. The corpus should be small enough that participants can inspect the exact FHIR JSON manually when endpoints disagree.

### Acceptance criteria

The entire challenge corpus can be understood without running a database query or statistical analysis.

---

## Phase 4 — Track-ingestion preflight

### Goal

Separate FHIR ingest failures from patient-information-quality failures.

### Principle

```text
FHIR cannot be consumed
    ≠
FHIR is consumable but contains poor-quality patient information
```

Most mutants should remain structurally ingestible FHIR.

### Work

For every baseline and mutant:

1. parse JSON;
2. verify Bundle shape;
3. exercise the same FHIR → PIQI conversion/client path intended for Connectathon use;
4. record whether ingestion succeeded.

### Minimal preflight record

```json
{
  "case_id": "PIQI-0042",
  "baseline_ingest": "PASS",
  "mutant_ingest": "PASS"
}
```

### Acceptance criteria

Every scenario reaches the PIQI evaluation boundary through the track-provided ingestion path.

---

## Phase 5 — PIQI endpoint submission and raw capture

### Goal

Submit the same controlled cases to multiple PIQI Enabled Endpoints and preserve what each endpoint actually reports.

### Timing dependency

Implement after the September 2 kickoff provides current API/client behavior and clarifies WIP response structures.

Do not hard-code assumptions about prototype report schemas before seeing live responses.

### Proposed module

```text
connectathon/piqi_client.py
```

### Configuration

Endpoint URLs and authentication belong in configuration/environment variables, not source code.

Conceptually:

```yaml
endpoints:
  reference:
    url: ...
    auth_env: PIQI_REFERENCE_KEY

  piqxl:
    url: ...
    auth_env: PIQXL_KEY
```

### Capture requirements

For every request preserve:

- endpoint identifier;
- case identifier;
- baseline or mutant variant;
- submission timestamp;
- submitted artifact hash;
- rubric/model identifier when available;
- HTTP status;
- raw PIQI Evaluation Report;
- raw Audit Report;
- raw error response if evaluation fails.

### Rule

**Do not normalize during capture.**

Raw evidence first. Interpretation later.

### Acceptance criteria

The same scenario can be submitted to at least two participating PIQI endpoints and both raw responses are retained verbatim.

---

## Phase 6 — Minimal response normalization

### Goal

Create only enough common structure to compare independent PIQI implementations.

### Internal comparison shape

```text
case_id
endpoint
test_variant      # baseline | mutant
sam
dimension
target
status
message_or_evidence
raw_response_pointer
```

### Implementation

Prefer one adapter per endpoint if their response structures differ:

```text
normalize_reference_response()
normalize_piqxl_response()
```

Do not attempt to normalize every field returned by either implementation.

### Acceptance criteria

Responses from both endpoints can be represented in a common comparison table while retaining pointers to their untouched native evidence.

---

## Phase 7 — Comparator

### Goal

Answer the actual experiment questions.

For each scenario compare:

```text
GROUND TRUTH ↔ Endpoint A
GROUND TRUTH ↔ Endpoint B
Endpoint A   ↔ Endpoint B
```

### Output shape

| Case | Intended SAM | Expected | Endpoint A | Endpoint B | A↔B | A↔Truth | B↔Truth |
|---|---|---|---|---|---|---|---|
| Control | — | no introduced failure | ... | ... | ... | ... | ... |
| 001 | ATTR_ISPOPULATED | FAIL | ... | ... | ... | ... | ... |
| 002 | CONCEPT_HASCODESYSTEM | FAIL | ... | ... | ... | ... | ... |

### Interpretation boundary

The comparator reports differences. It does not decide which independent implementation is correct.

If Endpoint A returns FAIL and Endpoint B returns PASS, the result is:

```text
ENDPOINT DIVERGENCE
```

The next action is human inspection of:

- baseline;
- mutant;
- mutation manifest;
- endpoint A raw report;
- endpoint B raw report;
- applicable PIQI model/rubric/SAM definition.

### Acceptance criteria

One command produces both machine-readable and human-readable endpoint agreement / ground-truth comparison results.

---

## Phase 8 — One-command orchestration

### Goal

Turn the individual working pieces into a reproducible experiment run.

### Proposed interface

```bash
python -m connectathon.run \
  --scenario-pack piqi43_mvp \
  --endpoints reference,piqxl
```

### Proposed output

```text
connectathon/results/<run-id>/
├── cases/
│   ├── case_000/
│   │   ├── baseline.fhir.json
│   │   ├── mutant.fhir.json
│   │   └── manifest.json
│   └── ...
├── responses/
│   ├── reference/
│   └── piqxl/
├── normalized/
├── comparison.json
├── comparison.csv
└── CONNECTATHON_REPORT.md
```

Reuse Disco Inferno's existing timestamped output, artifact, hashing, reporting, and evidence conventions wherever possible.

### Run report metadata

Preserve:

- MediLacra commit SHA;
- PIQITT commit SHA;
- scenario-pack version;
- reality seed;
- mutation seed;
- endpoint identifiers;
- PIQI model/rubric identifiers where available;
- artifact hashes;
- preflight status;
- endpoint results;
- divergences;
- execution timestamps.

### Acceptance criteria

The complete experiment can be reproduced with one orchestration command except for external endpoint availability.

---

# 9. Build Order

Execute in this order:

```text
1. experiment contract                       ← this document
2. PIQITT CLI FHIR export
3. FHIR mutation + manifest
4. control + three-mutant scenario pack
5. confirm exact target SAMs at kickoff
6. track-tool ingest preflight
7. endpoint raw capture
8. response normalization
9. comparison
10. one-command orchestration
11. documentation/UI polish only if demanded
```

Do not skip directly to endpoint automation before the local artifact pipeline is trustworthy.

---

# 10. Definition of MVP Complete

MVP is complete when all of the following are true:

- [ ] MediLacra source contains no PHI and the selected scenario can run offline.
- [ ] PIQITT transforms the selected MediLacra source into FHIR without manual UI interaction.
- [ ] An untouched baseline FHIR Bundle is retained.
- [ ] Every mutant contains exactly one declared controlled defect.
- [ ] The mutation manifest records exact before/after state.
- [ ] The mutation manifest uses the official PIQI SAM mnemonic for the intended target where known.
- [ ] Baseline and mutant both pass the track's ingestion boundary.
- [ ] The same case can be evaluated by at least two PIQI Enabled Endpoints.
- [ ] Raw Evaluation Reports are preserved.
- [ ] Raw Audit Reports are preserved when supplied.
- [ ] Endpoint results can be compared automatically.
- [ ] Endpoint results can be compared against known mutation ground truth automatically.
- [ ] Every result can be traced to source artifacts, seeds, hashes, and code revisions.
- [ ] A control case demonstrates zero introduced mutation.
- [ ] One command reproduces the experiment except for external endpoint availability.

Once those conditions are true, stop adding infrastructure and use the system against other implementations.

---

# 11. Kickoff-Call Decision Points

**PIQI Track Kickoff:** September 2, 2026 at 12:00 PM ET  
**Connectathon Touchpoint:** September 9, 2026 at 12:00 PM ET

Questions to resolve before freezing the final scenario pack:

1. Which 3–5 PIQI SAMs / US Realm Clinical Rubric elements would be most useful for a controlled before/after synthetic test corpus?
2. Are paired baseline/mutant FHIR Bundles with a machine-readable defect manifest useful for Scenario 2?
3. Which FHIR Bundle shapes are most representative of the expected test traffic?
4. What is the current preferred way to submit FHIR payloads to each participating PIQI endpoint?
5. What Evaluation Report / Audit Report structures should we expect during the Connectathon?
6. Which model/rubric/SAM versions or identifiers should be captured for reproducibility?
7. Are there known areas of expected implementation divergence that would benefit from controlled defect injection?

The build should absorb answers to these questions without changing its basic architecture.

---

# 12. Working Hypotheses

These are hypotheses, not claims established by the track.

### H1 — Controlled defects improve endpoint comparison

Using a known mutation manifest should make endpoint disagreement easier to diagnose than using only naturally messy synthetic data.

### H2 — PIQI endpoint agreement and assessment validity are different measurements

Two endpoints may agree with one another and still fail to detect a deliberately introduced defect. Conversely, one endpoint may detect a defect while another does not.

### H3 — Small manually inspectable fixtures are more useful than large cohorts during interoperability debugging

Large cohorts can be added later if scale becomes a test objective. Initial ambiguity resolution benefits from tiny cases.

### H4 — Most useful quality mutations should remain structurally ingestible FHIR

The purpose is to test patient-information quality rather than merely FHIR parse/validation failure.

---

# 13. Research / Interpretation Boundary

This branch should distinguish three layers of evidence:

### Established by generated artifacts

- what synthetic reality was generated;
- what FHIR baseline was produced;
- exactly what mutation was applied;
- what each endpoint returned.

### Derived by deterministic comparison

- whether endpoint outputs match;
- whether endpoint output matches the expected mutation target;
- which cases diverged.

### Requires human / specification interpretation

- why endpoints diverged;
- which implementation is correct;
- whether a SAM/rubric definition is ambiguous;
- whether a mutation targets the intended PIQI concept cleanly;
- whether a discrepancy implies an implementation bug, specification ambiguity, terminology issue, or test-design problem.

The software should expose these boundaries rather than collapsing them into a single quality score.

---

# 14. Naming / Internal Vocabulary

The existing experiment vocabulary remains useful but should not obscure standards terminology in shared Connectathon artifacts.

- **Beatrice** — untouched reference representation.
- **Disco Inferno** — controlled degradation experiment.
- **Reality seed 42** — determines which synthetic world exists.
- **Inferno seed 666** — determines deterministic corruption selection.

External/shared artifacts should additionally use plain terms such as:

- baseline;
- mutant;
- mutation;
- manifest;
- expected SAM;
- endpoint result;
- endpoint divergence.

The joke names are internal lineage; the standards-facing evidence must remain immediately interpretable by people who have never seen the project.

---

# 15. Immediate Next Work

The first implementation work on this branch should be:

1. verify the existing PIQITT conversion path against a small current MediLacra HL7 fixture;
2. add a non-Streamlit FHIR export command;
3. add the smallest safe FHIR mutation primitive;
4. prove baseline immutability and exact-delta manifest generation;
5. wait for / incorporate the September 2 track-lead guidance before freezing the three MVP mutation targets.

No additional architectural expansion is required before those steps work.

---

## Final Build Principle

> **MediLacra creates reality. PIQITT materializes FHIR. Disco Inferno introduces known information-quality defects. PIQI measures them. The Connectathon harness compares independent observations.**

That is the MVP.
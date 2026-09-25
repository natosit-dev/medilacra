# MediLacra — SDOH Baseline Phase 1 Build Plan

**Version:** v0.1  
**Date:** 2026-09-24  
**Status:** Proposed build plan  
**Reference implementation:** Gravity Caregiver Health Baseline  
**Branch:** `feature/gravity-sdoh-baseline-v0.1`

---

# 1. Purpose

Add a new MediLacra Streamlit page for basic SDOH screening using standardized Gravity Project questions.

The page should have the same interaction and artifact shape as the existing Caregiver Health page:

```text
synthetic Patient
      ↓
standardized questionnaire
      ↓
QuestionnaireResponse
      ↓
FHIR clinical representation
      ↓
HL7 v2 representation
      ↓
quality / semantic-survival checks
      ↓
DuckDB persistence + downloadable artifacts
```

The experiment is not:

> Can MediLacra invent another SDOH ontology?

It is:

> Can MediLacra capture standardized social-risk questions once and preserve their meaning across representations?

---

# 2. Phase 1 Scope

Phase 1 will create one MediLacra-owned FHIR Questionnaire composed of:

## Hunger Vital Sign

Complete basic instrument:

- `88122-7` — worry food would run out
- `88123-5` — food bought did not last
- `88124-3` — food insecurity risk, derived

The first two are human responses.

The third is computed.

## PRAPARE Basics

Initial subset:

### Housing
- `71802-3` — housing situation
- `93033-9` — worry about losing housing

### Material resources
- `93031-3` — material needs / resources unable to obtain
- `93030-5` — transportation barriers

### Social and emotional
- `93029-7` — frequency of meaningful social contact
- `93038-8` — stress

This is intentionally **not the complete PRAPARE instrument**.

---

# 3. Instrument Identity

The complete Questionnaire is a MediLacra instrument composed from standardized questions.

Do not identify the overall Questionnaire as PRAPARE.

Proposed identity:

```text
id:
medilacra-sdoh-baseline

url:
https://medilacra.dev/fhir/Questionnaire/sdoh-baseline

version:
0.1

name:
MediLacraSDOHBaseline

title:
MediLacra SDOH Baseline
```

Individual questions retain their canonical LOINC identities and standard answer codes.

This keeps three things separate:

```text
MediLacra
owns composition / workflow

Gravity / source instruments
define assessment semantics

LOINC
identifies questions and coded answers
```

---

# 4. Interaction Grain

One `QuestionnaireResponse` represents:

> one SDOH assessment of one Patient at one authored time.

No Encounter is required.

No ServiceRequest is required.

No practitioner attribution is required for Phase 1.

No diagnosis or Condition should be inferred merely because a screening response exists.

---

# 5. Page Shape

New page:

```text
pages/11_Gravity_SDOH.py
```

The page should deliberately resemble `10_Gravity_Caregiver_Health.py`.

## Section 1 — Synthetic Patient

Reuse existing behavior:

- load recent synthetic Patients from DuckDB;
- select Patient;
- generate Patient using existing `gen_patient()`;
- persist using existing Patient machinery.

No SDOH-specific Patient model.

## Section 2 — SDOH Baseline

Suggested layout:

```text
Gravity — SDOH Baseline

Standard questions.
Preserve the response.
See what survives.

[Reset assessment]


1. Synthetic patient

Patient
[ P000123 — Example Person ▼ ]       [Generate patient]


2. SDOH Baseline

Hunger Vital Sign
─────────────────

Within the past 12 months...
[answer ▼]                            [Decline]

Within the past 12 months...
[answer ▼]                            [Decline]

Food insecurity risk
At risk
[computed]


Housing
───────

What is your housing situation today?
[answer ▼]                            [Decline]

Are you worried about losing your housing?
[answer ▼]                            [Decline]


Material resources
──────────────────

Which resources have you been unable to obtain?
[multiselect]                         [Decline]

Has lack of transportation kept you from...
[answer ▼]                            [Decline]


Social and emotional health
───────────────────────────

How often do you see or talk to people you care about?
[answer ▼]                            [Decline]

How stressed are you?
[answer ▼]                            [Decline]


[Submit assessment]
```

Exact question text and answer displays should come from the verified standardized definitions, not paraphrased UI copy.

---

# 6. Decline and Missingness

Reuse the existing Caregiver interaction:

```text
[Decline]
```

A decline remains:

```text
data-absent-reason = asked-declined
```

Do not collapse:

```text
unanswered
declined
coded "don't know"
coded "refused"
negative response
```

into one state.

These represent different facts.

For instruments that themselves contain a coded response such as:

```text
Don't know / refused
```

preserve that coded answer independently from MediLacra's explicit Decline control.

---

# 7. Questionnaire Definition

Add:

```text
connectathon/gravity_sdoh_questionnaire.py
```

Responsibilities:

- Questionnaire canonical metadata;
- question definitions;
- LOINC codes;
- answer options;
- grouping;
- repeats/cardinality;
- HVS question metadata;
- PRAPARE subset metadata;
- SDOH domain bindings.

Prefer declarative definitions where reasonable.

Conceptually:

```python
QuestionDef(
    link_id="hvs-food-run-out",
    loinc="88122-7",
    domain="food-insecurity",
    ...
)
```

Do not create a new healthcare ontology or broad generalized form framework.

The metadata only needs to support this instrument and obvious reuse.

---

# 8. QuestionnaireResponse Capture

Add:

```text
connectathon/gravity_sdoh_response.py
```

Reuse from existing Gravity response code:

- `fhir_id()`
- `build_patient_resource()`
- `answer_absent_reason()`
- `iter_response_items()`
- `find_response_items()`
- standard `data-absent-reason`

New responsibilities:

- coded single-choice answers;
- coded multi-choice answers;
- explicit decline;
- unanswered items;
- nested groups;
- Questionnaire canonical reference;
- assessment authored time.

Raw UI answers should become standard FHIR answer types directly.

Avoid a bespoke intermediate SDOH dataclass layer.

---

# 9. Hunger Vital Sign Derivation

Add one explicit deterministic rule.

Conceptually:

```text
Q1 = Often true
OR
Q1 = Sometimes true
OR
Q2 = Often true
OR
Q2 = Sometimes true

        ↓

Food insecurity risk = At risk
```

Otherwise, when both questions supply sufficient non-risk answers:

```text
Food insecurity risk = No risk
```

If required source answers are missing, declined, or otherwise insufficient:

```text
do not invent risk result
```

The result should exist as a derived fact, not a third human-entered field.

The UI may display it read-only after sufficient answers exist.

---

# 10. SDOH Observation Materialization

Add:

```text
connectathon/gravity_sdoh_materialize.py
```

Each answered standardized screening question should materialize as a Gravity-compatible screening-response Observation.

Conceptually:

```text
QuestionnaireResponse
        ↓
Observation
    status
    code = question LOINC
    subject = Patient
    value = coded answer
    effectiveDateTime
    derivedFrom = QuestionnaireResponse

    category:
        survey
        sdoh
        specific SDOH domain
```

Examples of domain categories:

```text
food-insecurity
housing-instability
homelessness
transportation-insecurity
social-connection
stress
```

Use only verified Gravity categories.

Do not invent local categories where standard ones exist.

---

# 11. Interpretation Rules

Do not automatically interpret every screening response.

Where Gravity defines an answer as evidence of social risk:

```text
Observation.interpretation = POS
```

Where the response does not indicate risk:

```text
no POS
no NEG unless explicitly appropriate
```

A negative-looking answer is not automatically a clinically established negative finding.

---

# 12. Declined Screening Observations

For standardized SDOH screening questions, Phase 1 should preserve explicit decline through the extracted representation.

Conceptually:

```text
Observation.code
    = original question

Observation.category
    = survey
    = sdoh
    = relevant domain

Observation.dataAbsentReason
    = asked-declined

NO value
NO interpretation
```

This differs intentionally from some Caregiver materialization behavior, where unanswered/declined items simply do not produce an Observation.

That difference should be tested and documented.

---

# 13. Bundle Construction

Reuse:

```text
connectathon.fhir_control.prepare_control_bundle()
```

Bundle should contain:

```text
Patient

Questionnaire

QuestionnaireResponse

Observation
    one per relevant screening response

Observation
    Hunger Vital Sign risk result, when computable
```

No Condition in Phase 1.

No Goal.

No ServiceRequest.

No Procedure.

Those represent downstream interpretation or intervention and should not be invented from a screening form.

---

# 14. HL7 v2

Phase 1 should output an ORU^R01 just as Caregiver Health does.

But do not create another giant hard-coded projector.

Extract the obvious common seam from:

```text
connectathon/gravity_hl7v2.py
```

into something approximately like:

```text
QuestionnaireResponse item
        ↓
coded question + coded answer
        ↓
OBX
```

Then keep instrument-specific mapping/configuration in the Caregiver and SDOH modules.

Desired result:

```text
FHIR QuestionnaireResponse
          ↘
           generic projection mechanics
          ↗
HL7 v2 OBX representation
```

Not:

```text
500 more lines of if link_id == ...
```

The source of truth remains the QuestionnaireResponse.

The ORU is a projection.

---

# 15. Persistence

Reuse unchanged:

```text
connectathon/gravity_storage.py
```

The current schema already supports:

- questionnaire URL/version;
- Patient;
- authored timestamp;
- nested paths;
- coding system;
- code;
- displayed value;
- numbers;
- absent reasons;
- raw input JSON;
- complete QuestionnaireResponse JSON;
- Bundle JSON.

Do not make an `sdoh_questionnaire_responses` table.

That would duplicate an abstraction we already built correctly.

---

# 16. Quality Gate

Add:

```text
connectathon/gravity_sdoh_quality.py
```

Same philosophy as Caregiver:

> plausibility and semantic preservation before scoring.

No aggregate SDOH quality score.

Checks should say exactly what passed or failed.

## Structural checks

- Bundle preflight passes.
- exactly one Patient;
- exactly one Questionnaire;
- exactly one QuestionnaireResponse;
- subject resolves;
- QR points to correct Questionnaire canonical.

## Questionnaire checks

- expected LOINC question codes exist;
- expected standardized answer options exist;
- HVS derived question exists as computed/read-only semantics;
- PRAPARE subset is exactly the frozen v0.1 set.

## Response checks

- supplied coded answers belong to allowed answer sets;
- multiselect cardinality preserved;
- explicit declines remain `asked-declined`;
- corrupt/unrecognized codes fail visibly;
- unanswered does not become a coded negative answer.

## Materialization checks

For each answer:

```text
QuestionnaireResponse value
        ==
Observation value
```

including:

- code;
- coding system;
- SDOH domain;
- Patient;
- time;
- absent reason.

## HVS checks

- Often/Sometimes logic produces expected risk result;
- both negative responses produce expected non-risk result;
- insufficient source answers do not produce a fake risk result.

## Interpretation checks

- positive-risk answer produces `POS` only when appropriate;
- neutral/non-risk response does not automatically produce `NEG`;
- declined response produces no interpretation.

---

# 17. Artifact Set

Reuse the Caregiver pattern.

Outputs:

```text
sdoh_baseline_questionnaire_v0.1.json

sdoh_questionnaire_response.json

sdoh_baseline_bundle.json

sdoh_baseline_oru_r01.hl7

sdoh_quality_report.json

sdoh_bundle_cleanup.json
```

Plus:

```text
sdoh_baseline_phase1_artifacts.zip
```

UI tabs:

```text
Questionnaire

QuestionnaireResponse

FHIR Bundle

HL7 v2

PIQITT-style checks
```

---

# 18. Public Module

Add:

```text
connectathon/gravity_sdoh.py
```

Same purpose as `gravity_caregiver.py`:

small public API exposing the stable Phase 1 functions without coupling callers to implementation layout.

Approximately:

```text
build_questionnaire
build_questionnaire_response
extract_sdoh_resources
build_submission_bundle
build_sdoh_oru
sdoh_quality_gate
build_artifact_files
build_artifact_zip
```

Reuse shared storage and generic response helpers rather than re-exporting duplicated copies.

---

# 19. Tests

Add:

```text
tests/test_gravity_sdoh.py

tests/test_gravity_sdoh_streamlit.py

tests/test_gravity_sdoh_hl7v2.py
```

Minimum test cases:

1. Questionnaire is valid FHIR-shaped Questionnaire.
2. Questionnaire has the frozen HVS + PRAPARE v0.1 question set.
3. Standard question LOINC codes are preserved.
4. Standard answer codes are preserved.
5. Happy-path QuestionnaireResponse is generated.
6. Explicit decline becomes `asked-declined`.
7. Declined answer does not become a negative answer.
8. Coded `Don't know/refused` remains distinct from Decline.
9. Multi-answer resource-needs question preserves all selected answers.
10. HVS positive source response produces at-risk result.
11. HVS non-risk source responses produce non-risk result.
12. Incomplete HVS does not invent a derived risk result.
13. Each standardized answer materializes as the expected Observation.
14. Observation contains `survey` + `sdoh` + appropriate domain.
15. Positive interpretation appears only where justified.
16. Non-risk answer does not invent `NEG`.
17. Declined item materializes with `dataAbsentReason`.
18. QuestionnaireResponse → Observation semantic equality survives.
19. Bundle references resolve.
20. Generic DuckDB questionnaire persistence works unchanged.
21. Artifact ZIP contains complete artifact set.
22. HL7 ORU preserves coded question/answer semantics.
23. Streamlit page imports/renders without requiring IRIS or internet.

---

# 20. Documentation

Create this plan as:

```text
docs/gravity/
    SDOH_BASELINE_PHASE_1_PLAN_v0.1_2026-09-24.md
```

After implementation:

```text
SDOH_BASELINE_PHASE_1_BUILD_HISTORY_v0.1_2026-09-24.md

SDOH_BASELINE_PHASE_1_BUILD_ANALYSIS_v0.1_2026-09-24.md
```

Build history should record:

- files added;
- shared code extracted;
- terminology decisions;
- tests;
- deviations from plan;
- bugs/corrections discovered during implementation.

Build analysis should specifically compare:

```text
Caregiver Baseline
vs.
SDOH Baseline
```

and inventory how much infrastructure was reused.

That comparison is useful evidence for whether the questionnaire architecture is actually becoming reusable rather than merely duplicated.

---

# 21. Build Order

## Step 1 — Freeze terminology

Before UI work:

- verify exact question text;
- verify LOINC question codes;
- verify answer codes;
- verify Gravity SDOH domain codes;
- verify HVS risk rules.

Create the terminology/question registry first.

No guessing.

## Step 2 — Questionnaire

Implement:

```text
gravity_sdoh_questionnaire.py
```

Test the complete static Questionnaire independently.

## Step 3 — QuestionnaireResponse

Implement capture for:

- single coded response;
- multiple coded responses;
- declined;
- unanswered.

## Step 4 — HVS derivation

Implement and test risk derivation independently.

## Step 5 — FHIR extraction

Materialize Gravity screening-response Observations.

Test:

```text
response → observation
```

before touching Streamlit.

## Step 6 — Bundle

Attach Patient + Questionnaire + QuestionnaireResponse + Observations using existing normalization.

## Step 7 — Quality gate

Implement structural and semantic-survival checks.

## Step 8 — HL7 v2 shared seam

Extract minimal reusable QR → OBX mechanics from the Caregiver implementation.

Confirm existing Caregiver behavior still passes its tests.

Then add SDOH ORU output.

## Step 9 — Streamlit page

Clone the **shape**, not the code wholesale, from Caregiver Health.

Wire the already-tested backend into the page.

## Step 10 — Persistence and artifacts

Reuse current generic questionnaire storage and ZIP mechanics.

## Step 11 — Full regression

Run:

```text
existing Caregiver tests

new SDOH tests

Connectathon/FHIR control tests affected by shared HL7 changes
```

No SDOH feature is worth breaking the Caregiver baseline.

---

# 22. Explicit Non-Goals

Phase 1 does **not** include:

- complete PRAPARE;
- complete Gravity terminology universe;
- AHC HRSN;
- automatic Condition creation;
- automatic referrals;
- ServiceRequest generation;
- Goal creation;
- intervention tracking;
- Z-code inference;
- AI interpretation;
- scoring beyond canonical HVS derivation;
- longitudinal SDOH tracking;
- dashboards;
- risk prediction;
- IRIS round trip as a blocker;
- external terminology API dependency;
- generalized universal questionnaire engine.

Most importantly:

> Do not turn a six-question PRAPARE subset into an excuse to write a form-builder platform.

---

# 23. Phase 1 Definition of Done

A user can open MediLacra and:

```text
select/generate Patient

complete Hunger Vital Sign

complete basic PRAPARE questions

decline any individual question

submit
```

and inspect:

```text
standardized Questionnaire

QuestionnaireResponse

Gravity-style SDOH screening Observations

derived Hunger Vital Sign risk when computable

FHIR Bundle

HL7 v2 ORU^R01

quality / semantic-survival report

persisted DuckDB response
```

A deliberately ugly case must demonstrate:

```text
declined ≠ negative

unanswered ≠ negative

don't know/refused ≠ decline

screening response ≠ diagnosis

positive screening ≠ automatic Condition

missing HVS answer ≠ invented risk result

one question can belong to multiple SDOH domains

coded meaning survives FHIR and HL7 transformation
```

When those properties hold and the existing Caregiver tests remain green:

**stop. Phase 1 exists.**

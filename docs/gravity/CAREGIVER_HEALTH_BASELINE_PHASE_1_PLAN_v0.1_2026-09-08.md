# MediLacra Gravity Caregiver Health Baseline — Phase 1 Build Plan

**Project:** MediLacra / Gravity Project extension  
**Feature:** Caregiver Health Baseline Questionnaire  
**Version:** 0.1  
**Plan date:** September 8, 2026  
**Branch:** `feature/gravity-caregiver-baseline-v0.1`  
**Branch base:** `connectathon/piqi-43`  
**Status:** ACTIVE — PHASE 1 BASELINE BUILD  
**Phase 2 dependency:** Local IRIS FHIR server on the new development machine

---

## 1. Purpose

Add one deliberately boring, standards-based caregiver health questionnaire to MediLacra and prove that the captured facts remain recognizable as they move through the existing MediLacra / FHIR / PIQITT stack.

The project does **not** invent a questionnaire framework. Gravity / SDC already provides the questionnaire capture and extraction machinery. The work here is to materialize a small caregiver-health use case with standard FHIR resources and reuse existing MediLacra and PIQITT infrastructure wherever possible.

The Phase 1 experiment is:

```text
synthetic MediLacra Patient
        ↓
Streamlit caregiver questionnaire
        ↓
FHIR QuestionnaireResponse
        ↓
structured local persistence
        ↓
clinical extraction
        ↓
Observation / MedicationStatement
        ↓
FHIR collection Bundle
        ↓
PIQITT-style local plausibility + conformance checks
        ↓
inspect whether the facts still mean what was entered
```

Phase 2 adds IRIS persistence and round-trip comparison after IRIS is running locally.

### Core design sentence

> Use Gravity to capture the answers, existing clinical FHIR resources to represent the facts, and PIQITT to make sure reality did not turn into bullshit on the way through.

---

## 2. Why caregiver health belongs here

Caregiving is a clinically relevant status and relationship. The caregiver can also be a patient in their own right, with health facts that belong to them rather than to the person receiving care.

For this baseline:

- the caregiver is an existing synthetic MediLacra `Patient`;
- the questionnaire is about the caregiver's own health;
- sleep, pain, PHQ-2, heart rate, and medication use therefore have the caregiver Patient as subject;
- the caregiver → care-recipient relationship is important, but does **not** block Phase 1;
- a future phase can materialize that relationship using existing FHIR relationship machinery rather than inventing a `caregiver_patient_id` ontology.

The questionnaire should prove the capture/materialization path before the relationship graph gets fancy.

---

## 3. Reuse-first inventory

This branch starts from `connectathon/piqi-43` specifically because most of the machinery already exists.

### Reuse directly

- existing synthetic `Patient` dataclass and `gen_patient()`;
- existing Streamlit multipage app pattern in `pages/`;
- existing DuckDB connection utilities in `utils/db.py`;
- existing FHIR representation style in `fhir/fhir_convert_backend.py` (standard FHIR JSON resource dictionaries, not invented healthcare dataclasses);
- existing Connectathon bundle normalization in `connectathon/fhir_control.py`;
- existing structural and information-quality preflight patterns in `connectathon/preflight.py`;
- existing PIQITT bridge conventions where they apply;
- existing test organization in `tests/`.

### Do not create

- `CaregiverAssessment` class;
- `AssessmentResponse` class;
- `MedicationResponse` class;
- a custom questionnaire schema language;
- a new clinical ontology;
- a generic rules engine;
- a new FHIR server adapter in Phase 1;
- a caregiver wellness score.

The standard resources are the domain objects:

```text
Patient
Questionnaire
QuestionnaireResponse
Observation
MedicationStatement
Bundle
```

Standard FHIR datatypes such as `Quantity`, `Coding`, `CodeableConcept`, `Reference`, and extensions carry the details.

---

## 4. Baseline questionnaire

**Name:** MediLacra Caregiver Health Baseline  
**Version:** 0.1  
**Instrument type:** local mixed instrument containing standard and local questions  
**UI:** Streamlit  
**Response subject:** existing synthetic MediLacra Patient

No adaptive logic except showing medication details when medications are present. No scoring beyond the standard PHQ-2 sum.

### 4.1 Sleep

**Question:**

> About how many hours did you sleep in the past 24 hours?

Baseline representation:

```text
FHIR answer: Quantity
value: decimal
unit: h
system: UCUM
```

This question remains **locally coded** in v0.1. Do not force a merely-similar standardized sleep question onto it.

### 4.2 Pain

**Question:**

> On a scale from 0 to 10, where 0 means no pain and 10 means the worst pain imaginable, how would you rate your pain right now?

Baseline representation:

```text
LOINC: 72514-3
answer: integer
range: 0..10
```

**Deferred research note:** revisit the pain measure later and find something less crappy/confusing for people with chronic pain, likely involving function/interference rather than intensity alone.

### 4.3 PHQ-2

Use the standard two PHQ-2 questions and standard frequency choices.

```text
44250-9  Little interest or pleasure in doing things
44255-8  Feeling down, depressed, or hopeless
55757-9  PHQ-2 total score
```

Frequency answers:

```text
0  Not at all
1  Several days
2  More than half the days
3  Nearly every day
```

Derive the PHQ-2 total only when both component answers are present and valid.

Do **not** infer a diagnosis in this baseline.

### 4.4 Heart rate

**Question:**

> What is your current heart rate?

Baseline representation:

```text
LOINC: 8867-4
FHIR answer: Quantity
unit: /min
system: UCUM
```

Validation starts with representational plausibility, not clinical judgment.

Examples:

```text
82 /min      plausible representation
35 /min      plausible representation, possibly clinically important
190 /min     plausible representation, possibly clinically important
-12 /min     invalid
"potato"    corrupt/unparseable
```

Abnormal is not the same thing as invalid.

### 4.5 Medication reconciliation

First question:

> Are you currently taking any medications?

UI states:

```text
Yes
No
Decline
```

If yes, allow repeating medication rows:

```text
Medication
Dose
Dose unit
Route
Frequency
```

Phase 1 intentionally omits:

- indication;
- prescriber;
- pharmacy;
- dispense history;
- start/end dates;
- adherence scoring;
- interaction checking.

Medication normalization should preserve entered text. Use RxNorm coding when a code is supplied or otherwise available; do not invent a code for an uncoded medication string.

Downstream clinical representation is FHIR R4 `MedicationStatement`, because this baseline represents an assertion about what the person reports taking, not a prescription order.

---

## 5. Decline and missingness

Every ordinary question gets an explicit **Decline** button/control in Streamlit.

Medication reconciliation gets a section-level decline on the initial medication-status question.

Missingness must not collapse into one generic null.

At minimum distinguish:

| Situation | Baseline semantics |
|---|---|
| answered | actual `value[x]` |
| explicitly declined | `asked-declined` |
| explicitly unknown | `asked-unknown` when exposed later |
| conditionally skipped | `not-asked` if materialized |
| simply unanswered | no answer |
| corrupt/unparseable input | preserve raw input when possible + `error` |

FHIR `DataAbsentReason` is the canonical vocabulary. The implementation should use the standard data-absent-reason extension rather than creating a MediLacra-specific null-flavor code set.

Core invariant:

```text
DECLINED ≠ UNKNOWN ≠ UNANSWERED ≠ CORRUPT ≠ ZERO
```

---

## 6. Grain and cardinality

### QuestionnaireResponse grain

> One `QuestionnaireResponse` represents one completion of one questionnaire for one Patient at one assessment time.

```text
Patient
  1 ───────── N QuestionnaireResponse

Questionnaire
  1 ───────── N QuestionnaireResponse

QuestionnaireResponse
  1 ───────── N item

item
  0 ───────── N answer

medication group
  0 ───────── N medication entry
```

These are standard FHIR structures/cardinalities. Do not create parallel custom assessment entities merely to restate them.

---

## 7. Persistence

The user-facing event is the QuestionnaireResponse and that original response must survive extraction.

Phase 1 persistence should use the existing MediLacra DuckDB infrastructure.

Store:

- response id;
- questionnaire canonical/version;
- patient id;
- authored timestamp;
- response status;
- response items as nested structured data;
- original FHIR QuestionnaireResponse JSON for exact round-trip/provenance inspection;
- derived FHIR resource JSON as needed for inspection.

Prefer DuckDB nested `STRUCT` / list storage for response-item projections while retaining the complete FHIR JSON representation as the authoritative exchange artifact. If DuckDB driver behavior makes nested insertion unnecessarily brittle, preserve the FHIR JSON first and document the fallback rather than blocking the baseline.

Persistence is not an excuse to invent another healthcare model.

---

## 8. FHIR materialization

### 8.1 Questionnaire

Create one versioned FHIR `Questionnaire` that acts as the actual questionnaire definition. Do not create a separate local questionnaire DSL.

The Questionnaire contains:

- metadata;
- canonical URL;
- version `0.1`;
- item hierarchy;
- item types;
- standardized codes where exact mappings exist;
- local codes where they do not;
- standard answer options;
- repeating medication group.

### 8.2 QuestionnaireResponse

Streamlit submission produces one FHIR `QuestionnaireResponse` referencing:

- the versioned Questionnaire;
- the synthetic Patient subject;
- authored timestamp;
- response items and answers;
- standard absence semantics where needed.

The QuestionnaireResponse is retained after extraction. It is evidence of what was actually entered.

### 8.3 Clinical extraction

Materialize useful clinical facts:

```text
QuestionnaireResponse
       │
       ├── sleep ─────────→ Observation
       ├── pain ──────────→ Observation
       ├── PHQ q1 ────────→ Observation
       ├── PHQ q2 ────────→ Observation
       ├── PHQ total ─────→ Observation
       ├── heart rate ────→ Observation
       └── meds ──────────→ MedicationStatement(s)
```

The first implementation may use a small deterministic transformer. It must be explicit and testable. A generalized StructureMap engine is not required to prove the baseline.

### 8.4 Bundle

Create a self-contained FHIR collection Bundle containing the Patient, Questionnaire, QuestionnaireResponse, extracted Observations, and MedicationStatements.

Reuse `connectathon.fhir_control.prepare_control_bundle()` for stable fullUrls/reference rewriting and existing Connectathon bundle shape rather than duplicating that logic.

---

## 9. PIQITT / quality checks — plausibility before metrics

Phase 1 does **not** begin with aggregate scores.

### Gate 1 — coherent record

Check that:

- Patient exists;
- Questionnaire exists;
- QuestionnaireResponse references the expected Patient and Questionnaire;
- response has an authored timestamp;
- extracted resources reference the same subject.

### Gate 2 — basic plausibility

Examples:

```text
sleep = 6.5 h                  PASS
pain = 4                       PASS
PHQ response = Several days    PASS
heart rate = 82 /min           PASS
med = Lisinopril 10 mg         PASS

sleep = -8 h                   FAIL
pain = 47                      FAIL
PHQ response = Wednesday       FAIL
heart rate = potato            FAIL / corrupt
negative medication dose       FAIL
```

Do not fail clinically unusual but representable values merely because they are unusual.

### Gate 3 — recognizable materialization

Inspect whether:

- heart-rate Observation still contains the entered value/unit;
- pain Observation still contains the entered numeric score;
- PHQ component answers remain attached to the correct questions;
- PHQ total equals the component sum only when both components exist;
- MedicationStatement still represents the entered medication/dose/route/frequency;
- declined answers remain declined rather than becoming zero or false.

### Gate 4 — basic FHIR/terminology conformance

Reuse existing local preflight patterns for:

- FHIR resource shape;
- reference resolution;
- LOINC system/code presence;
- UCUM system/code presence;
- RxNorm coding when supplied;
- required fields.

### Gate 5 — semantic survival

Example:

```text
Streamlit:          82 beats/minute
QuestionnaireResponse: 82 /min
Observation:        82 /min

Result: PASS
```

No synthetic fidelity percentage is needed yet. A human-readable PASS/FAIL with evidence is enough.

---

## 10. Phase 1 code surface

The intended implementation is small.

### New module

`connectathon/gravity_caregiver.py`

Responsibilities:

- constants and canonical terminology;
- build the standard FHIR Questionnaire;
- build QuestionnaireResponse from UI state;
- create standard data-absent-reason extensions;
- extract Observations and MedicationStatements;
- build a self-contained Bundle using existing bundle normalization;
- run caregiver-specific plausibility/semantic-preservation checks;
- persist/load QuestionnaireResponses using existing DuckDB utilities.

### New Streamlit page

`pages/10_Gravity_Caregiver_Health.py`

Responsibilities:

- choose or generate a synthetic Patient;
- render the baseline Questionnaire;
- provide per-question Decline controls;
- collect repeatable medication rows;
- submit;
- persist;
- show QuestionnaireResponse;
- show extracted resources/Bundle;
- show local plausibility/conformance results.

### New tests

`tests/test_gravity_caregiver.py`

Cover at least:

1. Questionnaire uses expected standard resource/item structure.
2. Happy-path QuestionnaireResponse.
3. Declined value remains `asked-declined`.
4. PHQ-2 total only exists when both questions are answered.
5. Heart rate materializes as LOINC `8867-4` + UCUM `/min`.
6. Pain stays within the expected 0..10 representation.
7. MedicationStatement preserves medication/dose/route/frequency.
8. Invalid/corrupt values fail plausibility without being silently normalized into legitimate data.
9. Bundle references resolve after existing Connectathon normalization.
10. DuckDB persistence preserves the response and structured item projection.

---

## 11. Build order

1. Create this plan and freeze the v0.1 boundary.
2. Build the FHIR Questionnaire in code.
3. Build QuestionnaireResponse helpers and absence handling.
4. Build extraction into Observation / MedicationStatement.
5. Reuse existing collection-Bundle normalization.
6. Add caregiver-specific plausibility/semantic checks.
7. Add DuckDB persistence.
8. Add Streamlit page.
9. Add tests.
10. Exercise one happy case and one ugly missing/corrupt case.

---

## 12. Phase 1 definition of done

A developer can run MediLacra, open the caregiver-health page, select/generate a synthetic Patient, enter something boring such as:

```text
Sleep:       6.5 h
Pain:        4
PHQ-2:       1 + 0
Heart rate:  82 /min
Medication:  Lisinopril 10 mg oral daily
```

and inspect:

```text
FHIR Questionnaire
FHIR QuestionnaireResponse
persisted response
extracted Observations
MedicationStatement(s)
FHIR Bundle
local plausibility/conformance report
```

Then a deliberately ugly case can demonstrate that:

```text
declined ≠ unanswered
corrupt ≠ zero
missing PHQ component ≠ valid PHQ total
no medications ≠ unknown medication list
```

When both paths work, **stop**. Phase 1 baseline exists.

---

## 13. Phase 2 — deferred IRIS round trip

Phase 2 begins only after IRIS is running on the new machine.

```text
Phase 1 Bundle
      ↓
POST to IRIS FHIR endpoint
      ↓
retrieve resources
      ↓
PIQITT / semantic comparison
```

Phase 2 asks:

> Did the FHIR server preserve the same clinical representation we sent it?

IRIS setup must not block Phase 1.

---

## 14. Explicitly deferred

- richer chronic-pain instrument;
- detailed sleep instrument;
- vague global self-rated health measure;
- caregiver burden/risk score;
- intervention recommendations;
- Monarch interpretation/scoring;
- longitudinal dashboards;
- wearables / automatic heart-rate capture;
- medication adherence;
- medication interaction checks;
- prescriber/pharmacy/dispense history;
- sophisticated caregiver → care-recipient relationship graph;
- referral workflow / ServiceRequest / Task;
- CBO integration;
- consent workflow;
- adaptive questionnaires;
- AI interpretation;
- generalized StructureMap engine;
- generalized Reality Model architecture.

---

## 15. Glossary

### Caregiver
A person providing meaningful care to another person. In this baseline the caregiver is also represented as a synthetic FHIR Patient when recording their own health facts.

### Care recipient
The person receiving care from the caregiver. Important context, but not required to execute Phase 1.

### Patient
FHIR resource representing the subject whose health information is being recorded.

### Subject
The person a clinical resource is about. Here, caregiver sleep/pain/PHQ/heart-rate/medication resources point to the caregiver Patient.

### RelatedPerson
FHIR resource for a person related to or involved in another Patient's care. Candidate future representation for caregiver relationship context; not a Phase 1 blocker.

### Questionnaire
FHIR resource defining a form/assessment: items, types, answer options, codes, hierarchy, and metadata.

### QuestionnaireResponse
FHIR resource containing one completion/response to a Questionnaire.

### SDC
Structured Data Capture. FHIR implementation-guide machinery for richer, computable Questionnaire and QuestionnaireResponse behavior.

### Gravity Project / SDOH Clinical Care
Standards work for interoperable SDOH assessment, clinical representation, and workflow. The project already uses Questionnaire / QuestionnaireResponse / Observation patterns rather than requiring MediLacra to invent them.

### Mixed instrument
A local questionnaire composed of both standardized questions and locally defined questions. Exact standard codes are retained where they truly match; local codes are used where they do not.

### Item
One Questionnaire question or group.

### linkId
Identifier connecting a Questionnaire item with the corresponding QuestionnaireResponse item.

### Observation
FHIR resource representing a measured, reported, calculated, or otherwise observed fact.

### MedicationStatement
FHIR R4 resource representing an assertion that a patient is/was taking a medication. Appropriate to this baseline's self-reported medication reconciliation.

### Quantity
FHIR datatype combining a numeric value with units.

### Coding
FHIR datatype carrying terminology system + code + optional display.

### CodeableConcept
FHIR datatype carrying one or more Codings plus optional human-readable text.

### LOINC
Standard terminology used here for pain, PHQ-2, and heart rate where exact concepts exist.

### RxNorm
U.S. medication terminology. Use when a medication code is actually available; preserve entered medication text regardless.

### UCUM
Unified Code for Units of Measure. Used for computable units such as `h`, `mg`, and `/min`.

### DataAbsentReason
Standard FHIR vocabulary describing why an expected value is missing, including `asked-declined`, `asked-unknown`, `not-asked`, and `error`.

### Null flavor
General semantic distinction among different kinds of missingness. This implementation uses FHIR DataAbsentReason rather than inventing a parallel code set.

### Grain
What one record represents. Here: one QuestionnaireResponse = one questionnaire completion for one Patient at one assessment time.

### Cardinality
How many related objects may occur, e.g. one Questionnaire to many QuestionnaireResponses and zero-to-many medication entries within one response.

### Provenance
Information that allows an artifact to be traced back to its source. Retaining the original QuestionnaireResponse preserves what the person actually entered before clinical extraction.

### Materialization
Turning one explicit representation into another, e.g. a QuestionnaireResponse heart-rate answer into a Heart Rate Observation.

### Extraction
The specific materialization from QuestionnaireResponse answers into clinical FHIR resources.

### Plausibility
Whether a record is internally coherent and representable as something that could actually have happened. Plausibility comes before scoring.

### Conformance
Whether an artifact follows the structural and terminology rules of the relevant FHIR/profile contract.

### Semantic preservation
Whether the meaning survives transformation, e.g. `82 beats/minute` remains `82 /min` on the same Patient after extraction.

### PIQITT
The existing test/translation tooling used to inspect whether meaning, relationships, and representational quality survive transformation.

### Bundle
FHIR resource used to package multiple resources. Phase 1 uses a self-contained collection Bundle for local inspection/testing.

### Baseline
The smallest coherent implementation against which later sophistication can be compared.

---

## 16. Provenance / Gravity workgroup lineage

This plan follows earlier Gravity Project workgroup notes rather than treating the feature as greenfield.

Relevant notes include:

### October 15, 2025 — Technical Public Call / Clinical Care

- protective-factor instruments were discussed as standardized instruments that can be assessed, documented, monitored, and revisited over time;
- the captured slides explicitly aligned protective-factor instruments with `Questionnaire`, `QuestionnaireResponse`, and `Observation`;
- the workgroup distinguished instruments from interventions;
- the notes identified the open representational question of where a positive/protective finding belongs in FHIR.

This branch does not attempt to solve that protective-factor ontology question. It reuses the already-established questionnaire machinery.

### October 29, 2025 — Enhanced Referral / Personal Characteristics

- enhanced referral work included additional assessment/questionnaire context;
- push was the primary workflow focus;
- consent/privacy and sensitive-data segmentation were active concerns;
- personal-characteristic work emphasized alignment with US Core and the ability to segment/hide sensitive information.

This reinforces the Phase 1 decision to preserve explicit missingness/decline semantics and source response artifacts instead of flattening them.

### November 12, 2025 — Occupation / Personal Characteristics

- occupational data and personal characteristics were being aligned with US Core / USCDI;
- data segmentation remained relevant;
- Gravity needed terminology SMEs and SDOH use cases.

### Existing design question from the notes

> “Gravity has this built in.”

That is the implementation rule for this branch: reuse the agreed questionnaire and FHIR machinery, and spend MediLacra effort on the synthetic reality, materialization, and quality experiment.

---

## 17. Change policy for v0.1

Before adding anything to Phase 1, ask:

> Does this help one synthetic caregiver complete the baseline questionnaire, preserve the response, materialize standard clinical FHIR resources, or demonstrate that the facts survived?

If the answer is no, defer it.

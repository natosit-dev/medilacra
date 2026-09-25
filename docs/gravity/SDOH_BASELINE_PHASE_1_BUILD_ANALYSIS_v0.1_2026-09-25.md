# MediLacra — SDOH Baseline Phase 1 Build Analysis

**Document type:** Build analysis / reuse analysis  
**Project:** MediLacra — Gravity SDOH Baseline  
**Phase:** Phase 1  
**Version:** v0.1  
**Date:** 2026-09-25  
**Branch:** `feature/gravity-sdoh-baseline-v0.1`  
**Reference implementation:** Gravity Caregiver Health Baseline  

---

## 1. Executive finding

The SDOH page validated the architectural claim behind the Caregiver build:

> the expensive part is not rendering another questionnaire; it is preserving the semantics of the answers across representations.

Very little application infrastructure had to be invented.

The Caregiver work had already materialized a reusable path for:

```text
Patient
  ↓
Questionnaire interaction
  ↓
QuestionnaireResponse
  ↓
FHIR materialization
  ↓
Bundle normalization
  ↓
HL7 v2 projection
  ↓
quality checks
  ↓
DuckDB persistence
  ↓
artifact inspection/download
```

The SDOH build reused that path while changing the domain-specific semantics.

That distinction matters. The second questionnaire did not prove that MediLacra needs a universal form-builder framework. It proved that several existing layers are already generic enough.

---

## 2. What was actually generic

### Patient selection and generation

No SDOH-specific person or Patient object was needed.

The page uses the existing synthetic Patient population and the same Patient generation/persistence flow as Caregiver Health.

### Questionnaire persistence

`gravity_storage.py` was reusable unchanged.

This is the strongest evidence that the earlier architecture landed at the correct grain.

The table already stores:

- questionnaire canonical URL/version;
- Patient identity;
- authored timestamp;
- response status;
- nested item path;
- linkId;
- answer type;
- coded answer;
- numeric/text value;
- unit;
- absent reason;
- raw UI JSON;
- complete QuestionnaireResponse JSON;
- resulting Bundle JSON.

The SDOH page therefore required no new database schema.

### Response traversal

Existing helpers for nested QuestionnaireResponse items remained sufficient.

The same traversal handles:

- Caregiver groups;
- SDOH groups;
- repeating answers;
- explicit data-absent reasons.

### Bundle normalization

The existing Connectathon FHIR control path remained sufficient.

The SDOH build did not create a competing policy for:

- resource IDs;
- fullUrl values;
- reference rewriting;
- self-contained collection Bundles.

### Page interaction grammar

The Caregiver page already established a usable interaction grammar:

```text
question                           decline
[control....................]      [Decline]
```

The SDOH page reuses that grammar rather than introducing a new UI concept.

---

## 3. What correctly remained domain-specific

The second questionnaire also demonstrates what should **not** be prematurely generalized.

### Terminology registry

The concrete question codes, answer sets, repeat cardinality, source provenance, and domain mappings belong to the SDOH instrument.

They should not be pushed into a generic clinical-form abstraction just because they happen to be metadata.

### Derived logic

Hunger Vital Sign derivation is an instrument rule:

```text
Often / Sometimes on either source question
    → At risk

Never + Never
    → No risk

otherwise
    → insufficient information
```

That logic belongs next to the instrument.

It should not become a generic scoring engine until another use case demonstrates a common scoring ontology.

### Observation interpretation

The decision to emit `POS` only where the HVS semantics justify it is domain-specific.

A general QuestionnaireResponse engine should not infer clinical/social interpretation from arbitrary answer codes.

### Domain categories

Mapping a question to:

- food-insecurity;
- housing-instability;
- homelessness;
- material-hardship;
- transportation-insecurity;
- social-connection;
- stress;

is SDOH semantics, not generic questionnaire plumbing.

---

## 4. Important difference from Caregiver Health

The SDOH build exposed a meaningful semantic difference in missingness materialization.

### Caregiver behavior

For several caregiver metrics, an unanswered or declined item does not produce a downstream Observation.

The QuestionnaireResponse remains the evidence that the item was declined.

### SDOH behavior

For standardized SDOH screening, preserving the fact that a specific standardized question was asked and declined is itself useful.

Phase 1 therefore permits:

```text
Observation.code = original LOINC question
Observation.dataAbsentReason = asked-declined
Observation.category = survey + sdoh + domain
no value
no interpretation
```

This is not inconsistency.

It demonstrates why a supposedly universal extraction layer would have been the wrong abstraction: different clinical interaction types can legitimately materialize missingness differently.

---

## 5. Repeating-answer behavior was the useful stress test

The Caregiver page already had repeating medication groups, but the SDOH build introduced a different kind of repetition:

> one standardized question with multiple coded answers.

PRAPARE material needs and transportation therefore test whether MediLacra can preserve:

```text
one question
    ↓
multiple coded responses
    ↓
multiple queryable screening facts
```

Phase 1 keeps each selected coded answer separately in:

- QuestionnaireResponse;
- DuckDB STRUCT projection;
- screening Observations;
- HL7 v2 OBX segments.

This is a stronger semantic-preservation test than simply adding more scalar fields.

---

## 6. Coded refusal versus interaction refusal

One of the most useful properties of the build is that it preserves two superficially similar but ontologically different events.

### Instrument-coded response

Example:

```text
Don't know / refused
```

This is a supplied coded answer defined by the source instrument.

### MediLacra Decline

```text
DataAbsentReason = asked-declined
```

This means the interaction produced no answer because the person explicitly declined the item.

Collapsing them would destroy information.

The UI, QuestionnaireResponse, FHIR Observations, persistence, and tests preserve the distinction.

---

## 7. HVS risk proves the direction of derivation

The HVS result is not collected as another editable field.

The direction is:

```text
human answers
      ↓
QuestionnaireResponse source items
      ↓
deterministic HVS rule
      ↓
read-only derived response
      ↓
screening Observation
```

This preserves provenance and prevents the UI from pretending a computed assessment result is a third independent human statement.

That pattern is likely reusable later, but the implementation intentionally does not generalize it yet.

---

## 8. The HL7 decision

The original plan proposed extracting a generic QuestionnaireResponse → OBX projector.

The implementation stopped one level earlier.

It reused the existing Caregiver HL7 building primitives and added an SDOH-specific coded-answer iterator.

Current shape:

```text
existing MSH/PID/OBR/OBX primitives
             ↑
      ┌──────┴──────┐
      │             │
Caregiver logic   SDOH logic
```

This creates some coupling to the existing module's low-level helpers, but it avoids designing a generalized questionnaire-to-v2 model from only two examples.

That trade is acceptable for v0.1.

A third materially different questionnaire would provide better evidence for where the stable HL7 abstraction boundary actually belongs.

---

## 9. Infrastructure versus feature code

Compared with the Caregiver branch, the SDOH branch adds new domain modules, page code, tests, CI, and documentation but does not modify the underlying Patient, DuckDB questionnaire storage, or Bundle normalization machinery.

That is a useful architectural result.

The system is beginning to separate into:

```text
GENERIC INFRASTRUCTURE

Patient
questionnaire persistence
response traversal
Bundle normalization
FHIR identity/reference handling
low-level HL7 construction
artifact conventions


INSTRUMENT-SPECIFIC SEMANTICS

question definitions
answer value sets
repeat cardinality
derived rules
domain categories
interpretation rules
quality assertions
page composition
```

That split emerged from reuse rather than being imposed upfront.

---

## 10. What the tests establish

The combined test run reached:

**38 passed, 1 warning**

That run includes the SDOH tests and the existing Caregiver regression suite.

The evidence therefore establishes that, within the covered local test surface:

- the SDOH page can be added without breaking the Caregiver baseline;
- standard coded answers survive into downstream representations;
- repeating coded answers remain distinct;
- explicit decline survives;
- coded refusal is not collapsed into decline;
- HVS derived risk follows the implemented source-answer rules;
- screening categories are retained;
- `NEG` is not invented;
- downstream diagnosis/referral resources are not invented;
- generic questionnaire persistence handles the new instrument.

It does **not** establish external server conformance against every Gravity profile constraint or an IRIS round trip.

Those remain separate experiments.

---

## 11. Architectural conclusion

The useful result is not merely that MediLacra now has an SDOH page.

It is that the second questionnaire required **reuse plus instrument semantics**, not another application stack.

The current evidence supports keeping this architecture:

```text
shared execution/persistence infrastructure
                +
thin instrument-specific semantic modules
```

rather than replacing it with:

```text
universal healthcare questionnaire framework
```

The latter would currently be an abstraction in search of evidence.

Phase 1 should remain boring.

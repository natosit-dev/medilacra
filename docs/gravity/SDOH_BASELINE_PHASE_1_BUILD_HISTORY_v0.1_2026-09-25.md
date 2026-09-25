# MediLacra — SDOH Baseline Phase 1 Build History

**Document type:** Build history / decision log  
**Project:** MediLacra — Gravity SDOH Baseline  
**Phase:** Phase 1  
**Version:** v0.1  
**Build date:** 2026-09-25  
**Branch:** `feature/gravity-sdoh-baseline-v0.1`  
**Base branch:** `feature/gravity-caregiver-baseline-v0.1`  
**Plan:** `docs/gravity/SDOH_BASELINE_PHASE_1_PLAN_v0.1_2026-09-24.md`  
**Final verification checkpoint before documentation:** **38 passed, 1 warning**  

---

## 1. Build objective

Add a new MediLacra SDOH page with the same operational shape as the existing Gravity Caregiver Health page while reusing the generic questionnaire, Patient, Bundle-normalization, persistence, artifact, and quality patterns already present.

The new baseline combines:

- complete Hunger Vital Sign capture and derived food-insecurity risk;
- a deliberately small PRAPARE subset covering housing, material needs, transportation, social connection, and stress;
- FHIR Questionnaire / QuestionnaireResponse;
- Gravity-style screening-response Observations;
- HL7 v2 ORU^R01 projection;
- DuckDB persistence;
- local semantic-survival checks;
- downloadable artifacts.

The overall Questionnaire remains MediLacra-owned. Standard questions and answers retain their standard LOINC identities.

---

## 2. Standards decisions frozen during implementation

The implementation was checked against the current Gravity SDOH Clinical Care IG before coding the instrument.

### Observation categories

The screening-response Observation carries:

- `survey` observation category;
- US Core `sdoh` category;
- the applicable Gravity SDOH domain category or categories.

The domain category supplements rather than replaces the required `survey` and `sdoh` categories.

### Interpretation

The baseline does not generate `NEG`.

`POS` is emitted only for Hunger Vital Sign source answers that explicitly indicate risk and for the derived `At risk` result.

A non-risk response is not promoted into a clinically established negative finding.

### Missingness

The implementation preserves distinctions among:

- unanswered;
- explicit MediLacra Decline;
- an instrument-provided coded refusal / nonresponse;
- a valid non-risk answer;
- corrupt/unrecognized input.

Explicit MediLacra Decline becomes `asked-declined`.

### Repeating questions

The PRAPARE material-needs and transportation questions are implemented as repeating coded questions. Multiple selected answers remain multiple QuestionnaireResponse answers and materialize as separate screening-response Observations.

### HVS derivation

The HVS risk item is read-only/computed.

- Either source question = Often true or Sometimes true → At risk.
- Both source questions = Never true → No risk.
- Insufficient source information → no invented risk result.

---

## 3. Files added

### Application

- `pages/11_Gravity_SDOH.py`

### SDOH modules

- `connectathon/gravity_sdoh_terminology.py`
- `connectathon/gravity_sdoh_questionnaire.py`
- `connectathon/gravity_sdoh_response.py`
- `connectathon/gravity_sdoh_materialize.py`
- `connectathon/gravity_sdoh_quality.py`
- `connectathon/gravity_sdoh_hl7v2.py`
- `connectathon/gravity_sdoh.py`

### Tests

- `tests/test_gravity_sdoh.py`
- `tests/test_gravity_sdoh_hl7v2.py`
- `tests/test_gravity_sdoh_streamlit.py`

### CI

- `.github/workflows/gravity-sdoh-smoke.yml`

### Documentation

- `docs/gravity/SDOH_BASELINE_PHASE_1_PLAN_v0.1_2026-09-24.md`
- this build history
- companion build analysis

---

## 4. Existing infrastructure reused unchanged

The build intentionally did **not** create replacements for working infrastructure.

Reused directly:

- existing MediLacra synthetic Patient generation;
- existing Patient DuckDB persistence;
- `connectathon.gravity_response` traversal / FHIR ID / Patient helpers;
- `connectathon.gravity_storage.py` generic questionnaire persistence;
- `connectathon.fhir_control.prepare_control_bundle()`;
- existing Bundle fullUrl/reference normalization;
- existing Caregiver HL7 segment-building primitives;
- existing Streamlit page interaction pattern;
- existing artifact ZIP pattern.

No `sdoh_questionnaire_responses` table was created.

The canonical stored assessment artifact remains the complete FHIR QuestionnaireResponse JSON, with the existing nested DuckDB STRUCT projection for queryability.

---

## 5. SDOH-specific behavior added

### Questionnaire composition

The local baseline contains:

- Hunger Vital Sign:
  - `88122-7`
  - `88123-5`
  - derived `88124-3`
- PRAPARE basics:
  - `71802-3`
  - `93033-9`
  - `93031-3`
  - `93030-5`
  - `93029-7`
  - `93038-8`

The complete form is not labeled PRAPARE.

### Screening Observations

Each captured standardized answer materializes with:

- original LOINC question identity;
- original coded answer;
- Patient;
- authored/effective time;
- QuestionnaireResponse provenance;
- Gravity screening-response profile;
- `survey`, `sdoh`, and domain categories.

Repeating answers produce distinct Observations rather than being flattened into one pseudo-value.

### Decline behavior

Unlike the original Caregiver extraction behavior, an explicitly declined SDOH question can still materialize an Observation carrying the question identity and `dataAbsentReason=asked-declined`.

This preserves the fact that the question was presented and declined without inventing a response.

### Downstream restraint

Phase 1 does not infer or generate:

- Condition;
- Goal;
- ServiceRequest;
- Procedure;
- diagnosis;
- referral;
- intervention.

A screening response remains a screening response.

---

## 6. HL7 v2 implementation decision

The plan anticipated extracting a generic QuestionnaireResponse → OBX projector.

During implementation, the smaller coherent move was to reuse the existing low-level Caregiver HL7 primitives for:

- MSH;
- PID;
- OBR;
- OBX;
- absent-reason OBX;
- timestamp handling.

`gravity_sdoh_hl7v2.py` supplies only the SDOH-specific question/answer iteration.

A new universal questionnaire projection framework was **not** introduced in Phase 1.

This is a deliberate deviation from the original plan: reuse was achieved without forcing a broader abstraction before a third concrete questionnaire proves the abstraction boundary.

---

## 7. Test coverage

The SDOH tests cover:

1. frozen HVS + PRAPARE basic question set;
2. read-only HVS risk item;
3. repeating PRAPARE question cardinality;
4. HVS at-risk derivation;
5. HVS no-risk derivation;
6. incomplete HVS does not invent risk;
7. coded refusal remains distinct from explicit Decline;
8. explicit Decline remains `asked-declined`;
9. multiselect answers survive independently;
10. Gravity screening categories survive;
11. HVS positive interpretation;
12. no invented `NEG`;
13. no invented Condition / Goal / ServiceRequest / Procedure;
14. invalid codes fail visibly;
15. generic DuckDB persistence;
16. complete downloadable artifact set;
17. HL7 v2 coded-answer preservation;
18. HL7 repeating-answer sub-identifiers;
19. HL7 explicit absent-reason preservation;
20. Streamlit render / decline / reset behavior.

The SDOH CI workflow also runs the existing Caregiver test suite as a regression gate.

---

## 8. CI history

The initial CI run exposed one implementation wiring error: the response module imported explicit HVS derivation constant names that the terminology module had initially exposed under shorter names.

The fix added the explicit aliases. No semantic rule changed.

After that fix:

**38 passed, 1 warning**

Two small cleanup commits then:

- replaced a dynamic response-traversal import with the existing shared `iter_response_items` helper;
- removed redundant HVS source-list initialization.

After cleanup:

**38 passed, 1 warning in 3.25s**

The remaining warning is unrelated to the SDOH feature.

---

## 9. Phase 1 definition-of-done result

The implemented page can:

- select or generate a synthetic Patient;
- complete Hunger Vital Sign;
- complete the PRAPARE basic subset;
- explicitly decline any human-entered question;
- preserve coded instrument refusal separately from Decline;
- compute HVS risk when supported;
- generate Questionnaire and QuestionnaireResponse artifacts;
- materialize Gravity-style screening Observations;
- project the same responses into HL7 v2 ORU^R01;
- normalize a self-contained FHIR Bundle;
- persist the response through the existing generic questionnaire store;
- run inspectable semantic/conformance checks;
- download the complete artifact set;
- show recent persisted SDOH QuestionnaireResponses.

Phase 1 exists. The next work, if any, should start from demonstrated use rather than expanding the abstraction surface by default.

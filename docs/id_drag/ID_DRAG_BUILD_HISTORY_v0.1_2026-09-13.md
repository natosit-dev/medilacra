# ID DRAG Build History v0.1

**Project:** ID DRAG  
**Description:** Identity Resolution Doesn't Require A Gun  
**Repository:** `natosit-dev/medilacra`  
**Branch:** `experiment/id-drag`  
**Date:** 2026-09-13  
**Status:** Initial implementation

## Source plan

This build implements `docs/id_drag/ID_DRAG_PROJECT_PLAN_v0.1_2026-09-13.md`.

The implementation follows the deliberately narrow v0.1 experiment:

1. Reuse MediLacra's existing synthetic patient generator and DuckDB patient store.
2. Accept a JPEG or PNG hand image.
3. Ask one human-in-the-loop question: **“Does this hand belong to the human?”**
4. Only materialize an association when the answer is **Yes**.
5. Record `human_verified = true`.
6. Base64-encode the image without fingerprint extraction or biometric matching.
7. Carry the encoded image in an HL7 v2 OBX segment and a FHIR Observation.
8. Keep the experiment independent of law-enforcement infrastructure.

## Implementation decisions

### Separate page, shared patient substrate

ID DRAG is implemented as a sibling Streamlit page at:

`pages/11_ID_DRAG.py`

It reuses:

- `hl7_demo.generators.gen_patient`
- the existing MediLacra `patients` table
- `storage_duckdb_entities.init_db`
- `storage_duckdb_entities.upsert_patient`
- `connectathon.gravity_response.build_patient_resource`

No parallel patient model was introduced.

### Human verification is a hard gate

The UI asks exactly:

> **Does this hand belong to the human?**

The affirmative path is represented internally as:

`human_verified = true`

The gate is enforced in both layers:

- the Streamlit action is disabled until an image exists and the answer is Yes;
- the backend refuses to create artifacts unless `human_verified is True`.

Selecting **No** clears the current ID DRAG result and does not associate the uploaded image with the selected patient.

### No biometric processing in v0.1

The uploaded hand image is treated as the proof-of-concept identity artifact.

v0.1 does **not** perform:

- fingerprint enhancement;
- ridge or minutiae extraction;
- biometric template creation;
- 1:1 matching;
- 1:N search;
- forensic analysis.

The image bytes are Base64-encoded unchanged.

### HL7 v2

The backend creates a minimal `ORU^R01` message.

The image travels in an `OBX` with:

- `OBX-2 = ED`
- local observation code `IDDRAG-HAND-IMAGE`
- `ED.2 = IM`
- `ED.3 = JPEG` or `PNG`
- `ED.4 = Base64`
- `ED.5 = <encoded image>`

A second OBX carries the human assertion:

- code `IDDRAG-HUMAN-VERIFIED`
- value `Y`

This keeps the image and the provenance assertion explicit and inspectable in the healthcare message.

### FHIR

The backend creates:

- the existing synthetic FHIR `Patient`;
- an ID DRAG `Observation`;
- a collection `Bundle` containing both.

For this intentionally rough v0.1 transport experiment, the complete Base64 payload is carried directly in `Observation.valueString`.

The Observation also includes components for:

- `human_verified = true`;
- image content type;
- source filename when present.

This is a deliberate proof-of-concept shortcut, **not** a proposed canonical FHIR biometric profile.

### UI artifact inspection

The page exposes three result tabs:

1. **FHIR Observation**
2. **FHIR Bundle**
3. **HL7 ORU**

The on-screen previews truncate the Base64 string so the page remains usable. Downloaded artifacts retain the complete payload.

## Files added

### Runtime

- `connectathon/id_drag.py`
- `pages/11_ID_DRAG.py`

### Tests

- `tests/test_id_drag.py`
- `tests/test_id_drag_streamlit.py`

### CI

- `.github/workflows/id-drag-smoke.yml`

### Documentation

- `docs/id_drag/ID_DRAG_PROJECT_PLAN_v0.1_2026-09-13.md`
- `docs/id_drag/ID_DRAG_BUILD_HISTORY_v0.1_2026-09-13.md`

## Test coverage

The v0.1 tests verify:

- Base64 round-trip preservation of image bytes.
- Rejection of anything other than literal boolean `True` for `human_verified`.
- FHIR Observation contains the complete Base64 image.
- FHIR Observation identifies the synthetic Patient.
- FHIR Observation carries the human verification component.
- FHIR Bundle contains both Patient and Observation.
- HL7 output uses `OBX|...|ED|...` for the image.
- HL7 ED subtype follows JPEG/PNG.
- HL7 output carries the separate `IDDRAG-HUMAN-VERIFIED = Y` assertion.
- Unsupported image types are rejected.
- Streamlit page renders against the existing synthetic-patient store.
- The page contains the required single human verification question.
- Artifact creation is gated on affirmative human verification.

The branch has a dedicated GitHub Actions smoke-test workflow triggered by pushes to `experiment/id-drag`.

## Deferred by design

The following remain explicitly out of scope for v0.1:

- fingerprint masking;
- image normalization;
- fingerprint feature extraction;
- biometric templates;
- biometric matching;
- unknown-patient lookup;
- durable biometric registry;
- production consent and retention policy;
- canonical FHIR biometric modeling.

These should be added only if the first experiment demonstrates that they are useful to the underlying public-health identity question.

## v0.1 claim

ID DRAG v0.1 does not prove that a hand image can uniquely identify a patient.

It proves the smaller architectural point:

> **Healthcare can associate a human-verified, body-carried identity artifact with a patient and transport it through healthcare interoperability infrastructure without involving law enforcement.**

That is the experiment.

# MediLacra — Caregiver Health Baseline Initial User Testing

**Document type:** Initial user testing / usability feedback / defect provenance  
**Project:** MediLacra — Gravity Caregiver Health Baseline  
**Phase:** Phase 1  
**Document version:** v0.1  
**Testing date:** 2026-09-09  
**Branch:** `feature/gravity-caregiver-baseline-v0.1`  
**Environment:** WSL, existing `dev310` Conda environment, local Streamlit, local DuckDB  
**Tester:** Nat Osit  
**Status:** INITIAL INTERACTIVE TESTING SUCCESSFUL; ONE DEFECT FOUND AND FIXED; HOUSEKEEPING IMPROVEMENTS IMPLEMENTED  
**Related plan:** `docs/gravity/CAREGIVER_HEALTH_BASELINE_PHASE_1_PLAN_v0.1_2026-09-08.md`  
**Related build history:** `docs/gravity/CAREGIVER_HEALTH_BASELINE_PHASE_1_BUILD_HISTORY_v0.1_2026-09-08.md`  
**Related build analysis:** `docs/gravity/CAREGIVER_HEALTH_BASELINE_PHASE_1_BUILD_ANALYSIS_v0.1_2026-09-08.md`

---

## Verbatim user testing log

> **Nat:** “Don't we usually run from WSL?”

> **Nat:** “Clicking Decline threw this error”

Observed Streamlit exception:

```text
_duckdb.ConnectionException: Connection Error: Can't open a connection to same database file with a different configuration than existing connections
```

> **Nat:** “Looking good! Few housecleaning items-
> -There should be a reset button at the top to reset the buttons/values
> -All output artifacts should be in a zip you can download, and individual files
>
> Make these changes, and create a new doc with my initial user testing results”

---

## 1. Purpose

This document records the first direct human interaction with the Phase 1 caregiver-health UI on Nat's local machine.

The important distinction is that prior automated coverage had already shown that the page could render, FHIR artifacts could materialize, DuckDB persistence worked, and backend tests passed. This session tested the actual interaction surface in the environment Nat uses to run MediLacra.

The test immediately produced useful information that render-only testing had not exposed.

---

## 2. Test environment

The UI was run from the established MediLacra development environment rather than a new Windows-native environment:

```text
Windows host
    ↓
WSL
    ↓
Conda environment: dev310
    ↓
feature/gravity-caregiver-baseline-v0.1
    ↓
streamlit run medi_lacra_app.py
    ↓
Gravity — Caregiver Health Baseline
```

No IRIS server was required. No new Phase 2 infrastructure was involved.

The test used the existing local DuckDB path and existing MediLacra synthetic-patient machinery.

---

## 3. What worked immediately

The new Gravity caregiver page was reachable through the existing MediLacra Streamlit application.

The tester successfully reached the intended interface and was able to interact with the baseline questionnaire controls.

This confirms at minimum that the following integration assumptions held in the actual development environment:

- the feature branch could be pulled and run under the existing WSL / `dev310` workflow;
- the new Streamlit page loaded inside the existing multipage application;
- existing synthetic Patient data could be used by the caregiver baseline;
- the questionnaire controls rendered as intended;
- the explicit Decline control was visible and interactable.

This matters because those behaviors had previously been inferred from automated tests and CI, not from Nat's local interactive session.

---

## 4. Defect discovered: Decline-triggered DuckDB configuration conflict

### User action

Nat clicked a **Decline** button.

### Observed result

Streamlit reran the page and raised:

```text
_duckdb.ConnectionException:
Connection Error: Can't open a connection to same database file
with a different configuration than existing connections
```

The traceback reached:

```text
pages/10_Gravity_Caregiver_Health.py
    init_db(db_path)

storage_duckdb_entities.py
    _exec_ddl(...)

utils/db.py
    duckdb.connect(db)
```

### Engineering diagnosis

The existing DuckDB helper opened ordinary readers with `read_only=True` while writers used the default read/write configuration.

The Decline button intentionally calls `st.rerun()`. During Streamlit rerun behavior, connection lifetimes can briefly overlap. DuckDB does not permit connections to the same database file with incompatible configurations inside one process.

The interactive test therefore exposed a lifecycle problem that a simple page-render test did not.

### Fix

`utils/db.py` was changed so the ordinary `reader()` helper defaults to the same read/write connection configuration as `writer()`.

Explicit standalone callers can still request:

```python
reader(read_only=True)
```

when that distinction is actually required.

Fix commit:

```text
da3e19c5ed2a172b3ebdf1779d7970430ddd9843
Keep DuckDB reader configuration compatible with Streamlit writers
```

That fix passed the caregiver smoke workflow.

### Regression coverage

The Streamlit test was extended to execute the interaction that failed:

```text
render page
    ↓
click Decline
    ↓
Streamlit rerun
    ↓
assert no exception
    ↓
assert button changes to “Answer instead”
    ↓
assert asked-declined state is visible
```

Regression-test commit:

```text
a47bd1fa4cd33d76806400cb9f2ad16cc8dd03ad
Add regression test for caregiver decline rerun
```

---

## 5. Testing lesson

The first UI smoke test proved:

```text
THE PAGE RENDERS
```

Nat's first interaction tested:

```text
THE PAGE SURVIVES BEING USED
```

Those are not the same assertion.

The defect was not in the caregiver-health semantics, Gravity representation, FHIR materialization, or decline logic. It was in the interaction between Streamlit reruns and an older DuckDB connection policy inherited from the wider application.

This is a useful example of why interactive user testing should occur before treating CI-green UI code as finished.

---

## 6. Housekeeping feedback from initial testing

After the DuckDB issue was corrected, Nat reported that the UI was “Looking good!” and requested two usability improvements.

### UXR-001 — Reset assessment

**Request:** provide a reset button at the top of the page that resets questionnaire values and button states.

**Implementation:** added `Reset assessment` near the top of the caregiver page.

Reset clears caregiver-form session state including:

- entered questionnaire values;
- Decline / Answer instead states;
- medication repeat-row state and values;
- prior materialized result currently displayed in the UI.

Reset intentionally preserves:

- the configured DuckDB path;
- the selected synthetic Patient.

This makes Reset mean **start this assessment over**, not **reconfigure the application**.

A Streamlit regression test now verifies that a declined question returns to baseline after Reset.

Implementation/test commits:

```text
c97374916b81616f96f5b9842541508d688fe679
Add caregiver reset and complete artifact downloads

31526c5cb957d4156426be79b42f407baf213180
Test caregiver reset control
```

### UXR-002 — Complete downloadable artifact package

**Request:** every output artifact should be downloadable individually, and the complete output set should also be available as one ZIP archive.

**Implementation:** Phase 1 now serializes the following individual JSON artifacts:

```text
caregiver_health_baseline_questionnaire_v0.1.json
caregiver_health_questionnaire_response.json
caregiver_health_phase1_bundle.json
caregiver_health_quality_report.json
caregiver_health_bundle_cleanup.json
```

The same five files are packaged into:

```text
caregiver_health_phase1_artifacts.zip
```

The ZIP is generated in memory; no second artifact-storage subsystem was introduced.

A backend test verifies that the ZIP contains exactly the same bytes as the individually generated artifact files.

Implementation/test commits:

```text
deaa46535fb64df647a4d4aa658662a047fa85e6
Package caregiver Phase 1 output artifacts

dc71323fff13a39b2c668193d439be04dc39ed61
Test complete caregiver artifact archive
```

---

## 7. Initial testing result matrix

| Area | User-observed status | Engineering status | Notes |
|---|---|---|---|
| WSL / existing environment startup | PASS | PASS | Existing `dev310` workflow remains the expected local path |
| Gravity caregiver page reachable | PASS | PASS | New page appears in existing Streamlit app |
| Synthetic Patient integration | PASS | PASS | Existing patient machinery reused |
| Questionnaire controls render | PASS | PASS | Baseline UI reached successfully |
| Decline interaction | FAIL → FIXED | Regression-covered | Exposed DuckDB read-only/read-write configuration conflict |
| Reset assessment | Requested after first test | Implemented; automated verification added | Awaiting direct user confirmation after pull |
| Individual artifact downloads | Requested after first test | Implemented | Questionnaire, response, bundle, quality, cleanup |
| Complete ZIP download | Requested after first test | Implemented; archive-content test added | Same five artifacts as individual downloads |
| IRIS round trip | NOT TESTED | Phase 2 | Intentionally outside Phase 1 |

---

## 8. Provenance and interpretation boundary

The statements in this document are separated by source:

**Direct user observations:**

- the page was reached on Nat's machine;
- clicking Decline produced the DuckDB exception shown above;
- after the fix, Nat characterized the UI as “Looking good!”;
- Nat requested reset and ZIP/individual artifact downloads.

**Engineering diagnosis / implementation evidence:**

- the connection mismatch came from incompatible DuckDB reader/writer configurations during Streamlit rerun behavior;
- the reader default was changed to keep configurations compatible;
- reset behavior and artifact packaging were added in the commits listed above;
- automated tests were added for Decline rerun, Reset, and ZIP equality.

No claim is made here that Reset and artifact downloads have already been manually validated by Nat. They were implemented in response to the first testing session and are the next things to verify interactively.

---

## 9. Next manual verification

After pulling the latest branch, the next direct user test should be intentionally small:

```text
1. Enter a few values.
2. Decline one question.
3. Click Reset assessment.
4. Confirm values and decline states clear.
5. Submit a boring assessment.
6. Download one individual artifact.
7. Download the ZIP.
8. Confirm the ZIP contains the same visible artifact set.
```

If those actions behave as expected, the Phase 1 local UI is functionally complete for the current baseline.

---

## 10. Current conclusion

The first real user interaction did exactly what early user testing should do: it found a lifecycle defect outside the happy-path backend logic, produced a small corrective change, and then exposed two obvious usability improvements.

The resulting Phase 1 UI now has a cleaner interaction contract:

```text
START
  ↓
ANSWER / DECLINE
  ↓
RESET IF NEEDED
  ↓
SUBMIT
  ↓
INSPECT
  ↓
DOWNLOAD INDIVIDUAL ARTIFACTS
  ↓
DOWNLOAD COMPLETE ZIP
```

The experiment remains deliberately boring. The user-facing mechanics are now closer to the same standard as the data model: preserve the distinctions that matter, make the artifacts inspectable, and do not invent extra machinery when a small explicit operation is enough.

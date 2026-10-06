# X12 Eligibility UI MVP Build Design

**Version:** 0.1  
**Date:** 2026-10-06  
**Branch:** `experiment/employer-coverage`  
**Status:** Implementation-ready

---

# 1. Purpose

Add one Streamlit page that manually exercises the first two X12 270/271 scenarios already implemented.

The page is a thin test harness over existing clinical, payer, identity, and X12 code.

It must not introduce new payer logic, persistence, or X12 semantics.

---

# 2. User Flow

```text
choose scenario
      |
      v
inspect clinical reality beside payer reality
      |
      v
Run 270/271 Exchange
      |
      v
clinical state -> 270
      |
      v
parse 270 -> EligibilityInquiry
      |
      v
payer matching + eligibility
      |
      v
EligibilityResponse -> 271
      |
      v
inspect / download 270 and 271
```

---

# 3. New Streamlit Page

Create:

```text
pages/8_X12_Eligibility.py
```

Page title:

```text
MediLacra — X12 Eligibility
```

Caption:

```text
Synthetic 270/271 eligibility exchange between independent clinical and payer realities.
```

---

# 4. Controls

MVP controls:

```text
Scenario
    Clean Active Eligibility
    Identity Divergence — Payer Name Differs

Service Date

Run 270/271 Exchange
```

No arbitrary payer/member editing in this version.

The initial fixture service date is 2026-10-06 so both first scenarios remain the already-validated ACTIVE path.

---

# 5. Reality Preview

Before running, display two columns:

```text
CLINICAL REALITY                   PAYER REALITY
----------------                   -------------
Patient name                       Member name
DOB                                DOB
Member ID                          Member ID
Payer                              Payer
Plan                               Enrollment status
Group                              Plan
```

Scenario 1 should visibly show matching identities.

Scenario 2 should visibly show:

```text
Clinical: Devin Kelley
Payer:    Devin Kelly
```

Add a short note that payer evaluation uses payer-held state and does not dereference the clinical record.

---

# 6. Scenario Fixtures

Add:

```text
x12/scenarios.py
```

It owns only demo/test-harness fixtures and orchestration.

Expose two scenario keys:

```text
clean_active
identity_divergence
```

The clean scenario creates:

- clinical Patient;
- clinical CoverageProfile;
- hidden truth used only for materialization;
- payer MemberRecord;
- payer EnrollmentRecord;
- payer BenefitPlan;
- PayerSystem;
- requester organization.

The divergence scenario starts from the same synthetic truth but independently changes payer-local last name:

```text
KELLEY -> KELLY
```

The payer operational path still may not consume GroundTruthLink.

---

# 7. Exchange Execution

The scenario runner should:

```text
build clinical-side 270 transaction
      |
wrap in ISA/GS/GE/IEA
      |
parse full 270 into EligibilityInquiry
      |
resolve member against payer state
      |
evaluate payer eligibility
      |
build payer-authored 271 transaction
      |
wrap response in ISA/GS/GE/IEA
```

Everything remains in memory.

No DuckDB.

No output folder writes.

---

# 8. Result Summary

After execution show:

```text
Member Match
Eligibility
Plan
Coverage
Trace
```

Scenario 2 also shows:

```text
Identity Conflict: last_name
Clinical last name: Kelley
Payer last name: Kelly
```

The UI must not reconcile or hide the difference.

---

# 9. Message Inspection

Use two tabs:

```text
X12 270 Request
X12 271 Response
```

Display the full interchange:

```text
ISA
GS
ST
...
SE
GE
IEA
```

The displayed text may add line breaks after segment terminators for readability, but downloaded bytes must preserve the generated interchange string.

---

# 10. Downloads

Required:

```text
Download 270
Download 271
```

All filenames must include the datetime stamp from the exchange run.

Format:

```text
medilacra_270_YYYYMMDD_HHMMSS.x12
medilacra_271_YYYYMMDD_HHMMSS.x12
```

Also include one ZIP because it is low-complexity and useful for manual testing:

```text
medilacra_x12_exchange_YYYYMMDD_HHMMSS.zip
```

ZIP contents:

```text
medilacra_270_YYYYMMDD_HHMMSS.x12
medilacra_271_YYYYMMDD_HHMMSS.x12
exchange_summary_YYYYMMDD_HHMMSS.json
```

The summary should record scenario, trace, match outcome, eligibility outcome, conflicts, service date, and clinical/payer identity values.

---

# 11. Session State

Store the completed exchange in Streamlit session state.

Reason:

Streamlit reruns on UI interaction. Download clicks must continue to expose the exact same X12 artifacts rather than regenerating a new trace/timestamp.

The exchange is regenerated only when the user clicks:

```text
Run 270/271 Exchange
```

---

# 12. Tests

Add:

```text
tests/test_x12_ui_scenarios.py
```

Test the non-Streamlit scenario/workflow layer:

- both fixtures load;
- clean scenario stays KELLEY -> KELLEY;
- divergence scenario is KELLEY -> KELLY;
- clean scenario produces ACTIVE;
- divergence produces MATCHED with `last_name` conflict;
- generated 270 and 271 are full interchanges;
- 270 carries clinical identity;
- 271 carries payer identity;
- filenames contain the run datetime stamp;
- ZIP contains both stamped X12 files plus stamped JSON summary;
- summary records institutional identity divergence.

Do not test Streamlit rendering internals.

---

# 13. Explicit Non-Goals

Not in this page:

- manual raw 270 editor;
- arbitrary 270 upload;
- NOT_FOUND / AAA;
- INACTIVE response projection;
- payer/member free-form editing;
- dependent coverage;
- benefit financials;
- accumulators;
- batch X12;
- persistence;
- clearinghouse configuration;
- delimiter editing;
- 278 / 837 / 835.

---

# 14. Definition of Done

The page is complete when the normal MediLacra Streamlit application exposes an X12 Eligibility page where a user can:

1. choose either existing scenario;
2. see clinical and payer reality side by side;
3. run the exchange once;
4. see match and eligibility results;
5. inspect the full 270 and 271 interchanges;
6. download both X12 files with `YYYYMMDD_HHMMSS` filenames;
7. optionally download the stamped exchange ZIP;
8. visibly confirm in Scenario 2 that the 270 says `KELLEY` while the 271 says `KELLY`.

The UI remains a test harness. The institutional and payer boundaries remain unchanged.

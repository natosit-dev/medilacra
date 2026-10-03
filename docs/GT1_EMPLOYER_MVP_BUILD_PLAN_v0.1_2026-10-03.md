# GT1 Employer Projection MVP — Build Plan

**Version:** 0.1  
**Date:** 2026-10-03  
**Branch:** `experiment/employer-coverage`  
**Status:** Implementation-ready  
**Parent build:** `docs/EMPLOYER_COVERAGE_BUILD_DESIGN_v0.1_2026-10-03.md`

---

# Relevant Prompt Lineage

> "I think the employer from the insurance fields should also be instantiated in the corresponding PID fields."

This prompted a review of where employer information belongs in HL7 v2.5. PID does not contain an employer field. The patient-side canonical employer is already populated through `Patient.employer`, while the corresponding HL7 v2 employer representations live in insurance/guarantor context, particularly IN1/IN2 and GT1.

> "Let's do a mini gap analysis for what we'd need for MVP of GT1 filled with the matching employer info"

The gap analysis found that the current GT1 builder only populates GT1-1, GT1-3, and GT1-11 from legacy Transaction guarantor fields. Those guarantor values are still independently randomized, while CoverageProfile already owns the authoritative employer-sponsored coverage context.

> "We should only add GT1 if patient is over 18. We're not going to tackle family relationships yet. Let's see a minimal build plan"

This establishes the MVP boundary:

- GT1 is emitted only when the patient is strictly older than 18 at the encounter date.
- Age 18 or younger receives no GT1.
- No parent, spouse, guardian, dependent, or family relationship model is introduced.
- For an eligible adult with CoverageProfile, the patient is the guarantor and the employer comes from that same CoverageProfile.
- Employer address, employer phone, and employee ID remain deferred.

> "Document the plan, include my relevant prompts, write to MD, then build it"

This document is the durable build plan for that implementation.

---

# 1. Purpose

Make GT1 describe the same institutional reality already represented by:

```text
Patient.employer
CoverageProfile.employer
IN1 employer fields
IN2 employer fields
```

without introducing family/dependent modeling.

The current mismatch is:

```text
CoverageProfile
  employer = Home Depot
  subscriber = SELF

Transaction
  guarantor = randomly generated person
  relationship = randomly generated relationship
```

That allows GT1 to contradict the employer-sponsored coverage reality.

For this MVP:

```text
adult patient (>18)
      |
      v
CoverageProfile
      |
      +--> patient is guarantor
      +--> guarantor relationship = SELF
      +--> employer name
      +--> employment status
      '--> employer ID
      |
      v
GT1
```

---

# 2. Age Rule

GT1 is emitted only when:

```text
patient age at encounter > 18
```

This is deliberately **strictly greater than 18**.

Therefore:

```text
age 19  -> GT1
age 18  -> no GT1
age 17  -> no GT1
```

Age is calculated from the patient's date of birth relative to the encounter/admit date, not relative to the current wall-clock date.

That preserves consistency for historical and future synthetic encounters.

If age cannot be determined reliably from the available values, the safe MVP behavior is:

```text
no GT1
```

because emitting a self-guarantor assumption for a possibly minor patient would violate the explicit boundary of this build.

---

# 3. GT1 MVP Fields

For an eligible adult with a CoverageProfile:

| GT1 Field | Value | Source |
|---|---|---|
| GT1-1 Set ID | `1` | message builder |
| GT1-3 Guarantor Name | patient name | `Patient.patient_name` |
| GT1-11 Guarantor Relationship | SELF | CoverageProfile/current MVP assumption |
| GT1-16 Guarantor Employer Name | employer name | `CoverageProfile.employer_name` |
| GT1-20 Employment Status | Full time employed (`1`) | `CoverageProfile.worker_profile` |
| GT1-29 Guarantor Employer ID | employer ID | `CoverageProfile.employer_id` |

Current worker-profile mapping:

```text
DEFAULT_FULL_TIME_EMPLOYEE -> 1
```

No additional employment ontology is introduced in this build.

---

# 4. Explicitly Deferred GT1 Fields

The following remain blank:

```text
GT1-17 Employer Address
GT1-18 Employer Phone Number
GT1-19 Employee ID
```

Reason:

- employer address is not modeled;
- employer phone is not modeled;
- employee ID is not currently a CoverageProfile primitive;
- none of these are needed to prove the institutional-context mapping.

No synthetic corporate contact data is generated merely to fill HL7 fields.

---

# 5. Code Changes

## 5.1 `hl7_demo/segments.py`

Extend:

```python
seg_gt1(
    tx,
    patient=None,
    coverage_profile=None,
    set_id=1,
)
```

Behavior:

### Coverage-aware path

When both Patient and CoverageProfile are available:

```text
GT1-3  <- Patient.patient_name
GT1-11 <- SELF
GT1-16 <- CoverageProfile.employer_name
GT1-20 <- mapped CoverageProfile.worker_profile
GT1-29 <- CoverageProfile.employer_id
```

CoverageProfile is authoritative.

### Legacy fallback

If CoverageProfile is absent, preserve the existing Transaction-based GT1 behavior for compatibility:

```text
GT1-3  <- Transaction.guarantor_name
GT1-11 <- Transaction.guarantor_relationship
```

This build does not remove legacy fields or force unrelated callers to adopt CoverageProfile.

---

## 5.2 `hl7_demo/messages.py`

Add one private age helper, conceptually:

```python
_patient_age_at_encounter(patient, encounter) -> int | None
```

and one eligibility rule:

```python
_should_emit_gt1(patient, encounter) -> bool
```

The age calculation must account for whether the birthday has occurred by the encounter date.

GT1 insertion becomes:

```python
coverage_profile = patient.coverage_profile

if _should_emit_gt1(patient, encounter):
    parts.append(
        seg_gt1(
            transaction,
            patient=patient,
            coverage_profile=coverage_profile,
            set_id=1,
        )
    )
```

IN1 and IN2 are **not** age-gated. A minor may still have insurance coverage; this build simply refuses to invent the family/guarantor relationship needed for GT1.

Apply this rule to both current GT1 call sites:

- ADT^A01
- DFT^P03

---

# 6. No New Model Fields

This MVP does **not** add:

- `employee_id`
- employer address
- employer phone
- family relationship
- dependent/subscriber person
- guarantor entity
- CoverageEnrollment

The existing objects are sufficient.

---

# 7. Institutional Reality Invariant

For eligible adult CoverageProfile patients:

```text
Patient.employer
GT1-16 employer name
GT1-29 employer ID
IN1-11 employer name
IN2-3 employer ID/name
        |
        v
all originate from CoverageProfile
```

The GT1 builder must not independently generate employer values.

---

# 8. Tests

Add focused GT1 employer tests for:

1. age 19 -> GT1 emitted;
2. age 18 -> GT1 omitted;
3. age 17 -> GT1 omitted;
4. exact birthday handling at encounter time;
5. invalid/unparseable DOB -> GT1 omitted;
6. adult GT1-3 equals patient name;
7. adult GT1-11 is SELF;
8. GT1-16 equals `CoverageProfile.employer_name`;
9. GT1-20 is `1` for `DEFAULT_FULL_TIME_EMPLOYEE`;
10. GT1-29 equals `CoverageProfile.employer_id`;
11. GT1-17/18/19 remain blank;
12. ADT applies the age gate;
13. DFT applies the same age gate;
14. IN1 and IN2 remain present for covered minors even when GT1 is omitted;
15. existing full pytest regression remains green.

---

# 9. Demo Update

Update `scripts/demo_employer_coverage.py` so it uses the same coverage-aware GT1 signature rather than manually overriding Transaction guarantor values.

The adult demo should show the same employer in:

```text
Patient.employer
GT1
IN1
IN2
```

The previous hand-written plausible street address should also be replaced with an unmistakably synthetic/non-geocodable test address while preserving real city/state/ZIP context.

That address change is cleanup from the immediately preceding review, not an expansion of GT1 scope.

---

# 10. Definition of Done

The build is complete when:

1. this plan is durable in Git;
2. GT1 is emitted only for patients strictly older than 18 at encounter time;
3. adult CoverageProfile GT1 uses the patient as self-guarantor;
4. GT1 employer name and ID match CoverageProfile;
5. employment status is derived from the current full-time worker profile;
6. employer address, phone, and employee ID remain blank;
7. minors retain IN1/IN2 coverage context without GT1;
8. both ADT and DFT follow the same rule;
9. the deterministic coverage demo reflects the new behavior;
10. focused GT1 tests pass;
11. the complete repository regression suite passes.

# Institutional Reality Separation + Synthetic Payer MVP Build Design

**Version:** 0.1  
**Date:** 2026-10-05  
**Branch:** `experiment/employer-coverage`  
**Status:** Implementation-ready  
**Pre-build head:** `e0110ecbd2a9c7af5040a12e9fe0336c509e4a9c`

---

# 1. Purpose

Introduce the minimum architecture required for MediLacra to represent **separate synthetic clinical and payer realities** before implementing X12 270/271.

The core architectural rule is:

> **Clinical records and payer records may originate from the same hidden synthetic truth, but neither institutional reality may directly dereference the other.**

The first payer engine must therefore answer eligibility questions from payer-held state, not by reading `Patient` or `CoverageProfile`.

This build establishes boundaries and primitives only. It intentionally does **not** build X12 syntax.

---

# 2. Relevant Prompt Lineage

> "I think it's a good idea to start brainstorming about X12"

This introduced X12 as the next representation family.

> "Yeah, let's start with 270/271. Now the tricky part - the synthetic payer system. We should slow down and think about this because it will be a new engine."

This established that the payer must be a new engine rather than a 271 template generator.

> "Ah, this will also add a patient matching element. We can add it to the Medilacra side as well"

This introduced reusable identity matching as a MediLacra capability rather than an X12-specific function.

> "I'm thinking we should keep the synthetic clinical and payer realities separate. This is a big deal/change and I want to get the primitives right"

This is the governing architectural decision.

> "Put together a build plan. Don't overbuild but let's make clear boundaries."

This constrained the implementation to a narrow institutional-separation MVP.

> "Go build the MVP after you put this in a build design doc in the branch"

This document is the durable design checkpoint preceding implementation.

---

# 3. Architectural Thesis

A synthetic payer must not be omniscient.

If the payer engine reads the same `Patient` and `CoverageProfile` objects used by the clinical generator, then a future 270/271 workflow is only representational theater:

```text
clinical record
      |
      +---- payer reads same object
                 |
                 '--> 271
```

Instead:

```text
                    HIDDEN SIMULATION TRUTH
                           |
             +-------------+-------------+
             |                           |
             v                           v
      CLINICAL REALITY              PAYER REALITY
      ----------------              -------------
      Patient                       MemberRecord
      CoverageProfile               EnrollmentRecord
      Encounter                     BenefitPlan
      Observation
      Transaction
             |                           |
             | future 270                |
             +-------------------------->|
                                         |
                                  payer-side matching
                                  enrollment evaluation
                                         |
                                         | future 271
             <---------------------------+
```

This creates an **epistemic boundary**: each institution operates on its own materialized state.

---

# 4. Hidden Simulation Truth

The hidden truth layer exists for:

- deterministic scenario construction;
- materializing institutional records;
- test oracles;
- evaluating whether matching/eligibility logic reached the correct answer.

It must never be used as an operational lookup shortcut.

## 4.1 `PersonTruth`

Minimum fields:

```text
truth_person_id
first_name
last_name
date_of_birth
administrative_sex
address
phone
```

This is not a Patient, MemberRecord, FHIR Patient, or X12 subscriber.

## 4.2 `CoverageTruth`

Minimum fields:

```text
truth_coverage_id
truth_person_id
payer_id
employer_id
plan_id
group_number
member_id
effective_start
effective_end
```

It expresses the synthetic-world coverage fact. It is not clinical coverage state and not payer enrollment state.

## 4.3 `GroundTruthLink`

The oracle-only correspondence object:

```text
truth_person_id
truth_coverage_id

clinical_patient_id
clinical_coverage_profile_id

payer_member_record_id
payer_enrollment_id
```

Hard rule:

> `GroundTruthLink` may be used by generation/tests, but may never be passed into patient/member matching or payer eligibility evaluation.

---

# 5. Clinical Reality

The existing MediLacra clinical model remains intact.

Current primitives remain:

```text
Patient
Encounter
Observation
Transaction
CoverageProfile
```

For this architecture:

> `CoverageProfile` is explicitly interpreted as **clinical-side knowledge of coverage**, not universal coverage truth.

No rename or pipeline rewrite is required in this MVP.

The new identity toolkit is reusable by MediLacra clinical workflows, but this build does not retrofit all existing clinical generation around it.

---

# 6. Payer Reality

Create a new payer package with no dependency on clinical model classes.

Minimum payer-local primitives:

## `MemberRecord`

```text
member_record_id
payer_id
member_id
first_name
last_name
date_of_birth
administrative_sex
```

Forbidden fields:

```text
patient_id
clinical_patient_id
coverage_profile_id
```

## `EnrollmentRecord`

```text
enrollment_id
member_record_id
payer_id
plan_id
group_number
effective_start
effective_end
status
```

MVP statuses:

```text
ACTIVE
INACTIVE
```

## `BenefitPlan`

```text
plan_id
payer_id
plan_name
plan_type
```

Existing `STANDARD_PPO` / `STANDARD_HMO` fixtures can populate these records.

No detailed benefit design is needed yet.

---

# 7. Institutional Materialization

Truth materializes independent institutional state:

```text
PersonTruth
    |
    +--> existing clinical reality
    |
    '--> payer MemberRecord

CoverageTruth
    |
    +--> existing clinical CoverageProfile
    |
    '--> payer EnrollmentRecord / BenefitPlan
```

For the MVP, the new code only needs to materialize the payer-side state. Existing clinical generation already materializes the clinical side and will not be rewritten.

The key implementation property is **copy semantics, not shared-object semantics**.

After payer state is materialized, changes to clinical state must not mutate payer state.

---

# 8. Reusable Identity Matching

Create a MediLacra-level identity toolkit that is independent of X12.

Target package:

```text
identity/
    __init__.py
    models.py
    matcher.py
    normalize.py
```

## `IdentityQuery`

Minimum matchable fields:

```text
member_id?
first_name?
last_name?
date_of_birth?
administrative_sex?
```

## `MatchResult`

```text
outcome
candidate_ids
matched_fields
conflicting_fields
score
```

Outcomes:

```text
MATCHED
AMBIGUOUS
NOT_FOUND
```

## MVP matching policy

1. If member ID is supplied, perform exact member-ID resolution.
2. Compare supplied demographics against the resolved candidate and expose discrepancies.
3. If member ID is absent, exact first name + last name + DOB may resolve a member.
4. Zero candidates => `NOT_FOUND`.
5. Multiple candidates => `AMBIGUOUS`.
6. No fuzzy matching, nickname logic, phonetics, or probabilistic MPI scoring yet.

A member-ID match may still return demographic conflicts. This is intentional.

Example:

```text
member ID exact
DOB exact
last name differs

=> MATCHED
=> conflicting_fields = ["last_name"]
```

---

# 9. Synthetic Payer Engine

Target package:

```text
payer/
    __init__.py
    models.py
    materialize.py
    system.py
```

`PayerSystem` owns only payer-local state:

```text
members
enrollments
plans
```

It must not import or store `Patient`, `CoverageProfile`, or `GroundTruthLink`.

Conceptual API:

```python
payer.resolve_member(identity_query)

payer.evaluate_eligibility(eligibility_inquiry)
```

---

# 10. Eligibility Semantics

Define semantic request/response primitives before X12.

## `EligibilityInquiry`

```text
payer_id
requester_id?
member_id?
first_name?
last_name?
date_of_birth?
administrative_sex?
service_date
```

## `EligibilityResponse`

```text
outcome
member_record_id?
enrollment_status?
plan_id?
group_number?
coverage_start?
coverage_end?
matched_fields
conflicting_fields
errors
```

MVP outcomes:

```text
ACTIVE
INACTIVE
NOT_FOUND
AMBIGUOUS
CANNOT_DETERMINE
```

No X12 segment names belong in these objects.

Future adapter:

```text
X12 270
   |
   v
EligibilityInquiry
   |
   v
PayerSystem
   |
   v
EligibilityResponse
   |
   v
X12 271
```

---

# 11. Eligibility Evaluation

MVP decision sequence:

```text
EligibilityInquiry
       |
       v
Does inquiry target this payer?
       |
       v
Resolve against payer MemberRecords
       |
       +-- zero ------> NOT_FOUND
       |
       +-- multiple --> AMBIGUOUS
       |
       '-- one
            |
            v
       Find payer enrollment
            |
            +-- no enrollment --> CANNOT_DETERMINE
            |
            v
       Is service date inside enrollment period
       and enrollment status ACTIVE?
            |
            +-- yes --> ACTIVE
            |
            '-- no --> INACTIVE
```

No benefits, deductible, copay, accumulator, network, or trading-partner authorization logic yet.

---

# 12. Physical / Dependency Boundaries

Target additions:

```text
reality/
    __init__.py
    models.py

identity/
    __init__.py
    models.py
    normalize.py
    matcher.py

payer/
    __init__.py
    models.py
    materialize.py
    system.py
```

Dependency direction:

```text
reality.models
      |
      v
payer.materialize
      |
      v
payer.models
      |
      v
payer.system

identity.models/matcher
      |
      v
payer.system
```

Forbidden dependency direction:

```text
payer.models  -> hl7_demo.models
payer.system  -> Patient
payer.system  -> CoverageProfile
payer.system  -> GroundTruthLink
```

`payer.materialize` may consume truth objects because materialization is a simulation/generation concern, not operational payer logic.

---

# 13. First Scenario

Hidden truth:

```text
PersonTruth
    Devin Kelley
    DOB 1949-01-16

CoverageTruth
    payer = KAISER
    plan = STANDARD_PPO
    employer = CVS
    member = MEM-01374522
    group = GRP-CVS-398915
    effective = 2026-01-01 .. 2026-12-31
```

Materialize payer:

```text
MemberRecord
EnrollmentRecord
BenefitPlan
```

Inquiry:

```text
member_id = MEM-01374522
name = Devin Kelley
DOB = 1949-01-16
service_date = 2026-10-04
```

Expected:

```text
MatchResult = MATCHED
EligibilityResponse = ACTIVE
```

---

# 14. First Divergence Scenario

Same truth, but payer state is deliberately changed after materialization:

```text
clinical side:
    Devin Kelley

payer side:
    Devin Kelly
```

Inquiry:

```text
member ID exact
DOB exact
last name = Kelley
```

Expected:

```text
MATCHED
conflicting_fields = ["last_name"]
```

The matcher must not consult ground truth to repair the payer record.

---

# 15. Test Plan

Create:

```text
tests/test_reality_separation.py
tests/test_payer_matching.py
tests/test_payer_eligibility.py
```

## Boundary invariants

- payer MemberRecord has no patient ID field;
- EnrollmentRecord has no CoverageProfile reference;
- payer operational objects contain no `GroundTruthLink`;
- materialized payer objects are independent copies;
- mutating clinical state cannot mutate payer state;
- matching uses only inquiry values and payer records.

## Matching

- exact member ID => MATCHED;
- exact member ID + demographic discrepancy => MATCHED with conflict;
- unknown member ID => NOT_FOUND;
- exact demographic search with one candidate => MATCHED;
- duplicate plausible candidates => AMBIGUOUS.

## Eligibility

- matched + active/date-valid enrollment => ACTIVE;
- matched + out-of-period enrollment => INACTIVE;
- matched + enrollment status INACTIVE => INACTIVE;
- matched + no enrollment => CANNOT_DETERMINE;
- NOT_FOUND propagates;
- AMBIGUOUS propagates;
- wrong payer does not leak another payer's state.

## Separation

At least one explicit proof:

```text
materialize payer member
mutate clinical/source object
assert payer member unchanged
```

---

# 16. Storage Decision

No payer DuckDB in this MVP.

The first payer engine is in-memory.

Reason:

- fewer moving parts while primitives are still changing;
- easier enforcement of institutional boundaries;
- no accidental operational dependence on an oracle/truth database.

Roadmap:

```text
data/medilacra.duckdb
data/medilacra_payer.duckdb
```

Physical database separation remains the preferred later direction.

---

# 17. Explicit Non-Goals

Not in this build:

- X12 syntax;
- 270 parser;
- 271 builder;
- ISA / GS / ST / SE / GE / IEA;
- EB / AAA;
- trading-partner authorization;
- detailed benefits;
- accumulators;
- deductibles;
- copays;
- coinsurance;
- 278 prior authorization;
- 837 claims;
- 835 remittance;
- family/dependent relationships;
- fuzzy/probabilistic MPI;
- persisted payer database;
- ZMC;
- FHIR changes;
- UI changes.

---

# 18. Definition of Done

The MVP is complete when MediLacra can demonstrate:

```text
PersonTruth
     |
     +------> clinical world remains independent
     |
     '---> Payer MemberRecord

CoverageTruth
     |
     +------> clinical coverage remains independent
     |
     '---> Payer EnrollmentRecord
```

and:

```text
EligibilityInquiry
       |
       v
payer-side identity resolution
       |
       v
payer-side enrollment lookup
       |
       v
EligibilityResponse
```

with:

```text
no Patient reference in payer state
no CoverageProfile reference in payer state
no GroundTruthLink in payer operational logic
MATCHED / AMBIGUOUS / NOT_FOUND identity outcomes
ACTIVE / INACTIVE / CANNOT_DETERMINE eligibility behavior
institutional state divergence possible
focused tests green
full repository regression green
```

The architectural milestone is:

> **Two synthetic institutions can hold different records about the same hidden synthetic person without sharing operational state.**

Only after that boundary is demonstrated should X12 270/271 be added as an adapter around the payer engine.

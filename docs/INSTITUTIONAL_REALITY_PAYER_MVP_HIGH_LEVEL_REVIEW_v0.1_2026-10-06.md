# Institutional Reality + Synthetic Payer MVP — High-Level Review

**Version:** 0.1  
**Date:** 2026-10-06  
**Branch:** `experiment/employer-coverage`  
**Status:** Built / validated

---

# 1. What Changed

MediLacra now separates hidden synthetic truth from institution-specific records.

```text
Hidden synthetic truth
        |
        +--> Clinical reality
        |     Patient
        |     CoverageProfile
        |     Encounter
        |     Observation
        |     Transaction
        |
        '--> Payer reality
              MemberRecord
              EnrollmentRecord
              BenefitPlan
```

The clinical and payer records may originate from the same synthetic person and coverage truth, but they are no longer the same operational objects.

This creates an explicit **institutional epistemic boundary**.

---

# 2. Hidden Simulation Truth

The new `reality/` package contains:

- `PersonTruth`
- `CoverageTruth`
- `GroundTruthLink`

`PersonTruth` and `CoverageTruth` define what is actually true in the synthetic world.

`GroundTruthLink` records oracle-only correspondence between institutional records, for example:

```text
PersonTruth P-001
    |
    +--> Clinical Patient RAD1054994
    '--> Payer MemberRecord PM-...
```

The operational payer engine is not allowed to use this link for matching or eligibility.

---

# 3. Clinical Reality

The existing clinical side remains substantially unchanged.

Existing primitives continue to operate:

```text
Patient
CoverageProfile
Encounter
Observation
Transaction
```

The important semantic clarification is:

> `CoverageProfile` is clinical-side knowledge about coverage, not universal coverage truth.

Existing HL7 v2 and FHIR projections continue to use this clinical-side record.

---

# 4. Payer Reality

The new `payer/` package introduces payer-local state:

```text
MemberRecord
EnrollmentRecord
BenefitPlan
EligibilityInquiry
EligibilityResponse
PayerSystem
```

Payer records contain no clinical `patient_id` and no `CoverageProfile` reference.

The payer system therefore cannot answer eligibility by dereferencing clinical state.

---

# 5. Reusable Identity Matching

The new `identity/` package contains a representation-neutral matching toolkit:

```text
IdentityQuery
      |
      v
match_identity()
      |
      v
MatchResult
```

Current outcomes:

```text
MATCHED
AMBIGUOUS
NOT_FOUND
```

Current matching behavior is intentionally conservative:

- exact member ID is the primary payer lookup;
- without member ID, exact first name + last name + DOB may resolve a candidate;
- multiple candidates return `AMBIGUOUS`;
- demographic disagreement is preserved rather than silently repaired;
- no fuzzy or probabilistic MPI logic yet.

Example:

```text
Inquiry:
member ID = exact
DOB = exact
last name = Kelley

Payer record:
member ID = exact
DOB = exact
last name = Kelly

Result:
MATCHED
conflicting_fields = ["last_name"]
```

This makes institutional divergence testable.

---

# 6. Eligibility Engine

The payer now answers semantic eligibility questions from payer-held state.

```text
EligibilityInquiry
        |
        v
PayerSystem
        |
        +--> member resolution
        |
        '--> enrollment evaluation
                |
                v
        EligibilityResponse
```

Current eligibility outcomes:

```text
ACTIVE
INACTIVE
NOT_FOUND
AMBIGUOUS
CANNOT_DETERMINE
```

Examples:

```text
matched member
+ ACTIVE enrollment
+ requested date inside effective period
= ACTIVE
```

```text
matched member
+ service date outside enrollment period
= INACTIVE
```

```text
matched member
+ no payer enrollment
= CANNOT_DETERMINE
```

---

# 7. Institutional Separation Rule

The core invariant is:

```text
Clinical Patient
      X
      | no direct operational reference
      X
Payer MemberRecord
```

The hidden simulation layer may know that the two records correspond to the same synthetic person.

Neither institution may use that hidden correspondence operationally.

This means MediLacra can now represent:

```text
Clinical reality:
Devin Kelley

Payer reality:
Devin Kelly
```

without changing the hidden synthetic person.

Likewise, future scenarios can support:

```text
Clinical coverage:
active

Payer enrollment:
terminated
```

without forcing one institution's state to overwrite the other.

---

# 8. What Was Deliberately Not Built

The payer MVP does not yet contain:

- X12 syntax;
- 270 parsing;
- 271 generation;
- ISA/GS/ST envelope logic;
- EB or AAA projection;
- detailed benefit design;
- deductibles;
- copays;
- coinsurance;
- accumulators;
- trading-partner authorization;
- fuzzy/probabilistic MPI;
- dependent/family coverage;
- persisted payer DuckDB;
- 278 prior authorization;
- 837 claims;
- 835 remittance.

This is intentional.

The engine exists before the representation.

---

# 9. Next Architectural Layer

The next layer can now be:

```text
X12 270
   |
   v
adapter
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
adapter
   |
   v
X12 271
```

X12 will therefore represent payer behavior rather than define it.

---

# 10. Validation

Added test suites:

```text
tests/test_reality_separation.py
tests/test_payer_matching.py
tests/test_payer_eligibility.py
```

Validated result:

```text
Focused branch suite:
63 passed

Full repository regression:
76 passed
```

Successful CI run:

```text
https://github.com/natosit-dev/medilacra/actions/runs/37399334192
```

---

# 11. Compressed Summary

MediLacra can now represent **two institutions holding different records about the same synthetic person**, and the payer can answer eligibility questions using only payer-held state.

That is the prerequisite for a meaningful X12 270/271 exchange.

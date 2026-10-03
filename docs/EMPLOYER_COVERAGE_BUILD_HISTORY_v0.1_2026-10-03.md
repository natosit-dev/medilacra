# Employer Coverage MVP — Build History

**Version:** 0.1  
**Date:** 2026-10-03  
**Branch:** `experiment/employer-coverage`  
**Design:** `docs/EMPLOYER_COVERAGE_BUILD_DESIGN_v0.1_2026-10-03.md`

---

# Build Objective

Materialize the employer-coverage design as a working vertical slice:

```text
reference YAML
      |
      v
deterministic assignment
      |
      v
CoverageProfile
      |
      +--> Patient compatibility
      +--> Transaction compatibility
      +--> DuckDB
      '--> HL7 IN1 / IN2
```

The build deliberately stops before prior-authorization policy logic. CoverageProfile is the primitive that later prior-auth work will consume.

---

# Build Sequence

## 1. Design materialized

Created:

`docs/EMPLOYER_COVERAGE_BUILD_DESIGN_v0.1_2026-10-03.md`

The design captured prompt lineage, the four-YAML split, deterministic namespaced randomness, CoverageProfile ownership, DuckDB grain, compatibility behavior, HL7 intent, tests, and explicit non-goals.

## 2. Reference and configuration data

Created:

```text
data/coverage/employers.yaml
data/coverage/payers.yaml
data/coverage/plans.yaml
data/coverage/assignment.yaml
```

Employer fixture set:

```text
Walmart
Amazon
Home Depot
Target
Kroger
FedEx
UPS
HCA Healthcare
CVS Health
Starbucks
```

Starbucks intentionally replaces Berkshire Hathaway for a more immediately legible business type.

Payer fixture set:

```text
UnitedHealthcare
Aetna
Cigna Healthcare
Kaiser Permanente
Blue Cross Blue Shield
```

MVP plan set:

```text
STANDARD_PPO
STANDARD_HMO
```

The payer file also preserves two real-world plan examples per payer as documentation-only reference material. Assignment code does not consume those actual-plan references.

## 3. CoverageProfile added to the existing model layer

Added `CoverageProfile` to `hl7_demo/models.py`, beside the existing:

```text
Patient
Encounter
Observation
Transaction
```

The model records:

- patient;
- employer;
- payer;
- synthetic plan;
- worker profile;
- subscriber relationship;
- member/group/policy identifiers;
- effective period;
- provenance;
- deterministic assignment seed.

`Patient.coverage_profile` was added as an optional reference.

The existing `Patient.employer` field was retained for compatibility.

## 4. Deterministic assignment module

Created:

`hl7_demo/coverage.py`

Primary API:

```python
load_coverage_config(...)
assign_coverage_profile(patient, seed=...)
```

Assignment receives an isolated random stream derived from:

```text
SHA-256(global seed | patient ID | "coverage")
```

The code does not depend on global random state.

This means unrelated additions to lab, demographic, encounter, or other generators do not silently reshuffle an existing patient's employer/payer/plan assignment.

YAML record IDs are sorted before selection so mere YAML reordering also does not alter assignments.

## 5. CoverageProfile made authoritative for compatibility fields

When a profile is assigned:

```python
patient.employer = coverage_profile.employer_name
patient.coverage_profile = coverage_profile
```

`gen_transaction()` now accepts an optional CoverageProfile.

When supplied, Transaction inherits:

- plan ID;
- plan name;
- member ID;
- group number;
- plan type;
- subscriber relationship.

When no CoverageProfile is supplied, legacy random-insurance behavior remains available for backward compatibility.

Authorization number remains independent and is not treated as part of the coverage primitive.

## 6. DuckDB persistence

Added:

`coverage_profiles`

to the existing DuckDB schema.

Storage grain:

> one row = one CoverageProfile assigned to one synthetic patient for one effective period.

`patient_id` is indexed but deliberately not unique. The schema can therefore support future coverage history without migration from a one-coverage-per-patient design.

Added:

`upsert_coverage_profile()`

using the same writer/upsert style as the existing entity storage module.

Reference YAML is not copied to DuckDB. YAML describes what can be generated; DuckDB stores what was instantiated.

## 7. Pipeline integration

Two active generation paths were found during implementation.

### Main pipeline

`hl7_demo.pipeline.run_pipeline`

now performs:

```text
gen_patient
    |
assign_coverage_profile
    |
gen_encounter
    |
gen_transaction(coverage_profile)
    |
persist Patient + CoverageProfile + Encounter + Transaction + Observation
    |
build messages
```

### Generate & Persist pipeline

`pipeline_duckdb.run_and_persist`

is used separately by the Streamlit Generate & Persist page, so it was integrated as well.

Both paths now materialize the same coverage primitive instead of producing divergent insurance realities.

## 8. HL7 projection

Repository inspection showed the existing project already had usable IN1 plumbing, so the build extended through the projection layer rather than stopping immediately before it.

Coverage-aware IN1 now populates:

```text
IN1-2   Insurance Plan ID
IN1-3   Insurance Company ID
IN1-4   Insurance Company Name
IN1-8   Group Number
IN1-11  Insured's Group Employer Name
IN1-12  Plan Effective Date
IN1-13  Plan Expiration Date
IN1-15  Plan Type
IN1-16  Name of Insured
IN1-17  Insured's Relationship to Patient
IN1-49  Insured's ID Number
```

`IN1-14 Authorization Information` is intentionally blank.

Added minimal IN2 projection:

```text
IN2-3   employer_id ^ employer_name
```

This is deliberately the person-shaped employer field selected for the experiment.

ADT and DFT use the patient's established CoverageProfile when present.

## 9. Tests

Added:

```text
tests/test_coverage.py
tests/test_coverage_storage.py
```

Coverage tests verify:

- 10 employer fixtures;
- Starbucks included / Berkshire excluded;
- 5 payer fixtures;
- 2 synthetic plan primitives;
- 2 documented future plan references per payer;
- deterministic assignment;
- global RNG isolation;
- provenance;
- patient compatibility projection;
- transaction compatibility projection;
- IN1 fields;
- blank IN1-14;
- IN2-3 employer projection.

Storage tests verify:

- `coverage_profiles` table creation;
- round-trip persistence;
- multiple coverage periods for one patient;
- deterministic replacement by coverage_profile_id.

## 10. CI validation

Added a feature-branch GitHub Actions workflow that installs the project and executes:

```text
pytest -q
```

Validated result after both generation pipelines were integrated:

```text
21 passed, 1 warning
```

The warning is an unrelated pre-existing escape-sequence deprecation warning in `hl7_demo/utils.py`.

## 11. Diff hygiene

The GitHub editing path initially normalized four CRLF Python files to LF, producing noisy whole-file diffs.

The existing line-ending convention was restored before handoff.

Final logical diffs are limited to the intended changes.

---

# Important Design Decisions Preserved

| Decision | Materialized behavior |
|---|---|
| CoverageProfile is the primitive | one patient-level object owns coverage context |
| Two synthetic plans total | STANDARD_PPO and STANDARD_HMO only |
| Real plans are future reference | documented under payer metadata; ignored by assignment |
| Employer/payer relationship is not asserted as fact | provenance explicitly marks it synthetic |
| Coverage RNG is isolated | deterministic SHA-256-derived local random stream |
| Patient.employer remains | compatibility projection from CoverageProfile |
| Transaction insurance remains | compatibility projection from CoverageProfile |
| IN1-14 deferred | left blank in coverage-aware HL7 |
| Corporate employer remains visible in person-shaped field | employer projected to IN2-3 |
| DuckDB stores instantiated reality | reference YAML remains outside the DB |
| Coverage history remains possible | patient_id is not unique in coverage_profiles |

---

# Deferred Work

Still intentionally deferred:

- state-specific employer pools;
- employer-to-payer factual research;
- actual benefit design;
- payer-specific generation products;
- coverage enrollment lifecycle;
- secondary insurance;
- Medicare / Medicaid / uninsured scenarios;
- deductibles, copays, networks, formularies;
- prior-auth rules;
- AuthorizationCase lifecycle;
- Da Vinci PAS;
- coverage UI controls.

The next layer can consume CoverageProfile rather than reopening the assignment model.

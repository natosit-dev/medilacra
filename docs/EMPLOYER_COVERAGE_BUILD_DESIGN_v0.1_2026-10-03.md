# Employer Coverage MVP — Build Design

**Version:** 0.1  
**Date:** 2026-10-03  
**Branch:** `experiment/employer-coverage`  
**Status:** Build design / implementation-ready  
**Parent planning doc:** `docs/EMPLOYER_COVERAGE_PROJECT_PLAN_v0.1_2026-10-03.md`

---

# Prompt and Decision Lineage

> "She might like my next idea for Medilacra - for each state, add the top 10 employers to the synthetic patient. Use it to track coverage of an average employee. That feeds into my upcoming work with SHN pre authorization"

> "Let's do a gap analysis to MVP. We can make up most of the coverage/plan info and look it up later. Or make it configurable"

> "Let's see a full Nat style project plan. I want to understand what you're proposing"

> "Create a new branch and add this as the planning doc, full relevant prompt history at the top"

> "Let's swap out Berkshire Hathaway for Starbucks. Makes it easier to understand the business type."

> "No, let's use IN1:3 for the employer name. Corporations are legally people, right? 😅 The record shouldn't obscure that."

**Clarification retained in design:** HL7 v2 `IN1-3` is Insurance Company ID. The person-shaped employer field under discussion is `IN2-3` (Insured's Employer's Name and ID). This build uses `IN2-3` for employer projection and keeps `IN1-3` for payer/insurance company ID.

> "We should use Coverage Profile, that's the primitive"

> "We should also create a list of 5 insurance companies and 2 plans each."

> "Don't get fancy with the plan types. 2 total plans, each has the same one. Document the actual plans though for later use . For MVP we don't need that complexity. Agree we don't need IN1:14 yet."

> "Let's see a plan for the yaml files and the function to assign them to synthetic patients"

> "Where will the assignment functions reside?"

Decision: assignment code lives in `hl7_demo/coverage.py`; YAML source/configuration lives in `data/coverage/`; the `CoverageProfile` dataclass lives with the existing Patient/Encounter/Observation/Transaction dataclasses in `hl7_demo/models.py`.

> "Define RNG"

Decision: coverage assignment uses a patient-specific, namespaced deterministic random number generator so unrelated generator changes do not silently reshuffle coverage.

> "Where will the data be stored in duckdb?"

Decision: YAML remains reference/configuration data. Instantiated coverage profiles are persisted in `data/medilacra.duckdb` in a new `coverage_profiles` table.

> "CoverageProfile itself in hl7_demo/models.py — Yes that's fine if all the other classes are there."

Repository inspection confirmed `hl7_demo/models.py` currently contains the core `Patient`, `Encounter`, `Observation`, and `Transaction` dataclasses. It also confirmed that `Patient` already has an `employer` string and `Transaction` already contains insurance fields. This build makes CoverageProfile authoritative while preserving those existing fields as compatibility projections.

---

# 1. Build Purpose

This build turns existing employer and insurance placeholders into one coherent, deterministic patient-level object:

```text
Patient
   |
   v
CoverageProfile
   |-- employer
   |-- payer
   |-- synthetic plan
   |-- worker profile
   |-- member/group/policy identifiers
   |-- effective dates
   '-- provenance
```

The CoverageProfile is the MVP primitive.

It is deliberately smaller than the longer-term employment/coverage ontology. There is no separate CoverageEnrollment object in this build.

The purpose is to establish one stable coverage context that existing Patient, Transaction, DuckDB, and later HL7/prior-auth code can consume.

---

# 2. Existing Code Being Reused

The build reuses rather than replaces:

- `hl7_demo/models.py`
  - `Patient`
  - `Encounter`
  - `Observation`
  - `Transaction`
- `hl7_demo/generators.py`
  - existing patient generation
  - existing transaction generation
  - existing employer placeholder
  - existing insurance placeholder fields
- `storage_duckdb_entities.py`
  - current DDL/upsert pattern
- `utils/db.py`
  - existing `data/medilacra.duckdb` path and reader/writer helpers
- existing pipeline code
  - patient generation remains a separate step from coverage assignment

No new storage engine, graph database, or generalized ontology framework is introduced.

---

# 3. File Layout

```text
hl7_demo/
    models.py                   # add CoverageProfile
    coverage.py                 # new assignment/configuration module
    generators.py               # consume CoverageProfile where appropriate

data/
    coverage/
        employers.yaml
        payers.yaml
        plans.yaml
        assignment.yaml

storage_duckdb_entities.py      # add coverage_profiles DDL + upsert

tests/
    test_coverage.py
    test_storage_duckdb_entities.py   # extend existing coverage
```

Potential later files, explicitly outside this first build:

```text
hl7_demo/messages.py            # IN1/IN2 projection
prior authorization module
UI controls
state-specific employer pools
```

The MVP first proves generation, persistence, and compatibility.

---

# 4. Reference YAML Design

## 4.1 employers.yaml

Contains the ten large U.S. employer fixtures selected for the experiment:

1. Walmart
2. Amazon
3. Home Depot
4. Target
5. Kroger
6. FedEx
7. UPS
8. HCA Healthcare
9. CVS Health
10. Starbucks

Berkshire Hathaway is intentionally excluded in favor of Starbucks because the business type is easier to understand in demonstrations.

Each employer record should contain:

```yaml
WALMART:
  name: Walmart Inc.
  display_name: Walmart
  business_type: general_retail

  workforce:
    us_employee_count: 1600000
    selection_weight: 1.0

  hl7:
    employer_name_field: IN2-3

  provenance:
    status: researched
    as_of: 2026
    source: <reference URL>
```

`selection_weight` is separate from `us_employee_count` so the assignment strategy can change without changing source data.

For MVP assignment, employer selection will default to uniform unless assignment configuration specifies otherwise.

---

## 4.2 payers.yaml

Five payer brands:

```text
UHC
AETNA
CIGNA
KAISER
BCBS
```

Each payer contains the fields needed for generated coverage plus a non-executing documentation section for real-world plans:

```yaml
AETNA:
  name: Aetna

  hl7:
    insurance_company_id: AETNA
    insurance_company_name: Aetna

  actual_plan_references:
    status: documented_for_future_use
    plans:
      - name: <actual documented product/family>
        source: <URL>
```

**Important:** `actual_plan_references` is documentation only. Generation code must not consume it.

This lets the repository preserve real plan research without introducing real-world benefit complexity into the MVP.

---

## 4.3 plans.yaml

Exactly two synthetic plan primitives shared by all payers:

```yaml
STANDARD_PPO:
  name: Standard PPO
  plan_type: PPO
  provenance:
    status: synthetic

STANDARD_HMO:
  name: Standard HMO
  plan_type: HMO
  provenance:
    status: synthetic
```

No payer-specific plan classes.

No EPO/OAP/HDHP branching in MVP.

The actual payer product names remain documentation in `payers.yaml`.

---

## 4.4 assignment.yaml

Controls simulation behavior rather than entity facts.

```yaml
version: 0.1

assignment:
  employer:
    strategy: uniform

  payer:
    strategy: uniform

  plan:
    strategy: uniform

  defaults:
    worker_profile: DEFAULT_FULL_TIME_EMPLOYEE
    subscriber_relationship: SELF

  generated_identifiers:
    member_id_prefix: MEM
    group_number_prefix: GRP
    policy_number_prefix: POL

  effective_period:
    duration_days: 365
```

Assignment strategy is configurable, but MVP implements only the strategies required by this file.

---

# 5. CoverageProfile Model

Add to `hl7_demo/models.py`:

```python
@dataclass
class CoverageProfile:
    coverage_profile_id: str
    patient_id: str

    employer_id: str
    employer_name: str

    payer_id: str
    payer_name: str

    plan_id: str
    plan_name: str
    plan_type: str

    worker_profile: str
    subscriber_relationship: str

    member_id: str
    group_number: str
    policy_number: str

    effective_start: str
    effective_end: str

    employer_provenance: str
    payer_provenance: str
    employer_payer_provenance: str
    plan_provenance: str

    assignment_seed: str
```

The model intentionally duplicates human-readable names beside identifiers. MediLacra already uses that pattern elsewhere, and it keeps generated artifacts inspectable.

---

# 6. Deterministic RNG Design

Coverage assignment gets its own random stream.

Input:

```text
global seed
+ patient_id
+ namespace "coverage"
```

Derive a stable integer with a cryptographic hash rather than Python's process-randomized `hash()`.

Conceptually:

```python
digest = sha256(f"{seed}|{patient_id}|coverage".encode()).digest()
coverage_seed = int.from_bytes(digest[:8], "big")
rng = random.Random(coverage_seed)
```

This ensures:

- same patient + same seed => same assignment;
- adding a new lab/random demographic call elsewhere does not change coverage;
- coverage tests are reproducible;
- assignment provenance can record the derived seed.

Do not call `random.seed()` globally.

---

# 7. Assignment Module

New module:

```text
hl7_demo/coverage.py
```

Public API:

```python
load_coverage_config(...)
assign_coverage_profile(patient, seed=...)
```

Internal helpers:

```python
_make_coverage_rng(...)
_select_employer(...)
_select_payer(...)
_select_plan(...)
_generate_identifier(...)
_generate_effective_period(...)
```

Primary call:

```python
profile = assign_coverage_profile(
    patient=patient,
    seed=seed,
)
```

Assignment sequence:

```text
Patient
  |
  v
coverage-specific deterministic RNG
  |
  +--> choose employer
  |
  +--> choose payer
  |
  +--> choose Standard PPO or Standard HMO
  |
  +--> assign default worker profile
  |
  +--> generate member ID
  |
  +--> generate group number
  |
  +--> generate policy number
  |
  +--> generate effective period
  |
  v
CoverageProfile
```

---

# 8. Existing Patient and Transaction Compatibility

## Patient

`Patient.employer` currently exists and is generated independently.

Do not delete the field in this build.

Instead, after assignment:

```python
patient.employer = coverage_profile.employer_name
```

This makes CoverageProfile authoritative while preserving existing consumers.

The old random employer helper can remain temporarily for backward compatibility with code paths that do not yet assign coverage, but the coverage-enabled pipeline must overwrite it from CoverageProfile.

## Transaction

`Transaction` already includes:

- insurance_plan_id
- insurance_plan_name
- member_id
- group_number
- plan_type
- subscriber_relationship
- authorization_number

Coverage-enabled transaction generation should consume the CoverageProfile values for all applicable fields rather than independently inventing insurance facts.

`authorization_number` remains outside this build's coverage assignment logic; no IN1-14 or prior-authorization workflow is introduced yet.

---

# 9. DuckDB Design

Existing default database:

```text
data/medilacra.duckdb
```

YAML is not copied into DuckDB.

DuckDB stores instantiated synthetic reality.

Add:

```sql
CREATE TABLE IF NOT EXISTS coverage_profiles (
    coverage_profile_id TEXT PRIMARY KEY,
    patient_id TEXT,

    employer_id TEXT,
    employer_name TEXT,

    payer_id TEXT,
    payer_name TEXT,

    plan_id TEXT,
    plan_name TEXT,
    plan_type TEXT,

    worker_profile TEXT,
    subscriber_relationship TEXT,

    member_id TEXT,
    group_number TEXT,
    policy_number TEXT,

    effective_start DATE,
    effective_end DATE,

    employer_provenance TEXT,
    payer_provenance TEXT,
    employer_payer_provenance TEXT,
    plan_provenance TEXT,

    assignment_seed TEXT,

    created_ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

Grain:

> one row = one CoverageProfile assigned to one synthetic patient for one effective period.

Do **not** enforce patient uniqueness. Later coverage history should be possible without schema replacement.

Add `upsert_coverage_profile()` using the same short-lived writer/transaction style as the existing entity upserts.

---

# 10. HL7 Field Intent

HL7 projection is documented here but is **not required for the first implementation pass**.

Expected projection:

| CoverageProfile value | HL7 v2 field |
|---|---|
| payer ID | IN1-3 Insurance Company ID |
| payer name | IN1-4 Insurance Company Name |
| group number | IN1-8 Group Number |
| employer name | IN1-11 Insured's Group Employer Name |
| effective start | IN1-12 Plan Effective Date |
| effective end | IN1-13 Plan Expiration Date |
| plan type | IN1-15 Plan Type |
| patient name | IN1-16 Name of Insured |
| SELF | IN1-17 Insured's Relationship to Patient |
| worker profile/full-time projection | IN1-42 Insured's Employment Status |
| member ID | IN1-49 Insured's ID Number |
| employer name/ID | IN2-3 Insured's Employer's Name and ID |

`IN1-14 Authorization Information` is explicitly deferred.

The deliberate `IN2-3` employer projection is retained rather than abstracting the corporate employer into only the organization-shaped alternative field.

---

# 11. Tests

## Configuration tests

- all four YAML files load;
- exactly ten employers exist;
- exactly five payers exist;
- exactly two synthetic plans exist;
- every payer contains documentation-only actual plan references;
- plan IDs are unique;
- employer/payer IDs are unique.

## Determinism tests

For one fixed Patient:

```text
assign(patient, seed=42)
==
assign(patient, seed=42)
```

A different seed may produce a different profile.

## Isolation test

Coverage RNG must be independent of global random state.

Changing/calling Python's global `random` stream before coverage assignment must not alter the coverage result.

## Model/provenance tests

Generated profile contains:

- employer;
- payer;
- plan;
- member/group/policy IDs;
- effective dates;
- researched provenance for source institutions;
- synthetic provenance for employer-payer relationship and plan;
- assignment seed.

## Storage tests

- `init_db()` creates `coverage_profiles`;
- `upsert_coverage_profile()` inserts a row;
- same `coverage_profile_id` can be replaced deterministically;
- same patient can have multiple coverage profiles with different profile IDs/effective periods.

## Compatibility tests

- patient employer is updated from CoverageProfile in the coverage-enabled path;
- Transaction insurance fields can be populated from CoverageProfile;
- authorization number remains independent.

---

# 12. First Completion Target

A minimal executable path should be able to generate patients such as:

```text
Patient 001
Employer: Starbucks
Payer: Aetna
Plan: Standard PPO

Patient 002
Employer: Amazon
Payer: Blue Cross Blue Shield
Plan: Standard HMO

Patient 003
Employer: Walmart
Payer: UnitedHealthcare
Plan: Standard PPO
```

Then rerun with the same patient identifiers and seed and receive the same results.

Those profiles must persist to DuckDB.

The build is complete when this behavior is covered by tests and existing tests remain green.

---

# 13. Explicit Non-Goals

Not part of this build:

- state-specific top-10 employer pools;
- accurate employer-to-payer contracting;
- actual benefit design;
- payer-specific synthetic plan types;
- prior-authorization rules;
- IN1-14;
- full IN1/IN2 message projection;
- enrollment lifecycle;
- secondary insurance;
- Medicare/Medicaid/uninsured logic;
- deductible/copay/network modeling;
- UI controls;
- Da Vinci PAS.

Those are later layers. This build establishes the primitive they can consume.

---

# 14. Definition of Done

1. Build design is durable in Git.
2. Four coverage YAML files exist.
3. Ten employer fixtures exist, with Starbucks replacing Berkshire Hathaway.
4. Five payer fixtures exist.
5. Actual payer plan examples are documented for later use and ignored by generation.
6. Exactly two synthetic plan primitives exist for all payers.
7. `CoverageProfile` lives in `hl7_demo/models.py`.
8. Coverage assignment lives in `hl7_demo/coverage.py`.
9. Assignment is deterministic per patient/seed/coverage namespace.
10. CoverageProfile becomes authoritative for employer/insurance values in the coverage-enabled path.
11. DuckDB persists generated profiles in `coverage_profiles`.
12. Tests prove deterministic generation, RNG isolation, configuration validity, persistence, and compatibility.
13. Existing tests remain green.
14. No prior-auth logic or IN1-14 is introduced.

# Employer Coverage Reality Slice — Project Plan

**Version:** 0.1  
**Date:** 2026-10-03  
**Branch:** `experiment/employer-coverage`  
**Status:** Planning / ready for implementation  
**Project:** MediLacra  
**Purpose:** Make employment and insurance context part of synthetic reality so the same clinical patient can experience different prior-authorization conditions depending on institutional context.

---

# Relevant Prompt History

## Origin — 2026-10-02

> She might like my next idea for Medilacra - for each state, add the top 10 employers to the synthetic patient. Use it to track coverage of an average employee. That feeds into my upcoming work with SHN pre authorization

## MVP framing — 2026-10-02

> Let's do a gap analysis to MVP. We can make up most of the coverage/plan info and look it up later. Or make it configurable

## Planning request — 2026-10-02

> Let's see a full Nat style project plan. I want to understand what you're proposing

## Materialization request — 2026-10-03

> Create a new branch and add this as the planning doc, full relevant prompt history at the top

---

# 1. Project Thesis

The initial idea sounds simple:

> For each state, add the top 10 employers to the synthetic patient. Use it to track coverage of an average employee. Feed that into upcoming SHN prior-authorization work.

The important architectural move is **not** to turn `Patient` into a row with `employer_name`, `payer_name`, and `plan_type` attached.

The useful model is the institutional system around the person:

```text
PERSON
  |
  |-- lives in ----------------> STATE
  |
  '-- has employment ----------> EMPLOYER
                                   |
                                   '-- coverage context
                                          |
                                          |-- PAYER
                                          |-- PLAN
                                          |-- FUNDING ARRANGEMENT
                                          '-- PRIOR AUTH POLICY
                                                   |
                                                   v
                                           REQUESTED SERVICE
                                                   |
                                                   v
                                          AUTH REQUIREMENT
```

This gives MediLacra a new experimental axis:

> **Hold the human and clinical need constant. Change the institutional context. Observe what happens to access.**

That is the actual experiment.

---

# 2. Why This Belongs in MediLacra

MediLacra already has most of the machinery needed for this:

- Patient, Encounter, Observation, and Transaction already exist.
- Geography already exists.
- Organizations/facilities already exist conceptually in scenario configuration.
- DuckDB already persists cross-entity relationships.
- Scenario profiles already act as a primitive world model.
- The emerging Reality Model is explicitly about shared facts and relationships instead of downstream builders inventing facts.

The broader Reality Model direction is:

```text
CURRENT

entity generator
    |
    v
dataclass
    |
    v
HL7 builder
```

becoming:

```text
TARGET

semantic requirement
    |
    v
generator / existing fact / relationship
    |
    v
shared reality state
    |
    v
existing dataclasses + pipelines
```

Employer coverage is a strong first vertical slice because it immediately requires MediLacra to understand:

- independently existing entities,
- relationships between those entities,
- shared institutional context,
- persistent facts,
- configuration,
- provenance,
- and downstream workflows that consume those facts.

Instead of building `RealityContext` abstractly, this project gives it something concrete to do.

---

# 3. MVP Definition

The MVP is **not**:

> Accurately reproduce the employee health benefits of the ten largest employers in all fifty states.

That is a later research/data-loading problem.

The MVP is:

> **MediLacra can generate a synthetic person with an employment relationship and a configurable insurance context, then use that context to answer a simple prior-authorization question.**

Initially:

- employer lists can be tiny fixtures,
- employer names can later become real,
- coverage can be synthetic,
- plans can be configurable,
- prior-authorization policy can be deliberately simple,
- provenance must distinguish synthetic/configured/researched/verified information.

The architecture should not care whether the data is synthetic today and researched later.

---

# 4. Core Design Rule

The Reality Model boundary is:

> **Nothing downstream is allowed to invent reality.**

Wrong:

```python
def build_prior_auth(patient):
    payer = random_payer()
    plan = random_plan()
    employer = random_employer()
```

Right:

```python
patient = reality.patient(...)
employment = reality.employment_for(patient)
coverage = reality.coverage_for(patient)

build_prior_auth(
    patient=patient,
    coverage=coverage,
)
```

The prior-auth workflow does not decide where the patient works.

The FHIR builder does not decide what plan they have.

The output layer does not decide whether the employer self-funds.

Those facts already exist in the generated reality.

---

# 5. Minimum Ontology

The MVP needs a small number of explicit concepts.

## 5.1 Organization

Use one institutional object for multiple roles.

```text
Organization
    organization_id
    name
    organization_type
    state
    metadata
```

Initial roles:

```text
EMPLOYER
PAYER
TPA
PROVIDER
HEALTH_SYSTEM
GOVERNMENT
OTHER
```

Do not create separate Employer/Payer/Hospital classes unless their behavior later demands it.

They are organizations playing different roles.

---

## 5.2 Employment

Employment is a relationship, not a Patient property.

```text
Employment
    employment_id

    person_id
    employer_organization_id

    worker_profile
    status

    start_date
    end_date

    source
    provenance
```

Example:

```text
Employment EMP-00912

Person:
    PERSON-1734

Employer:
    ORG-WALMART

Worker profile:
    FULL_TIME_HOURLY

Status:
    active
```

This allows one human to change employers over time without changing identity.

---

# 6. Worker Profiles

The original phrase was "average employee."

Do not encode that literally.

There is no coherent generic average worker. Instead, create a named experimental archetype:

```text
DEFAULT_FULL_TIME_EMPLOYEE
```

Later:

```text
FULL_TIME_HOURLY
FULL_TIME_SALARIED
PART_TIME
SEASONAL
UNION
DEPENDENT_ONLY
COBRA
RETIREE
```

These are simulation assumptions, not claims about any employer.

MVP configuration:

```yaml
worker_profile:
  id: DEFAULT_FULL_TIME_EMPLOYEE
  employment_status: full_time
  hours_per_week: 40
```

---

# 7. Coverage Has Two Layers

Separate the reusable rule/configuration from the instantiated fact.

```text
CoverageProfile
      |
      | instantiate
      v
CoverageEnrollment
      |
      '-- covers PERSON-1734
```

## 7.1 CoverageProfile

A reusable configuration/template.

```text
CoverageProfile
    profile_id

    employer_id
    worker_profile

    payer_id
    plan_name
    plan_type
    funding_type
    network_type

    prior_auth_policy_id

    provenance
```

Example:

```yaml
id: EMPLOYER_001_SYNTHETIC_DEFAULT

employer: ORG_EMPLOYER_001
worker_profile: DEFAULT_FULL_TIME_EMPLOYEE

payer: ORG_SYNTHETIC_PAYER_01

plan:
  name: Synthetic Large Employer PPO
  type: PPO

funding:
  type: self_funded

prior_auth_policy:
  id: DEFAULT_SYNTHETIC_PA

provenance:
  status: synthetic
```

## 7.2 CoverageEnrollment

The actual coverage attached to a synthetic person.

```text
CoverageEnrollment
    coverage_id

    person_id
    subscriber_id
    group_number
    member_number

    payer_id
    employer_id
    coverage_profile_id

    effective_start
    effective_end
```

This keeps "the rule for generating the world" distinct from "the thing that exists in the generated world."

---

# 8. Provenance Is Mandatory

This project may eventually combine:

- real employer names,
- synthetic plan information,
- researched payer information,
- verified policy information.

Without provenance, synthetic information can silently become false factual claims.

Use an explicit status vocabulary:

```text
SYNTHETIC
CONFIGURED
RESEARCHED
VERIFIED
```

Example:

```yaml
provenance:
  status: synthetic
  source: medilacra
  note: >
    Synthetic coverage scenario for interoperability
    and workflow testing. Not an assertion about
    actual employee benefits.
```

Later:

```yaml
provenance:
  status: researched
  source:
    url: ...
    accessed: 2026-11-04
```

Eventually:

```yaml
provenance:
  status: verified
  effective_year: 2027
```

The software should behave the same regardless.

---

# 9. Employer Data Strategy

Eventually:

```text
50 states x top 10 employers
~500 employer/state entries
```

That is content, not architecture.

Do not start there.

Start with one state and a deliberately tiny fixture set:

```yaml
MA:
  - id: EMPLOYER_MA_001
    name: Example Employer One
    selection_weight: 0.40

  - id: EMPLOYER_MA_002
    name: Example Employer Two
    selection_weight: 0.35

  - id: EMPLOYER_MA_003
    name: Example Employer Three
    selection_weight: 0.25
```

Prove:

```text
patient.address.state
        |
        v
state employer pool
        |
        v
employer selection
        |
        v
employment
        |
        v
coverage profile
        |
        v
coverage enrollment
```

Once this works, loading 500 rows should be boring.

Boring is good.

---

# 10. Employer Selection Is Contextual Generation

The semantic relationship is:

```text
person.state
    |
    v
employer_pool(state)
    |
    v
employment.employer
```

Not:

```text
patient.employer = faker.company()
```

This is exactly the distinction the Reality Model is trying to introduce: context is part of shared world state, not a one-off random value generated by whichever function happens to need it.

---

# 11. Prior Authorization Policy

Do not implement full payer-policy interpretation in the MVP.

Start with inspectable configuration:

```yaml
prior_auth_policy:
  id: SYNTH_PA_001

  rules:

    MRI:
      required: true

    CT:
      required: true

    PHYSICAL_THERAPY:
      required: true

    PRIMARY_CARE:
      required: false

    LAB_CBC:
      required: false
```

Then:

```python
evaluate_prior_auth(
    coverage,
    requested_service,
)
```

returns something like:

```json
{
  "required": true,
  "policy_id": "SYNTH_PA_001",
  "service": "MRI",
  "coverage_id": "COV-92881"
}
```

No machine learning.

No LLM policy interpretation.

No full payer policy corpus.

Just a transparent rule.

---

# 12. AuthorizationCase

Introduce a lightweight authorization object early so the experiment can grow directly into SHN-related prior-auth work.

```text
AuthorizationCase

authorization_id
person_id
coverage_id
payer_id
service_request_id

required
status

requested_datetime
decision_datetime

outcome
reason
```

MVP can stop at:

```text
status = DETERMINED
required = TRUE
```

Later the lifecycle can become:

```text
NEEDS_AUTH
    |
    v
SUBMITTED
    |
    v
PENDING
    |
    +--> APPROVED
    |
    '--> DENIED
```

---

# 13. Relationship Graph

The generated reality becomes:

```text
Person
|
|-- address ------------------------> Massachusetts
|
|-- employment ---------------------> Employer
|                                        |
|                                        '-- Organization
|
|-- coverage enrollment
|       |
|       |-- employer ----------------> Employer
|       |-- payer -------------------> Payer Organization
|       '-- profile -----------------> CoverageProfile
|                                           |
|                                           '-- PriorAuthPolicy
|
'-- encounter
        |
        '-- service request
                   |
                   v
             AuthorizationCase
                   |
                   |-- person
                   |-- coverage
                   |-- payer
                   '-- requested service
```

The project is about building edges, not decorating rows.

---

# 14. RealityContext Integration

The emerging RealityContext should hold:

```text
RealityContext

entities
facts
identities
relationships
events
seed
scenario
```

Its job is:

> If a fact already exists, return it. Otherwise resolve dependencies, generate it once, and retain it.

Employer coverage gives that abstraction an immediate purpose.

Example:

```python
reality.get(person, "person.state")
```

returns:

```text
MA
```

Then:

```python
reality.get(person, "employment.employer")
```

resolves:

```text
person.state
-> employer pool
-> employer
```

Then:

```python
reality.get(person, "coverage.enrollment")
```

resolves:

```text
employment.employer
+ worker_profile
+ coverage_profile
-> enrollment
```

The same request must always return the same already-established fact.

Synthetic reality is not rerolled every time another subsystem asks a question.

---

# 15. Semantic Concepts to Add

```text
employment.identifier
employment.person
employment.employer
employment.worker_profile
employment.status
employment.start_date
employment.end_date

coverage.identifier
coverage.person
coverage.subscriber
coverage.employer
coverage.payer
coverage.plan_identifier
coverage.plan_name
coverage.plan_type
coverage.funding_type
coverage.network_type
coverage.effective_start
coverage.effective_end

authorization.identifier
authorization.person
authorization.coverage
authorization.payer
authorization.service
authorization.required
authorization.status
authorization.outcome
```

These become first concrete additions to the semantic registry.

---

# 16. Configuration Architecture

Initial structure:

```text
config/
    employers/
        MA.yaml

    worker_profiles.yaml

    coverage_profiles.yaml

    prior_auth_policies.yaml
```

Each file answers a different question.

### `MA.yaml`

What employers can exist in this geographic context?

### `worker_profiles.yaml`

What kind of employee are we simulating?

### `coverage_profiles.yaml`

What coverage context follows from employer + worker scenario?

### `prior_auth_policies.yaml`

What authorization rule set applies to that coverage?

Keep these separate rather than creating one giant insurance configuration file.

---

# 17. Example Complete Configuration

```yaml
# employers/MA.yaml

state: MA

employers:

  - id: ORG_EMP_001
    name: Synthetic Massachusetts Employer A
    organization_type: employer
    selection_weight: 0.40

  - id: ORG_EMP_002
    name: Synthetic Massachusetts Employer B
    organization_type: employer
    selection_weight: 0.35

  - id: ORG_EMP_003
    name: Synthetic Massachusetts Employer C
    organization_type: employer
    selection_weight: 0.25
```

```yaml
# worker_profiles.yaml

DEFAULT_FULL_TIME_EMPLOYEE:
  employment_status: full_time
  hours_per_week: 40
```

```yaml
# coverage_profiles.yaml

EMP_001_DEFAULT:
  employer: ORG_EMP_001
  worker_profile: DEFAULT_FULL_TIME_EMPLOYEE

  payer: ORG_PAYER_001

  plan:
    id: PLAN_001
    name: Synthetic PPO
    type: PPO

  funding_type: self_funded
  network_type: PPO

  prior_auth_policy: PA_POLICY_001

  provenance:
    status: synthetic
```

```yaml
# prior_auth_policies.yaml

PA_POLICY_001:

  MRI:
    required: true

  CT:
    required: true

  PRIMARY_CARE:
    required: false
```

That is enough data to run the first experiment.

---

# 18. Generation Flow

```text
SEED
 |
 v
Generate Person
 |
 v
Generate Geography
 |
 '-- State = MA
       |
       v
Resolve Employer Pool
       |
       v
Select Employer
       |
       v
Create Employment
       |
       v
Resolve Worker Profile
       |
       v
Resolve Coverage Profile
       |
       v
Create Coverage Enrollment
       |
       v
Generate Clinical Event
       |
       v
Requested Service
       |
       v
Evaluate Prior Auth Policy
       |
       v
Create Authorization Case
```

Every object is stored in the same shared reality.

---

# 19. DuckDB Persistence

Likely new tables:

```text
organizations
employments
coverage_profiles
coverage_enrollments
authorization_cases
```

Potentially:

```text
prior_auth_policies
```

though policies may remain config-only for the MVP.

Relationships:

```text
employments.person_id
    -> patients.patient_id

employments.employer_id
    -> organizations.organization_id

coverage_enrollments.person_id
    -> patients.patient_id

coverage_enrollments.employer_id
    -> organizations.organization_id

coverage_enrollments.payer_id
    -> organizations.organization_id

authorization_cases.coverage_id
    -> coverage_enrollments.coverage_id
```

No graph database is required.

---

# 20. UI

The MVP UI should be intentionally boring.

Add an optional panel to the existing generation workflow:

```text
Employment & Coverage

State:
[ Massachusetts ]

Employer:
[ Auto-select v ]

Worker profile:
[ Default Full-Time Employee v ]

Coverage:
[ Auto-select v ]

Requested service:
[ MRI v ]

[ Generate ]
```

Output:

```text
PATIENT

Morgan Rivera
DOB: 1984-07-12
State: MA


EMPLOYMENT

Employer:
Synthetic Massachusetts Employer A

Worker profile:
Default Full-Time Employee


COVERAGE

Payer:
Synthetic Health Plan

Plan:
Synthetic PPO

Funding:
Self-funded

Provenance:
Synthetic configuration


PRIOR AUTHORIZATION

Service:
MRI

Authorization required:
YES

Policy:
PA_POLICY_001
```

No dashboard is required.

The UI exists so a human can understand the experiment.

---

# 21. Manual Override

Generated context should support:

```text
AUTO
CONFIGURED
MANUAL
```

Example:

```text
Employer:
[ Massachusetts General Hospital ]

Coverage:
[ Custom ]

Payer:
[ Blue Cross ]

Funding:
[ Self-funded ]

MRI requires PA:
[ Yes ]
```

This makes the feature useful for implementation work before any real employer-benefit research exists.

The user can say, effectively:

> Pretend this employer uses this plan structure and run the workflow.

That is enough for implementation testing.

---

# 22. FHIR Projection

FHIR comes **after** the reality objects exist.

Minimum output:

```text
Patient
Organization -- employer
Organization -- payer
Coverage
```

Later, as needed:

```text
ServiceRequest
Claim / ClaimResponse
Task
QuestionnaireResponse
Prior-auth artifacts
```

The architectural constraint is:

```text
FHIR != reality
```

FHIR is one projection of an already-instantiated reality.

The employment relationship can remain a MediLacra relationship for the first cut if no clean FHIR representation is needed for the experiment.

---

# 23. HL7 v2 Is Out of Scope for MVP

Do not solve employer coverage in HL7 v2 as part of this experiment.

The central flow is:

```text
reality
    |
    v
FHIR / API / JSON / database / other projection
```

not:

```text
invent reality because an output field exists
```

---

# 24. Implementation Phases

## Phase 0 — Preserve the Experiment

This document is the initial durable artifact.

Branch:

```text
experiment/employer-coverage
```

Planning artifact:

```text
docs/EMPLOYER_COVERAGE_PROJECT_PLAN_v0.1_2026-10-03.md
```

Maintain subsequent:

- build history,
- decision log,
- prompt lineage,
- assumptions,
- definition of done.

---

## Phase 1 — Institutional Objects

Implement:

```text
Organization
Employment
CoverageProfile
CoverageEnrollment
```

Add tests for references and deterministic identifiers.

Success:

```text
Person P1
-> Employment E1
-> Organization O1
-> Coverage C1
-> Payer O2
```

exists coherently in memory.

---

## Phase 2 — Configuration

Implement:

```text
employers/MA.yaml
worker_profiles.yaml
coverage_profiles.yaml
prior_auth_policies.yaml
```

Validate:

```text
employer exists
payer exists
coverage profile references valid employer
PA policy exists
selection weights are legal
```

Success:

No hardcoded insurance logic is required to generate a coverage scenario.

---

## Phase 3 — State-Aware Employer Generation

Wire:

```text
person.state
-> employer pool
-> employer
-> employment
```

Use deterministic seed behavior.

Test:

```text
seed = 123
state = MA
```

always generates the same employer.

---

## Phase 4 — Coverage Generation

Wire:

```text
employment
+ worker profile
-> coverage profile
-> CoverageEnrollment
```

Generate synthetic:

```text
member ID
group ID
subscriber ID
effective dates
```

Persist to DuckDB.

---

## Phase 5 — Prior-Auth Evaluator

Add:

```python
evaluate_prior_auth(
    coverage,
    service,
)
```

Return:

```text
required
policy
rule
```

Then create `AuthorizationCase`.

No workflow engine yet.

---

## Phase 6 — RealityContext Integration

Register:

```text
employment.employer
coverage.enrollment
coverage.payer
coverage.plan
authorization.required
```

with the semantic layer.

Downstream systems retrieve rather than regenerate these facts.

---

## Phase 7 — Minimal UI

Expose:

```text
employment context
coverage context
requested service
authorization result
provenance
```

Support manual overrides.

---

## Phase 8 — FHIR Projection

Export:

```text
Patient
Organization
Organization
Coverage
```

Bundle coherently.

Validate references.

No facts may be invented during projection.

---

# 25. Testing Strategy

## Determinism

The same:

```text
seed
state
worker profile
```

produces the same institutional reality.

## Referential Integrity

Every:

```text
Employment.employer
Coverage.payer
Coverage.person
Authorization.coverage
```

points to something that exists.

## Configuration Isolation

Changing:

```yaml
MRI:
  required: true
```

to:

```yaml
MRI:
  required: false
```

must change the authorization result without changing code.

## Institutional Counterfactual

This is the important test.

Generate:

```text
Person P
Clinical condition C
Service MRI
```

Scenario A:

```text
Employer A
Coverage A
PA required
```

Scenario B:

```text
Employer B
Coverage B
PA not required
```

Assert:

```text
Person == same
Clinical condition == same
Requested service == same

Institutional context != same
Access requirement != same
```

That proves the experiment.

---

# 26. Demonstration Scenario

Start:

```text
Jamie Lee
Age 43
Massachusetts
Needs MRI
```

Reality A:

```text
Employer:
Employer A

Plan:
Synthetic PPO A

MRI:
Prior authorization required
```

Change employer/coverage only.

Reality B:

```text
Same human
Same symptoms
Same clinician
Same MRI

Employer:
Employer B

Plan:
Synthetic PPO B

MRI:
No prior authorization required
```

Nothing medical changed.

The bureaucracy did.

That is the conceptual payload.

---

# 27. Explicitly Out of Scope

Do not build any of these for the MVP:

- accurate employer-benefits research,
- full 50-state employer dataset,
- actual payer contracts,
- full provider network modeling,
- deductible calculation,
- actuarial modeling,
- eligibility engines,
- COBRA,
- ERISA interpretation,
- benefit accumulators,
- formulary logic,
- complete prior-auth workflow,
- full Da Vinci PAS implementation,
- claims adjudication,
- provider-network adequacy,
- cost estimation,
- real-time eligibility,
- payer API integration.

These can become later experiments.

None is required to answer:

> Can MediLacra represent employment-mediated insurance context and allow it to influence a healthcare workflow?

---

# 28. Important Assumptions

## Employer does not determine coverage by itself

The more correct causal model is:

```text
Person
+
Employment
+
Employer
+
Worker classification
+
Benefit offering
+
Enrollment decision
+
Time
----------------
Coverage
```

For MVP, much of this complexity is intentionally compressed into:

```text
CoverageProfile
```

That is deliberate compression and should be documented as such.

## Top ten employers is a sampling strategy, not an ontology

"Top ten employers by state" is useful because it gives:

- high-volume employment contexts,
- institutional variety,
- recognizable organizations,
- likely employer-sponsored coverage scenarios,
- an intuitive human demonstration.

It is not a scientifically representative model of the labor market.

Later employer-pool strategies might include:

```text
large employer
small employer
public employer
hospital system
university
retail
manufacturing
gig work
unemployed
self-employed
```

Therefore `top_10` should become one employer-pool strategy rather than an assumption baked into the model.

---

# 29. Expected File Layout

Approximate target:

```text
medilacra/
|
|-- reality/
|   |-- organizations.py
|   |-- employment.py
|   |-- coverage.py
|   '-- authorization.py
|
|-- config/
|   |-- employers/
|   |   '-- MA.yaml
|   |-- worker_profiles.yaml
|   |-- coverage_profiles.yaml
|   '-- prior_auth_policies.yaml
|
|-- generators/
|   |-- employment.py
|   '-- coverage.py
|
|-- fhir/
|   |-- organization.py
|   '-- coverage.py
|
|-- tests/
|   |-- test_employment.py
|   |-- test_coverage.py
|   |-- test_prior_auth.py
|   '-- test_institutional_counterfactual.py
|
'-- docs/
    |-- EMPLOYER_COVERAGE_PROJECT_PLAN_v0.1_2026-10-03.md
    |-- EMPLOYER_COVERAGE_DECISION_LOG.md
    '-- EMPLOYER_COVERAGE_BUILD_HISTORY.md
```

Exact names should follow repository conventions encountered during implementation.

---

# 30. Initial Decision Log

| Decision | Reason |
|---|---|
| Employment is a relationship, not Patient attribute | People change employers; employer exists independently |
| Employer and payer both use Organization | Avoid unnecessary entity proliferation |
| Separate CoverageProfile from CoverageEnrollment | Configuration is not instantiated reality |
| Insurance data may initially be synthetic | Architecture does not require research accuracy |
| Provenance is required | Prevent synthetic information becoming accidental factual claims |
| Worker archetype replaces "average employee" | Makes simulation assumptions explicit |
| PA rules live in configuration | Policy changes should not require code changes |
| Only Massachusetts is needed initially | 50-state data is content-loading work |
| RealityContext is introduced through this experiment | Concrete vertical slice is preferable to abstract framework work |
| FHIR is projection, not source of reality | Output schema should not determine ontology |
| No full PA workflow in first cut | Boolean/rule evaluation proves the core relationship |
| Manual configuration is supported | Makes the feature useful before research data exists |

---

# 31. Definition of Done

The MVP is complete when a clean run can do all of the following:

```text
1. Generate a synthetic Massachusetts person.

2. MediLacra assigns:
      employer
      employment
      worker profile

3. MediLacra resolves:
      coverage profile
      payer
      plan
      funding type

4. MediLacra creates:
      CoverageEnrollment

5. Generate/request:
      MRI

6. MediLacra evaluates:
      prior authorization = required

7. Change only:
      employer or coverage profile

8. Re-run:
      prior authorization = not required

9. Verify:
      person unchanged
      clinical facts unchanged
      service unchanged

10. Export:
      patient
      organizations
      coverage
      authorization result

11. Every synthetic/configured fact contains provenance.

12. Entire scenario reproduces from seed + configuration.
```

MVP is **not** 500 employer records.

It is **not** production payer policy.

It is **not** full Da Vinci prior auth.

It is:

> **One coherent synthetic human whose healthcare access changes when the institutional relationships around them change.**

---

# 32. Architectural Meaning

This project does three things at once.

**Technically:** it gives the Reality Model its first genuinely cross-domain institutional relationship.

**Operationally:** it creates infrastructure directly adjacent to upcoming SHN prior-authorization work.

**Conceptually:** it moves MediLacra another level away from synthetic healthcare records and toward synthetic healthcare reality.

The central architecture is:

```text
MediLacra does not model a patient.

MediLacra models a person interacting with systems.

The medical record is one output of those interactions.
Coverage is another.
Prior authorization is another.
```

That is the experiment.

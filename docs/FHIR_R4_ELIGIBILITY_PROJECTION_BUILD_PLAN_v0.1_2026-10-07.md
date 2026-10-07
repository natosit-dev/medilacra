# FHIR R4 Eligibility Projection Build Plan

**Version:** 0.1  
**Date:** 2026-10-07  
**Branch:** `experiment/employer-coverage`  
**Status:** Implementation-ready  
**Pre-build head:** `d582ee0ffd44ecb069b64c3a8d12eab9c3c2d9c5`

---

# 1. Purpose

Add FHIR R4 4.0.1 eligibility artifacts as a second projection of the same synthetic eligibility event already producing X12 270/271.

The new path must **not** convert X12 into FHIR.

Target architecture:

```text
Synthetic clinical + payer reality
              |
              v
      EligibilityInquiry
              |
        +-----+------+
        |            |
        v            v
      X12 270     FHIR R4
                  CoverageEligibilityRequest
              |
              v
         PayerSystem
              |
              v
     EligibilityResponse
              |
        +-----+------+
        |            |
        v            v
      X12 271     FHIR R4
                  CoverageEligibilityResponse
```

Both representations consume the same semantic inquiry, the same payer evaluation, the same service date, and the same exchange identity.

---

# 2. Prompt History / Design Lineage

> "Will X12 messages get generated in Disco Inferno? Right now the main generate and persist still pings an API even if all the sdoh/lab buttons are not checked, and I know we fixed that with inferno"

This exposed that the normal core generator still had hidden SDOH network behavior.

> "Yeah, that makes more sense. Go fix the core generator after you commit the last round of test results to an MD in docs"

The core generator was changed so external SDOH enrichment is opt-in and offline generation is the default.

> "K, that works. Next step- output the FHIR equivalent for each x12 message. What resources are needed in the bundle? What's the difference between versions?"

This established eligibility FHIR projection as the next representation layer.

The initial design conclusion was:

```text
X12 270 -> CoverageEligibilityRequest
X12 271 -> CoverageEligibilityResponse
```

with self-contained R4 bundles and independent clinical/payer institutional representations.

> "Let's do R4 4.0.1 first. Add the timestamp to the file name.
> We should be building it from the synthetic reality, not simply converting x12.
> Let's see a build plan"

This fixed the target version, artifact naming, and most important architectural constraint: FHIR is a direct projection of synthetic reality.

> "Commit to docs as the build plan, then go build it"

This document is the durable pre-build checkpoint.

---

# 3. Version Target

This build targets:

```text
FHIR R4
Version 4.0.1
```

No R4B or R5 compatibility layer is introduced in this round.

The implementation should make the version explicit in module names, tests, and output filenames.

---

# 4. Semantic Layer Before Representation

The existing scaled X12 path currently builds a 270, parses that 270 back into `EligibilityInquiry`, and then evaluates the payer response.

That should be replaced in the normal generation path.

Add a shared semantic helper:

```text
eligibility/generation.py
```

Primary function:

```python
build_eligibility_inquiry_from_clinical(
    patient,
    coverage_profile,
    encounter,
    requester_id,
) -> EligibilityInquiry
```

Normal flow becomes:

```text
Patient + CoverageProfile + Encounter
              |
              v
      EligibilityInquiry
              |
              +----> X12 270
              |
              +----> FHIR Request
              |
              v
          PayerSystem
              |
              v
      EligibilityResponse
              |
              +----> X12 271
              |
              '---> FHIR Response
```

The X12 parser remains as an independent test/validation tool.

The FHIR generator must not call:

```text
parse_270_to_inquiry()
```

or consume raw X12 strings.

---

# 5. Shared Exchange Identity

Add a shared run-scoped semantic exchange identity independent of X12 syntax.

Target primitives:

```text
EligibilityRunContext
EligibilityExchangeIdentity
```

Example identity:

```text
20261007182900-00001
```

Derived trace:

```text
TRACE-270-20261007182900-00001
```

The same semantic exchange identity should appear in:

- X12 trace/reference values;
- FHIR `CoverageEligibilityRequest.identifier`;
- FHIR `CoverageEligibilityResponse.identifier`.

X12 constrained control numbers remain representation-specific and continue to use the existing timestamp + incrementing numeric control allocator.

---

# 6. New FHIR Modules

Add:

```text
fhir/eligibility_r4.py
fhir/eligibility_generation.py
```

## `fhir/eligibility_r4.py`

Owns pure R4 4.0.1 resource construction:

- deterministic FHIR resource IDs;
- clinical Patient;
- payer Patient;
- requester Organization;
- payer Organization;
- employer Organization;
- clinical Coverage;
- payer Coverage;
- CoverageEligibilityRequest;
- CoverageEligibilityResponse;
- collection Bundle assembly.

## `fhir/eligibility_generation.py`

Owns:

- FHIR eligibility artifact dataclass;
- orchestration from semantic inquiry/response + institutional source objects;
- timestamped JSON / NDJSON output behavior.

Do not add this behavior to `fhir/fhir_convert_backend.py`.

That module remains the HL7-v2-to-FHIR converter.

---

# 7. Deterministic FHIR Resource IDs

Generate valid R4 `Resource.id` values deterministically from synthetic source identity.

Examples:

```text
pat-<hash>
pmem-<hash>
cov-<hash>
pcov-<hash>
org-<hash>
cerq-<hash>
cers-<hash>
bundle-<hash>
```

Requirements:

- only FHIR-safe characters;
- <= 64 characters;
- deterministic for the same synthetic source identity;
- no UUID randomness;
- no reuse of X12 control numbers as FHIR resource IDs.

---

# 8. Request Bundle

Each 270-equivalent FHIR artifact is a self-contained:

```json
{
  "resourceType": "Bundle",
  "type": "collection"
}
```

Resources:

```text
CoverageEligibilityRequest
Patient                 <- clinical Patient
Coverage                <- clinical CoverageProfile
Organization            <- requester / MEDILACRA CLINIC
Organization            <- payer
Organization            <- employer
```

The employer Organization is retained because the clinical CoverageProfile knows the employer and the clinical Coverage can represent it as `policyHolder`.

No MessageHeader is included.

---

# 9. Clinical Patient

Build directly from MediLacra `Patient`.

Project:

```text
patient_id
patient_name
date_of_birth
sex
address
city/state/zip
phone
```

Do not invent missing data.

The resource should carry a MediLacra patient identifier and a deterministic FHIR resource ID.

---

# 10. Clinical Coverage

Build directly from `CoverageProfile`.

Map:

```text
status                 active
beneficiary            -> clinical Patient
subscriber             -> clinical Patient
subscriberId           member_id
relationship           self
period                 effective_start/end
payor                  -> payer Organization
policyHolder           -> employer Organization
class[group].value     group_number
class[plan].value      plan_id
class[plan].name       plan_name
type.text              plan_type
```

The current model is subscriber-is-patient only.

---

# 11. CoverageEligibilityRequest

Build from:

```text
EligibilityInquiry
EligibilityExchangeIdentity
clinical Patient
clinical Coverage
requester Organization
payer Organization
run timestamp
```

Target R4 fields:

```text
status          active
purpose         [validation, benefits]
patient         -> clinical Patient
servicedDate    inquiry.service_date
created         run datetime
provider        -> requester Organization
insurer         -> payer Organization
insurance
  focal         true
  coverage      -> clinical Coverage
identifier      shared eligibility exchange identity
```

The generic X12 service type `30` is not mechanically translated into a fake one-field FHIR equivalent.

Both formats represent the same semantic request independently.

---

# 12. Response Bundle

Each 271-equivalent FHIR artifact is also a `Bundle.type = collection`.

Resources:

```text
CoverageEligibilityResponse
CoverageEligibilityRequest       <- original request resource
Patient                          <- clinical request Patient
Coverage                         <- clinical request Coverage
Organization                     <- requester
Organization                     <- employer
Organization                     <- payer
Patient                          <- payer MemberRecord
Coverage                         <- payer EnrollmentRecord + BenefitPlan
```

The normal generated data will align, but the clinical and payer resources remain separate institutional materializations.

---

# 13. Payer Patient

Build from `MemberRecord`, not clinical `Patient`.

Project only payer-held facts:

```text
member_id
first_name
last_name
date_of_birth
administrative_sex
```

Do not copy address, phone, employer, or other clinical-only values.

---

# 14. Payer Coverage

Build from:

```text
MemberRecord
EnrollmentRecord
BenefitPlan
```

Map:

```text
status                 active for current ACTIVE MVP
beneficiary            -> payer Patient
subscriber             -> payer Patient
subscriberId           payer member_id
relationship           self
period                 enrollment effective_start/end
payor                  -> payer Organization
class[group].value     enrollment group_number
class[plan].value      plan_id
class[plan].name       plan_name
type.text              plan_type
```

Do not add `policyHolder`.

The payer primitive does not currently contain employer ownership information.

---

# 15. CoverageEligibilityResponse

Build from:

```text
EligibilityResponse
EligibilityExchangeIdentity
payer Patient
payer Coverage
payer Organization
requester Organization
original CoverageEligibilityRequest
service date
response timestamp
```

For the current ACTIVE MVP:

```text
status          active
purpose         [validation, benefits]
patient         -> payer Patient
servicedDate    same semantic service date
created         response timestamp
requestor       -> requester Organization
request         -> embedded CoverageEligibilityRequest
outcome         complete
insurer         -> payer Organization
insurance
  coverage      -> payer Coverage
  inforce       true
  benefitPeriod enrollment effective_start/end
identifier      shared eligibility exchange identity
```

Important semantic distinction:

```text
payer EligibilityOutcome.ACTIVE
        !=
FHIR response.outcome = "active"
```

FHIR `outcome` is processing outcome.

For a successfully produced ACTIVE eligibility response:

```text
CoverageEligibilityResponse.outcome = complete
CoverageEligibilityResponse.insurance.inforce = true
```

Negative eligibility scenarios remain out of scope for this round.

---

# 16. Pipeline API

Add:

```python
include_fhir_eligibility: bool = False
```

Define internally:

```python
include_eligibility = (
    include_x12
    or include_fhir_eligibility
)
```

Payer state must therefore materialize when either representation is requested.

Supported combinations:

```text
X12 only
FHIR only
X12 + FHIR
neither
```

No FHIR generation should require X12 to be enabled.

---

# 17. Counts

When enabled add:

```text
FHIR_ELIGIBILITY_REQUEST
FHIR_ELIGIBILITY_RESPONSE
```

For N encounters:

```text
N request bundles
N response bundles
```

When both X12 and FHIR are enabled:

```text
X12_270 == FHIR_ELIGIBILITY_REQUEST
X12_271 == FHIR_ELIGIBILITY_RESPONSE
```

---

# 18. Timestamped File Naming

## Per-encounter mode

```text
FHIR_R4_4.0.1_CoverageEligibilityRequest_<encounter>_YYYYMMDD_HHMMSS.json

FHIR_R4_4.0.1_CoverageEligibilityResponse_<encounter>_YYYYMMDD_HHMMSS.json
```

Each file contains one self-contained FHIR Bundle.

## Bulk mode

Use newline-delimited JSON:

```text
FHIR_R4_4.0.1_CoverageEligibilityRequest_YYYYMMDD_HHMMSS.ndjson

FHIR_R4_4.0.1_CoverageEligibilityResponse_YYYYMMDD_HHMMSS.ndjson
```

One complete Bundle per line.

This is MediLacra packaging for scaled artifact generation, not a claim of conformance to the FHIR Bulk Data Export implementation guide.

---

# 19. Main UI

Add independent controls:

```text
Include X12 Eligibility (270/271)
Include FHIR Eligibility (R4 4.0.1)
```

Completion summary should expose both counts.

Recent files should include:

```text
*.hl7
*.x12
*.json
*.ndjson
```

The Generate & Persist page gets the same FHIR eligibility toggle.

No new network dependency is introduced.

---

# 20. Persistence

Do not persist raw FHIR resources into DuckDB in this round.

Existing clinical and payer primitives remain the durable persisted reality.

Raw representation persistence is deferred to a representation-neutral artifact table that can later hold:

```text
HL7 v2
X12
FHIR
```

without overloading `messages.raw_hl7`.

---

# 21. Existing FHIR Converter

Do not delete or rewrite:

```text
fhir/fhir_convert_backend.py
```

That remains:

```text
HL7 v2 -> FHIR
```

The new path is:

```text
synthetic reality -> FHIR
```

Pure helper extraction is acceptable only where it removes real duplication without coupling the new generator to HL7 parsing.

---

# 22. Tests

Add tests covering:

## FHIR R4 structure

- request bundle is `Bundle/type=collection`;
- response bundle is `Bundle/type=collection`;
- required eligibility resources exist;
- all internal references resolve;
- request has required status/purpose/patient/created/insurer;
- response has required status/purpose/patient/created/request/outcome/insurer;
- request `insurance.coverage` resolves;
- response `insurance.coverage` resolves;
- response `request` resolves;
- response `insurance.inforce=true` for ACTIVE.

## Institutional authorship

- request Patient is built from clinical Patient;
- request Coverage is built from clinical CoverageProfile;
- response Patient is built from payer MemberRecord;
- response Coverage is built from payer EnrollmentRecord/BenefitPlan;
- employer exists only in clinical Coverage as policyHolder;
- payer Coverage contains no policyHolder;
- changing clinical state after payer materialization does not change payer-side FHIR projection.

## Semantic/X12 equivalence

For the same synthetic event:

```text
X12 270 member ID == FHIR request Coverage.subscriberId
X12 270 service date == FHIR request.servicedDate
X12 270 payer == FHIR request.insurer
X12 270 group == FHIR request Coverage.class[group]

X12 271 active == FHIR response.insurance.inforce
X12 271 dates == FHIR payer Coverage.period
X12 271 group == FHIR payer Coverage.class[group]
X12 271 payer-held subscriber == FHIR payer Patient
```

Also assert the FHIR generation modules do not import or call X12 parsing.

## Output/scale

- N exchanges produce N request bundles;
- N exchanges produce N response bundles;
- bulk NDJSON has exactly N lines;
- per-encounter filenames contain encounter + timestamp;
- bulk filenames contain R4 4.0.1 + timestamp;
- FHIR can be enabled without X12;
- existing offline core-generation behavior remains offline.

---

# 23. CI

Add the new FHIR tests to the focused branch suite.

Extend the small offline scale check so one normal `run_pipeline()` execution can validate:

```text
25 X12 270
25 X12 271
25 FHIR request bundles
25 FHIR response bundles
0 X12 control collisions
```

Do not introduce external validation dependencies into CI.

---

# 24. External Validation

After automated validation, load a small generated FHIR request and response bundle into IRIS FHIR tooling.

Target validation:

- resources parse as FHIR R4 4.0.1 JSON;
- references resolve within the bundle;
- CoverageEligibilityRequest is accepted structurally;
- CoverageEligibilityResponse is accepted structurally.

This remains separate from exhaustive implementation-guide certification.

---

# 25. Explicit Non-Goals

Not part of this build:

- R4B;
- R5;
- FHIR messaging Bundle / MessageHeader;
- FHIR transaction Bundle semantics;
- Bulk Data IG conformance;
- InsurancePlan;
- Practitioner / PractitionerRole;
- Location;
- Claim / ExplanationOfBenefit;
- raw FHIR DuckDB persistence;
- negative eligibility response mapping;
- AAA mapping;
- dependent coverage;
- benefit financial details;
- X12 -> FHIR conversion.

---

# 26. Implementation Order

1. Commit this build plan.
2. Add shared eligibility semantic/run context.
3. Build `EligibilityInquiry` directly from clinical synthetic reality.
4. Refactor normal X12 generation to consume semantic inquiry/response.
5. Preserve existing X12 parser tests as independent representation validation.
6. Add deterministic R4 resource-ID helpers.
7. Add `fhir/eligibility_r4.py`.
8. Build clinical Patient/Coverage/Organizations.
9. Build payer Patient/Coverage.
10. Build CoverageEligibilityRequest.
11. Build CoverageEligibilityResponse.
12. Build request/response collection Bundles.
13. Add `fhir/eligibility_generation.py`.
14. Add timestamped JSON/NDJSON writers.
15. Add `include_fhir_eligibility` to `run_pipeline()`.
16. Add counts.
17. Wire both Streamlit generation pages.
18. Add focused structural/institutional/equivalence/output tests.
19. Extend CI.
20. Run focused and full regression.
21. Run small scaled normal-pipeline validation.
22. Record implementation outcome in this document.

---

# 27. Definition of Done

A normal run:

```python
run_pipeline(
    n_patients=1000,
    include_x12=True,
    include_fhir_eligibility=True,
    include_sdoh=False,
    persist="duckdb",
    ...
)
```

can produce:

```text
1000 X12 270
1000 FHIR R4 CoverageEligibilityRequest Bundles

1000 X12 271
1000 FHIR R4 CoverageEligibilityResponse Bundles
```

with:

- R4 4.0.1 resource shapes;
- timestamped filenames;
- shared semantic exchange identity;
- shared semantic inquiry/response;
- separate clinical and payer institutional resources;
- no X12-to-FHIR conversion step;
- no FHIR dependency on X12 parsing;
- no raw FHIR DuckDB persistence;
- offline generation still offline by default;
- focused tests green;
- full regression green.

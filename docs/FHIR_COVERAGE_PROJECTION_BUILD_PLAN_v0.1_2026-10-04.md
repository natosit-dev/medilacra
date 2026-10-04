# FHIR Coverage Projection Build Plan

**Version:** 0.1  
**Date:** 2026-10-04  
**Branch:** `experiment/employer-coverage`  
**Status:** Implemented / validated  
**Pre-build head:** `708855704ec4cb453f5e731b2abbd54424378008`

---

# 1. Purpose

Extend MediLacra's existing HL7 v2 → FHIR converter so the employer-sponsored coverage reality now present in GT1, IN1, and IN2 survives into the FHIR Bundle.

This is a projection build, not a new ontology build.

The governing invariant is:

```text
GT1 ─┐
IN1 ─┼──► semantic coalescence ──► one Coverage graph
IN2 ─┘

                         ├── Employer Organization
Patient ─────────────────┼── Coverage
                         └── Payer Organization
```

GT1, IN1, and IN2 are overlapping representations of one institutional reality. They are not independent facts that should produce duplicate FHIR resources.

---

# 2. Relevant Prompt Lineage

> "We should do the FHIR transform next. Maybe in Disco Inferno?"

Initial direction toward transforming the newly generated employer/coverage data into FHIR.

> "No need for Disco experiments yet, we'll do that another time. For now, just add the new data to the FHIR resource bundle. Let's do a gap analysis. We're also dropping ZMC for now but it should remain on the roadmap. For now, we just want to add the GT1 and IN1/2 data as FHIR data"

This narrowed scope to the existing FHIR converter only.

> "Yeah we should leave out GT1:20 and use 1 coverage resource.
> Your fix for resource IDs is fine for now but I thought that was odd previously, we should put a fix on the roadmap.
> Double check PIQITT for FHIR converter pytest tests. Either way, we should create a suite of tests for this too.
> Let's see a Nat style build plan, with fancy terminology where relevant"

This establishes the core build constraints:

- exactly one Coverage resource for the current single-coverage message;
- GT1-20 employment status is recognized but deliberately not materialized;
- generated FHIR resource IDs are acceptable for the MVP;
- stable/deterministic FHIR resource identity remains a roadmap concern;
- PIQITT test lineage should be checked and reused where useful;
- MediLacra gets a dedicated FHIR coverage pytest suite.

> "Looks good. Add the build plan as an MD to docs, then go build it"

This document is the durable implementation plan.

---

# 3. Existing State / Gap

MediLacra already has:

```text
fhir/fhir_convert_backend.py
fhir/fhir_convert_app.py
```

The parser already preserves unrecognized segments, so GT1, IN1, and IN2 survive parsing.

The semantic loss occurs later.

Current ADT transformation:

```text
MSH -> MessageHeader
PID -> Patient
PV1 -> Encounter
GT1 -> dropped
IN1 -> dropped
IN2 -> dropped
```

Current DFT transformation:

```text
MSH -> MessageHeader
PID -> Patient
PV1 -> Encounter
FT1 -> Claim
GT1 -> dropped
IN1 -> dropped
IN2 -> dropped
```

Current ORU transformation remains intentionally clinical and does not project the financial/coverage segments.

---

# 4. PIQITT Lineage

PIQITT was checked for existing FHIR converter tests.

Findings:

- `main` has no `tests/` directory.
- `experiment/official-piqi-artifacts` contains pytest coverage for PIQI reference artifacts, not the FHIR converter.
- `connectathon/piqi-43` contains:
  - `tests/test_fhir_convert_cli.py`
  - `scripts/fhir_convert.py`
  - `scripts/fhir_convert_backend.py`

The PIQITT FHIR test is a useful end-to-end smoke-test pattern:

```text
HL7 file
  ↓
convert_file()
  ↓
FHIR Bundle
  ↓
Patient + Encounter
```

PIQITT also contains an important converter correction that MediLacra does not yet have: MSH requires dedicated indexing because MSH-1 is the field separator and is not represented in the same way as normal segment fields after splitting.

That fix should be ported before adding new semantic projection.

---

# 5. Phase 0 — Structural Normalization

Add:

```python
get_msh_field(msh_fields, msh_idx)
```

Use it in:

- `build_message_header()`
- `detect_message_type()`

Rationale:

```text
generic segment indexing != MSH indexing
```

This is **structural normalization before semantic projection**.

Acceptance:

```text
ADT^A01 detected as ADT^A01
DFT^P03 detected as DFT^P03
ORU^R01 detected as ORU^R01
```

---

# 6. Semantic Coalescence Layer

Add a small intermediate reconciler:

```python
extract_coverage_context(parsed) -> dict | None
```

Its job is not to generate FHIR. Its job is to collapse the redundant v2 representation into one normalized institutional context.

Target normalized shape:

```text
patient_is_subscriber
employer_id
employer_name
payer_id
payer_name
plan_id
plan_name
plan_type
group_number
member_id
effective_start
effective_end
subscriber_relationship
gt1_employment_status
conflicts
```

## Precedence

Employer ID:

```text
IN2-3.1
fallback GT1-29
```

Employer name:

```text
IN2-3.2
fallback IN1-11
fallback GT1-16
```

Payer:

```text
IN1-3 / IN1-4
```

Plan:

```text
IN1-2.1 / IN1-2.2
```

Group:

```text
IN1-8
```

Period:

```text
IN1-12 / IN1-13
```

Plan type:

```text
IN1-15
```

Subscriber relationship:

```text
IN1-17
```

Member ID:

```text
IN1-49
```

GT1 is primarily corroborating evidence in the current synthetic path.

If GT1 / IN1 / IN2 disagree on employer identity, deterministic precedence remains as above and the conflict is detectable in the normalized context. This MVP does not implement a generalized conflict-resolution engine.

Fancy term: **semantic coalescence with deterministic precedence**.

---

# 7. Employer Organization

Build one employer Organization when employer identity is available.

Conceptual output:

```json
{
  "resourceType": "Organization",
  "id": "org-<generated-valid-fhir-id>",
  "identifier": [
    {
      "system": "urn:medilacra:employer",
      "value": "CVS"
    }
  ],
  "name": "CVS Health Corporation"
}
```

Important distinction:

```text
FHIR Resource.id
    = bundle/reference identity

Organization.identifier
    = source/business identity
```

The original employer ID must be preserved exactly in `Organization.identifier.value`.

---

# 8. Payer Organization

Build one payer Organization from IN1:

```text
IN1-3 -> payer identifier
IN1-4 -> payer name
```

Example:

```json
{
  "resourceType": "Organization",
  "id": "org-<generated-valid-fhir-id>",
  "identifier": [
    {
      "system": "urn:medilacra:payer",
      "value": "KAISER"
    }
  ],
  "name": "Kaiser Permanente"
}
```

No legal-entity normalization is attempted in this MVP.

---

# 9. One Coverage Resource

The current source message represents one synthetic CoverageProfile and should materialize exactly one FHIR Coverage.

Target:

```text
Coverage
├── status = active
├── beneficiary -> Patient
├── subscriber -> Patient       [SELF only]
├── subscriberId = member ID
├── relationship = self
├── policyHolder -> Employer Organization
├── payor -> Payer Organization
├── period
├── type = plan type
└── class
    ├── group
    └── plan
```

## Mapping

```text
IN1-2   -> Coverage.class[type=plan]
IN1-3/4 -> payer Organization -> Coverage.payor
IN1-8   -> Coverage.class[type=group]
IN1-11  -> employer evidence
IN1-12  -> Coverage.period.start
IN1-13  -> Coverage.period.end
IN1-15  -> Coverage.type
IN1-16  -> subscriber evidence
IN1-17  -> Coverage.relationship
IN1-49  -> Coverage.subscriberId
IN2-3   -> employer Organization identity
GT1     -> corroborating patient/employer/SELF evidence
```

## Local mapping decision

For this MVP:

```text
IN1-49 member ID -> Coverage.subscriberId
```

This is an explicit local modeling decision and should be tested/documented as such.

---

# 10. GT1-20 — Deliberately Unmaterialized

Current generated value:

```text
GT1-20 = 1
```

meaning full-time employed.

For this build:

```text
parseable       YES
recognized      YES
documented      YES
FHIR projected  NO
```

Do not force employment status into Coverage.

GT1-20 belongs to the deferred material-context / ZMC roadmap.

This is **deliberate semantic non-projection**, not accidental data loss.

---

# 11. Resource Identity — MVP and Roadmap

Current MVP:

```text
source employer ID: HOME_DEPOT
      ↓
Organization.identifier.value = HOME_DEPOT

FHIR Resource.id
      ↓
generated legal FHIR id
```

This avoids illegal FHIR Resource.id characters while preserving source identity.

Roadmap item: **Resource Identity Canon**

The longer-term problem is not merely underscore replacement. It is stable referential identity:

```text
same conceptual employer
      ↓
same stable FHIR resource identity
      ↓
across repeated transformations
```

A deterministic identity strategy should eventually replace per-transform UUID identity for reusable organizations.

Not part of this build.

---

# 12. Bundle Assembly

## ADT

```text
Bundle
├── MessageHeader
├── Patient
├── Encounter
├── Organization [employer]
├── Organization [payer]
└── Coverage
```

## DFT

```text
Bundle
├── MessageHeader
├── Patient
├── Encounter
├── Organization [employer]
├── Organization [payer]
├── Coverage
└── Claim...
```

## ORU

Unchanged:

```text
Bundle
├── MessageHeader
├── Patient
├── Encounter
├── DiagnosticReport
└── Observation...
```

Fancy term: **message-specific projection without canonical-model contamination**.

---

# 13. Negative / Partial Data Behavior

## No IN1

```text
no Coverage
no coverage Organizations
```

## IN1 but no GT1 / IN2

Build from IN1 where possible.

## No employer

Coverage may still exist without `policyHolder` if payer and patient context are sufficient.

## No payer

Do not emit an invalid Coverage requiring payor.

## Employer disagreement

Use deterministic precedence and expose a conflict marker in the normalized context.

## Illegal source business identifier

Preserve exact source value in `Organization.identifier`; generated Resource.id remains legal.

---

# 14. Pytest Plan

Create:

```text
tests/test_fhir_coverage_conversion.py
```

## A. Structural substrate

Verify MSH detection:

```text
ADT^A01
DFT^P03
ORU^R01
```

## B. Reconciliation

For the manual UI specimen:

```text
KELLEY^DEVIN
CVS
Kaiser Permanente
STANDARD_PPO
GRP-CVS-398915
MEM-01374522
SELF
```

assert one normalized context.

Test employer fallback from GT1 when IN2 is absent.

Test mismatch detection.

## C. FHIR resources

Assert:

```text
exactly 1 Coverage
exactly 1 employer Organization
exactly 1 payer Organization

Coverage.beneficiary -> Patient
Coverage.subscriber -> Patient
Coverage.policyHolder -> employer Organization
Coverage.payor[0] -> payer Organization

employer identifier preserved
payer identifier preserved
member ID preserved
group preserved
plan preserved
period preserved
SELF preserved
```

Explicitly assert GT1-20 employment status is not projected.

## D. Referential closure

Every local FHIR reference introduced by the conversion should resolve to a resource present in the same Bundle.

Fancy term: **referential closure**.

## E. Message integration

Verify:

```text
ADT -> coverage graph present
DFT -> coverage graph present + Claim preserved
ORU -> unchanged / no coverage graph
```

## F. Edge cases

Verify:

```text
no IN1 -> no Coverage
no payer -> no invalid Coverage
HOME_DEPOT -> preserved as business identifier while Resource.id stays valid
```

Finally run the complete repository regression suite.

---

# 15. Expected Files Changed

```text
docs/FHIR_COVERAGE_PROJECTION_BUILD_PLAN_v0.1_2026-10-04.md
fhir/fhir_convert_backend.py
tests/test_fhir_coverage_conversion.py
.github/workflows/employer-coverage-ci.yml
```

No FHIR Streamlit UI redesign is expected. The existing app already serializes whatever resources the backend places into the Bundle.

---

# 16. Explicit Non-Goals

Not in this build:

- GT1-20 projection
- ZMC implementation
- material-condition Observations
- Disco Inferno
- semantic-survival scoring
- family/dependent relationships
- RelatedPerson
- multiple concurrent Coverage resources
- InsurancePlan
- employer benefit details
- payer legal-entity normalization
- prior authorization
- network modeling
- stable/deterministic FHIR Resource.id implementation

---

# 17. Definition of Done

The build is complete when the tested CVS/Kaiser HL7 specimen:

```text
GT1
  CVS + SELF

IN1
  Kaiser
  Standard PPO
  CVS
  group
  dates
  member

IN2
  CVS employer identity
```

produces:

```text
FHIR Bundle

Patient
Employer Organization = CVS
Payer Organization = Kaiser
Coverage
  beneficiary = Patient
  subscriber = Patient
  relationship = self
  policyHolder = CVS
  payor = Kaiser
  subscriberId = member
  group = GRP-CVS-398915
  plan = STANDARD_PPO / Standard PPO
  period = 2026
```

with all of the following true:

```text
1 Coverage
2 Organizations
0 duplicate employer realities
0 GT1-20 projection
all new references resolvable
ADT supported
DFT supported
ORU unchanged
FHIR Resource.ids valid
source business identifiers preserved
focused FHIR tests green
full repository regression green
```

---

# 18. Roadmap Preserved

```text
ZMC / material conditions
GT1-20 employment status
Resource Identity Canon
family/dependent coverage
RelatedPerson
richer InsurancePlan modeling
payer legal-entity normalization
semantic-transform experiments
Disco Inferno
```

The architecture is **semantic compression without semantic collapse**: redundant HL7 v2 representations enter; one coherent FHIR coverage graph leaves.


---

# 19. Implementation Outcome

Implemented on `experiment/employer-coverage`.

## Materialized changes

### `fhir/fhir_convert_backend.py`

- Ported PIQITT-style MSH-specific indexing via `get_msh_field()`.
- Corrected MessageHeader source/destination/event extraction.
- Corrected message-type detection for ADT, DFT, and ORU.
- Added `extract_coverage_context()` as the semantic coalescence layer.
- Added employer conflict detection with deterministic precedence.
- Added employer and payer Organization construction.
- Added one Coverage resource construction for the current single-coverage MVP.
- Added group and plan `Coverage.class` projection.
- Added member ID -> `Coverage.subscriberId`.
- Added SELF -> `Coverage.relationship`.
- Added employer -> `Coverage.policyHolder`.
- Added payer -> `Coverage.payor`.
- Added effective period conversion.
- Added coverage resources to ADT and DFT bundles.
- Left ORU conversion unchanged.
- Recognizes GT1-20 in normalized context but deliberately does not project it.

### `tests/test_fhir_coverage_conversion.py`

Added dedicated tests for:

- MSH structural normalization;
- ADT / DFT / ORU message-type detection;
- GT1 + IN1 + IN2 semantic coalescence;
- employer fallback behavior;
- employer mismatch detection;
- one-Coverage invariant;
- employer Organization;
- payer Organization;
- Patient subscriber / beneficiary references;
- policyHolder / payor references;
- member, group, plan, relationship, and period survival;
- GT1-20 deliberate non-projection;
- DFT Claim preservation;
- ORU non-expansion;
- no-IN1 behavior;
- no-payer safety behavior;
- illegal source business IDs such as `HOME_DEPOT`;
- FHIR-valid generated Resource.id values;
- referential closure within the generated Bundle.

### CI

The employer-coverage workflow now runs the FHIR coverage projection suite as part of the focused branch tests.

## Validation result

Final CI:

```text
Focused employer coverage + GT1 + FHIR suite:
43 passed

Full repository regression:
56 passed
```

No failures were reported.

## Resulting projection

The tested CVS / Kaiser specimen now follows:

```text
GT1 + IN1 + IN2
       |
       v
normalized coverage context
       |
       +--> Organization [CVS employer]
       +--> Organization [Kaiser payer]
       '--> Coverage
              ├── beneficiary -> Patient
              ├── subscriber -> Patient
              ├── relationship = self
              ├── policyHolder -> CVS
              ├── payor -> Kaiser
              ├── subscriberId = MEM-01374522
              ├── group = GRP-CVS-398915
              ├── plan = STANDARD_PPO / Standard PPO
              '--> period = 2026-01-01 .. 2026-12-31
```

GT1-20 remains intentionally outside the FHIR projection and ZMC / material-context work remains on the roadmap.

The Resource Identity Canon also remains deferred: source business identifiers are preserved in `Organization.identifier`, while legal generated FHIR Resource.id values are used for current Bundle references.

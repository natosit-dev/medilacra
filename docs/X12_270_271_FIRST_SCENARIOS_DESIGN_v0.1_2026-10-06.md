# X12 270/271 — First Two Scenario Design

**Version:** 0.1  
**Date:** 2026-10-06  
**Branch:** `experiment/employer-coverage`  
**Status:** Implemented / validated

---

# 1. Purpose

Define the first two X12 270/271 eligibility scenarios that exercise the new synthetic payer engine without expanding scope into detailed benefits, family/dependent logic, or trading-partner authorization.

The design goal is to prove:

```text
clinical-side identity + coverage knowledge
            |
            v
          X12 270
            |
            v
    payer-side member matching
            |
            v
    payer-side enrollment decision
            |
            v
          X12 271
```

The payer must answer from payer-held state only.

---

# 2. Standards Baseline

Initial implementation target:

```text
ASC X12N 005010X279A1
270 — Health Care Eligibility Benefit Inquiry
271 — Health Care Eligibility Benefit Information
```

Public X12 examples confirm the subscriber-is-patient flow uses the hierarchy:

```text
Information Source
    |
Information Receiver
    |
Subscriber / Patient
```

and a generic eligibility inquiry may use:

```text
EQ*30
```

for Health Benefit Plan Coverage.

Useful public references:

- https://x12.org/examples/005010x279
- https://x12.org/examples/005010x279/example-1a-generic-request-clinic-patients-subscriber-eligibility
- https://x12.org/examples/005010x279/example-1b-response-generic-request-clinic-patients-subscriber-eligibility

The full implementation guide remains authoritative where public examples are incomplete.

---

# 3. Shared MVP Constraints

Both first scenarios intentionally use the simplest current MediLacra coverage shape:

```text
patient = subscriber
member has payer-assigned member ID
no dependent loop
one payer
one active/inactive enrollment candidate
generic service type 30
no detailed benefit accumulator logic
```

No family relationship modeling is introduced.

No benefit-specific copay/deductible/coinsurance content is required yet.

---

# 4. Representation Boundary

The X12 package should remain an adapter layer.

Target dependency direction:

```text
clinical-side source facts
        |
        v
x12.build_270(...)
        |
        v
X12 270 text
        |
        v
x12.parse_270(...)
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
x12.build_271(...)
        |
        v
X12 271 text
```

The 270 parser/builder must not contain payer decision logic.

The 271 builder must not perform matching or enrollment evaluation.

---

# 5. Scenario 1 — Clean Active Eligibility

## 5.1 Intent

Prove the complete happy path:

```text
clinical identity
    |
    v
270
    |
    v
payer exact member match
    |
    v
active enrollment
    |
    v
271 ACTIVE
```

## 5.2 Clinical-Side Source

Use the existing Devin Kelley / Kaiser specimen:

```text
Clinical Patient
    name = Devin Kelley
    DOB = 1949-01-16
    sex = M

Clinical CoverageProfile
    payer = KAISER / Kaiser Permanente
    member_id = MEM-01374522
    group = GRP-CVS-398915
    plan = STANDARD_PPO / Standard PPO
```

The 270 should be generated from **clinical-side state only**.

## 5.3 Payer-Side State

```text
MemberRecord
    payer_id = KAISER
    member_id = MEM-01374522
    first_name = Devin
    last_name = Kelley
    DOB = 1949-01-16
    sex = M

EnrollmentRecord
    status = ACTIVE
    plan_id = STANDARD_PPO
    group = GRP-CVS-398915
    effective = 2026-01-01 .. 2026-12-31
```

## 5.4 270 Semantic Content

Minimum transaction semantics:

```text
transaction = eligibility inquiry
payer = KAISER
requester = synthetic clinical organization
subscriber/patient = Devin Kelley
member ID = MEM-01374522
DOB = 1949-01-16
sex = M
service date = inquiry date
service type = 30 / Health Benefit Plan Coverage
trace ID = generated request trace
```

Likely transaction-set structure:

```text
ST
BHT

HL 20  Information Source
NM1 PR  Payer

HL 21  Information Receiver
NM1 1P  Provider / clinical organization

HL 22  Subscriber
TRN
NM1 IL  Subscriber
DMG
DTP 291 requested plan/service date
EQ 30

SE
```

Envelope generation (`ISA/GS/GE/IEA`) should be implemented separately from transaction-set semantics.

## 5.5 Payer Evaluation

270 adapter produces:

```text
EligibilityInquiry
    payer_id = KAISER
    member_id = MEM-01374522
    first_name = Devin
    last_name = Kelley
    DOB = 1949-01-16
    sex = M
    service_date = requested date
```

Expected engine path:

```text
member ID exact
demographics consistent
    |
MATCHED
    |
active enrollment on date
    |
ACTIVE
```

## 5.6 271 Semantic Content

Minimum response semantics:

```text
payer = Kaiser Permanente
requester = original clinical organization
trace = original request trace
subscriber = payer-held MemberRecord
member ID = MEM-01374522
plan begin = 2026-01-01
plan end = 2026-12-31
active coverage = service type 30
plan description = Standard PPO
```

Likely transaction-set structure:

```text
ST
BHT

HL 20
NM1 PR

HL 21
NM1 1P

HL 22
TRN
NM1 IL
DMG
DTP 346 Plan Begin
DTP 347 Plan End
EB 1 / service type 30 / Standard PPO

SE
```

Do not add copay, deductible, PCP, network, or accumulator EB loops yet.

## 5.7 Assertions

Scenario passes when:

```text
270 is parseable into one EligibilityInquiry
payer engine returns MATCHED + ACTIVE
271 references the same trace
271 uses payer-held member identity
271 identifies active generic plan coverage
no clinical object is dereferenced during payer evaluation
```

---

# 6. Scenario 2 — Institutional Identity Divergence, Successful Match

## 6.1 Intent

Prove the reason institutional separation exists.

The clinical system and payer system hold slightly different identity records for the same hidden synthetic person.

```text
Hidden PersonTruth:
Devin Kelley

Clinical Patient:
Devin Kelley

Payer MemberRecord:
Devin Kelly
```

The 270 sends what the clinical institution knows.

The payer matches using its own records and returns what the payer knows.

## 6.2 Clinical-Side Source

Same as Scenario 1:

```text
first_name = Devin
last_name = Kelley
DOB = 1949-01-16
member_id = MEM-01374522
payer = KAISER
```

## 6.3 Payer-Side Divergence

Deliberately mutate payer-local state after materialization:

```text
MemberRecord
    member_id = MEM-01374522
    first_name = Devin
    last_name = Kelly
    DOB = 1949-01-16
    sex = M
```

Enrollment remains:

```text
ACTIVE
STANDARD_PPO
GRP-CVS-398915
2026-01-01 .. 2026-12-31
```

Ground truth still knows both institutional records originated from the same `PersonTruth`, but operational matching cannot use that oracle.

## 6.4 270

The 270 must contain the **clinical** spelling:

```text
NM1 IL:
KELLEY / DEVIN

member ID:
MEM-01374522

DOB:
1949-01-16
```

This proves the outbound X12 request is a projection of clinical-side knowledge, not payer state.

## 6.5 Payer Matching

Expected result:

```text
member ID exact
DOB exact
first name exact
last name conflict

=> MATCHED
=> conflicting_fields = ["last_name"]
```

The engine must not use GroundTruthLink to repair the mismatch.

## 6.6 Eligibility

Enrollment evaluation proceeds because the member record resolved successfully.

Expected:

```text
EligibilityOutcome = ACTIVE
```

## 6.7 271

The 271 should project **payer-held identity**, not echo the 270 blindly.

Therefore the subscriber name in the 271 should be:

```text
KELLY / DEVIN
```

while retaining:

```text
member ID = MEM-01374522
active plan = STANDARD_PPO
coverage dates = payer EnrollmentRecord
trace = original request trace
```

This is the critical semantic demonstration:

```text
270 says:
KELLEY

payer system says:
KELLY

271 says:
KELLY
```

The transformation therefore preserves institutional authorship instead of smoothing disagreement away.

## 6.8 Assertions

Scenario passes when:

```text
270 contains clinical-side Kelley spelling
payer MatchResult = MATCHED
payer MatchResult exposes last_name conflict
EligibilityResponse = ACTIVE
271 contains payer-side Kelly spelling
271 does not silently copy subscriber name from 270
GroundTruthLink is never consulted by payer matching
```

---

# 7. Why These Two Scenarios First

Together, the scenarios prove both halves of the new architecture.

Scenario 1 proves:

```text
standards mechanics + clean payer workflow
```

Scenario 2 proves:

```text
institutional separation + patient matching + payer authorship
```

A simple ACTIVE and NOT_FOUND pair would test branching, but would not prove that the clinical and payer realities are genuinely independent.

NOT_FOUND should be Scenario 3.

---

# 8. Minimal New X12 Primitives

Do not build a general EDI framework yet.

First-cut package:

```text
x12/
    __init__.py
    envelope.py
    eligibility_270.py
    eligibility_271.py
    parser.py
```

Responsibilities:

## `envelope.py`

```text
ISA / IEA
GS / GE
ST / SE control-number support
```

Keep envelope/control scaffolding separate from eligibility semantics.

## `eligibility_270.py`

```text
clinical-side facts -> 270 transaction set
parsed 270 -> EligibilityInquiry
```

## `eligibility_271.py`

```text
EligibilityResponse + payer MemberRecord -> 271 transaction set
```

## `parser.py`

Only enough generic X12 tokenization to support:

```text
segment terminator
element separator
component/repetition separators as needed
segment name + element access
```

No universal X12 schema engine yet.

---

# 9. Trace Primitive

Add one explicit transaction-level trace value because request/response correlation matters.

Conceptually:

```text
EligibilityExchange
    trace_id
    request_control_number
    response_control_number
```

Do not make this payer reality.

It belongs to the inter-institutional exchange layer.

For the MVP, the 271 must preserve the 270 trace relationship.

---

# 10. Requester Primitive

The first 270 needs an information receiver / provider organization.

Do not build a full provider network model.

Use one synthetic requester fixture:

```text
requester_id
requester_name
identifier_qualifier
identifier
```

This belongs to exchange configuration, not payer MemberRecord state.

Trading-partner authorization remains deferred.

---

# 11. Tests for the First X12 Build

Suggested test file:

```text
tests/test_x12_270_271.py
```

Minimum tests:

```text
Scenario 1:
clinical state -> 270
270 -> EligibilityInquiry
payer -> ACTIVE
ACTIVE + payer state -> 271
271 trace correlates to 270
271 contains payer/member/plan coverage

Scenario 2:
270 contains clinical Kelley
payer record contains Kelly
matcher returns MATCHED + last_name conflict
271 contains payer Kelly
271 does not echo clinical Kelley
```

Boundary tests:

```text
x12 modules do not import GroundTruthLink
271 builder does not import clinical Patient/CoverageProfile
payer system remains unaware of X12 segment names
```

Round-trip semantics, not byte-for-byte identity, should be the primary test target.

---

# 12. Explicit Non-Goals

Not in the first two scenarios:

- dependent loop 2000D;
- family coverage;
- AAA error response;
- unauthorized requester;
- detailed EB benefit categories;
- copay;
- coinsurance;
- deductible;
- accumulators;
- PCP;
- network status;
- clearinghouse routing;
- batch 270;
- multiple patient requests;
- multiple active plans;
- COB;
- 278;
- 837;
- 835.

---

# 13. Roadmap After Scenario 2

Natural next scenarios:

```text
3. member not found
4. ambiguous member match
5. inactive / terminated enrollment
6. malformed or insufficient inquiry
7. requester unauthorized
8. benefit-detail expansion
9. dependent/member relationship
```

Only after the generic eligibility path is stable should the payer engine gain richer benefit state.

---

# 14. Design Principle

The first X12 implementation should prove:

> **The 270 carries what the clinical institution knows; the payer resolves against its own records; the 271 carries what the payer knows.**

That is the minimum meaningful 270/271 experiment for MediLacra.


---

# 15. Implementation Outcome

Implemented on `experiment/employer-coverage`.

## New X12 adapter package

```text
x12/
    __init__.py
    models.py
    parser.py
    envelope.py
    eligibility_270.py
    eligibility_271.py
```

The payer engine remains unchanged in role: X12 is an adapter around semantic eligibility behavior rather than the location where payer decisions are made.

## Exchange-layer primitives

Added:

```text
X12Party
EligibilityExchange
EnvelopeConfig
```

`EligibilityExchange` owns trace/control metadata for the inter-institutional exchange and is intentionally separate from both clinical and payer state.

## 270 implementation

Added:

```text
build_270_transaction()
build_270_from_clinical()
parse_270_to_inquiry()
```

The first 270 implementation supports the subscriber-is-patient path and projects:

- payer identity;
- requester/provider organization;
- subscriber name;
- payer-assigned member ID;
- DOB;
- administrative sex;
- requested plan/service date;
- generic service type 30;
- request trace;
- transaction control/reference metadata.

The clinical helper reads the existing clinical `Patient` + `CoverageProfile` values but the parser emits the representation-neutral payer `EligibilityInquiry`.

No payer decision logic exists in the 270 adapter.

## 271 implementation

Added:

```text
build_271_transaction()
parse_271()
```

The first 271 builder intentionally supports only the ACTIVE outcome required by Scenarios 1 and 2.

The response projects payer-held:

- subscriber/member identity;
- member ID;
- DOB / sex;
- coverage start;
- coverage end;
- active plan name;
- group number;
- generic plan coverage status;
- response trace.

The 271 builder requires a payer-side `MemberRecord` and `BenefitPlan`; it does not import or receive clinical `Patient` / `CoverageProfile`.

## Public-X12 alignment refinement

The design originally showed only:

```text
EB*1**30**<plan>
```

During implementation, the public X12 interpretation for a generic `EQ*30` request was reviewed. X12 indicates that the generic response also returns active-status information for the standard service-type set.

The implementation therefore emits:

```text
EB*1**30**<plan>
EB*1**1>33>35>47>86>88>98>AL>MH>UC
```

This does **not** add detailed financial benefits. Copays, deductibles, coinsurance, accumulators, PCP, and network detail remain out of scope.

The single-plan MVP also returns the payer-held group number as:

```text
REF*6P*<group>
```

Known plan end date is emitted with `DTP*347` in addition to plan begin `DTP*346`.

## Envelope support

Added a deliberately small envelope wrapper for one transaction set:

```text
ISA
GS
ST ... SE
GE
IEA
```

Eligibility semantics remain independent from envelope/control scaffolding.

The tokenizer can read either the bare transaction set or the MediLacra-generated envelope.

## Scenario 1 — Clean ACTIVE

Validated path:

```text
Clinical Patient / CoverageProfile
        |
        v
270
        |
        v
parse_270_to_inquiry()
        |
        v
PayerSystem
        |
        v
MATCHED + ACTIVE
        |
        v
271 from payer-held MemberRecord / Enrollment / BenefitPlan
```

Validated surviving facts include:

```text
member = MEM-01374522
subscriber = KELLEY / DEVIN
payer = KAISER
plan = Standard PPO
group = GRP-CVS-398915
coverage = 2026-01-01 .. 2026-12-31
service type = 30
trace = TRACE-270-0001
```

## Scenario 2 — Institutional divergence

Validated:

```text
270 clinical identity:
KELLEY / DEVIN

payer MemberRecord:
KELLY / DEVIN

matcher:
MATCHED
conflicting_fields = ["last_name"]

271 payer identity:
KELLY / DEVIN
```

The 271 does not echo the clinical spelling from the request. It projects the payer's own MemberRecord.

This is the first standards transaction in MediLacra that visibly demonstrates the institutional-reality separation.

## Test suite

Added:

```text
tests/test_x12_270_271.py
```

Coverage includes:

- Scenario 1 end-to-end semantic path;
- Scenario 2 identity divergence;
- 270 parsing into `EligibilityInquiry`;
- service type 30 preservation;
- request/response trace correlation;
- plan begin/end dates;
- group number;
- generic active service-type status set;
- ST/SE segment counts and control-number correlation;
- parsing a 270 inside the generated ISA/GS envelope;
- explicit refusal to build non-ACTIVE 271 outcomes in this MVP;
- no GroundTruthLink import into the X12 adapters;
- no clinical Patient/CoverageProfile dependency in the 271 builder;
- payer engine remains X12-agnostic.

## CI validation

Final branch CI:

```text
Focused employer coverage + GT1 + FHIR + payer + X12 suite:
70 passed

Full repository regression:
83 passed
```

Successful run:

```text
https://github.com/natosit-dev/medilacra/actions/runs/37471025198
```

No failures were reported.

## Scope boundary retained

Still not implemented:

- NOT_FOUND / AMBIGUOUS / INACTIVE 271 projections;
- AAA;
- dependents;
- family coverage;
- detailed benefit financials;
- accumulators;
- requester authorization;
- clearinghouse behavior;
- batch transactions;
- generalized X12 schema validation;
- 278 / 837 / 835.

The first two scenarios therefore remain intentionally narrow: **clinical-side knowledge enters the 270; payer-side knowledge determines and authors the 271.**

# Employer Coverage / GT1 UI User Test

**Version:** 0.1  
**Date:** 2026-10-04  
**Branch:** `experiment/employer-coverage`  
**Tested branch head before documentation:** `91c5826842df76e5a5c274b9f24c744688e907ae`  
**Status:** Manual UI smoke test passed

---

# 1. Purpose

Document the first manual end-to-end user test of the employer coverage + GT1 work through the MediLacra UI.

The test was intended to answer a simple question:

> Does the institutional reality established in `CoverageProfile` actually survive the ordinary UI generation path into the emitted HL7 v2 messages?

The specific invariant under test was:

```text
CoverageProfile
      |
      +--> Patient.employer
      +--> GT1 employer
      +--> IN1 employer
      '--> IN2 employer
```

The test also checked that the ordinary UI path generated ADT, ORU, and DFT messages without requiring the deterministic standalone demo script.

---

# 2. Relevant Prompt Lineage

## Manual testing request

> "Now, how do I test this manually through the UI?"

This shifted validation from pytest/CI into the actual Streamlit workflow.

## Pulling the tested branch

> "Ok, I'm back on my laptop. Let's pull the latest version so I can test the UI"

The tested branch was `experiment/employer-coverage`.

## User result

After generating and visually inspecting the HL7 output:

> "Looks good!"

The user supplied a rendered ADT screenshot plus the generated ADT, ORU, and DFT files.

## Address clarification

During review of the generated PID address:

> "Faker plausible is good. The issue I had with your previous address was you pulled a real address from context."

This corrected an earlier interpretation. Faker-generated plausible street addresses are accepted behavior. The rejected behavior was manually constructing an address from real contextual information.

## Next transformation direction

> "We should do the FHIR transform next. Maybe in Disco Inferno?"

This establishes FHIR transformation / semantic-survival testing as the next candidate experiment, but it is not part of this user-test implementation.

## Post-test semantic critique

> "It's interesting that employer only seems to be stored in relation to insurance... Seems like it should be in PID"

Followed by:

> "My point though is a critique of how the most important SDOH, the ability to afford necessities of life, is not a required field and when it's recorded it's tucked away in insurance fields"

This moved the interpretation from a simple mapping issue to a representation critique: employment and material conditions are not first-class patient context in the core HL7 v2 patient segment.

## Z-segment direction

The following material-context dimensions were accepted as good candidate fields for a future Z segment:

```text
Employment
    |
    +-- income
    +-- insurance
    +-- schedule stability
    +-- paid leave
    +-- occupational exposure
    +-- transportation demands
    +-- childcare constraints
    '-- ability to afford necessities
```

User response:

> "Those are good fields for the Z segment"

This is recorded as a design direction, not part of the tested GT1 MVP.

---

# 3. Test Setup

The branch was pulled locally and exercised through the normal MediLacra Streamlit UI.

The manual testing path was:

```text
MediLacra UI
    |
    v
Generate & Persist
    |
    v
pipeline_duckdb / existing generation path
    |
    +--> Patient
    +--> CoverageProfile
    +--> Encounter
    +--> Transaction
    |
    v
ADT / ORU / DFT generation
    |
    v
manual inspection of emitted HL7
```

The submitted output artifacts were:

```text
ADT_20261004_162009.hl7
ORU_20261004_162009.hl7
DFT_20261004_162009.hl7
```

The uploaded ADT file contained five ADT^A01 messages.

The uploaded DFT file contained five DFT^P03 messages.

The uploaded ORU file contained five ORU^R01 messages.

---

# 4. Manual Test Results

## 4.1 Employer reality matched across GT1 / IN1 / IN2

All five generated patients showed internally consistent employer identity across the ADT and DFT financial / insurance segments.

| Patient ID | Patient | Employer | Payer | Plan |
|---|---|---|---|---|
| RAD1583565 | LEE^TREVOR | Target Corporation | Aetna | Standard PPO |
| RAD0033925 | LYONS^WILLIAM | FedEx Corporation | Cigna Healthcare | Standard PPO |
| RAD9644860 | CALHOUN^ANN | FedEx Corporation | Kaiser Permanente | Standard PPO |
| RAD7553356 | DVM^NICHOLAS | Target Corporation | Cigna Healthcare | Standard PPO |
| RAD1054994 | KELLEY^DEVIN | CVS Health Corporation | Kaiser Permanente | Standard PPO |

For each record:

```text
GT1-3  = patient
GT1-11 = SELF
GT1-16 = employer name
GT1-20 = 1 / full-time employed
GT1-29 = employer ID

IN1-11 = same employer name

IN2-3  = same employer ID + employer name
```

No employer mismatch was observed in the submitted ADT or DFT artifacts.

---

# 5. Representative User-Test Specimen

The visually inspected example was:

```text
Patient:
KELLEY^DEVIN

Employer:
CVS Health Corporation

Employer ID:
CVS

Payer:
Kaiser Permanente

Plan:
Standard PPO
```

The generated ADT contained:

```text
GT1|1||KELLEY^DEVIN||||||||SEL^Self^HL70063|||||CVS Health Corporation||||1|||||||||CVS

IN1|1|STANDARD_PPO^Standard PPO^L|KAISER|Kaiser Permanente||||GRP-CVS-398915|||CVS Health Corporation|20260101|20261231||PPO|KELLEY^DEVIN|SEL^Self^HL70063||||||||||||||||||||||||||||||||MEM-01374522

IN2|||CVS^CVS Health Corporation
```

This is the intended institutional-reality projection.

---

# 6. ADT Result

The ADT path passed the manual smoke test.

Observed:

- Patient identity was present in PID.
- Encounter context was present in PV1.
- Existing clinical enrichment remained present.
- GT1 was emitted for the adult patients in the sample.
- GT1 used the patient as the self-guarantor.
- GT1 employer name and ID matched IN1 and IN2.
- IN1 payer, plan, group, dates, subscriber relationship, and member ID remained populated.
- IN2 retained employer ID + employer name.

The test therefore validated the normal UI path rather than only the isolated coverage demo.

---

# 7. DFT Result

The DFT path also passed.

Each submitted DFT^P03 message contained:

```text
PID
PV1
FT1
DG1
GT1
IN1
IN2
```

The same employer/payer/plan reality seen in ADT was preserved in DFT.

This matters because ADT and DFT are separate message-construction paths and had both required GT1 integration.

---

# 8. ORU Result

The ORU messages contained:

```text
MSH
PID
PV1
OBR
OBX...
```

They did not contain:

```text
GT1
IN1
IN2
```

This is expected under the current architecture. The employer-coverage work was intentionally wired into the ADT and DFT financial / insurance paths rather than the narrative ORU.

This is recorded as expected behavior, not a test failure.

---

# 9. Age-Gate Coverage

The GT1 MVP rule is:

```text
age at encounter > 18  -> emit GT1
age at encounter <= 18 -> do not emit GT1
unparseable age        -> do not emit GT1
```

All five patients in this manual user-test sample were adults.

Therefore:

- the manual test confirms adult GT1 generation through the UI;
- the manual test did **not** exercise the age-18 or minor boundary;
- boundary behavior remains covered by the dedicated pytest suite.

This distinction is important: the UI smoke test validates the real generation path, while automated tests validate the exact boundary conditions.

---

# 10. Address Observation

The manual test produced ordinary Faker-style addresses, for example:

```text
1249 Mendoza Corner
4353 Elliott Stream
4621 Mills Road Apt. 610
15621 Melissa Islands Suite 377
224 Stevens Mall
```

Decision:

**Keep this behavior.**

The desired model remains:

```text
real ZIP / city / state context
+
Faker-plausible synthetic street address
```

The earlier concern was not that plausible synthetic addresses resemble real addresses.

The concern was specifically the assistant manually constructing a plausible address using real contextual information from the conversation.

No `gen_patient()` address-generator cleanup is required as a result of this test.

---

# 11. Representation Finding

The manual inspection made a structural property of HL7 v2 more visible:

```text
PID
    patient identity / demographics

GT1 / IN1 / IN2
    employer appears primarily in financial / insurance context
```

The user identified this as a substantive SDOH critique rather than merely a missing-field inconvenience.

Employment is related to:

```text
income
insurance
schedule stability
paid leave
occupational exposure
transportation demands
childcare constraints
ability to afford necessities
```

Yet the employer/material-condition relationship is not represented as first-class core patient context in PID.

This finding motivates a future custom material-context Z segment rather than abusing an unrelated PID field.

---

# 12. Z-Segment Direction

Future design direction:

Create a custom Z segment for material conditions.

Working concept:

```text
ZMC-1   Set ID
ZMC-2   Employment Status
ZMC-3   Employer
ZMC-4   Income / Income Band
ZMC-5   Insurance / Coverage Status
ZMC-6   Schedule Stability
ZMC-7   Paid Leave Access
ZMC-8   Occupational Exposure / Risk
ZMC-9   Transportation Burden
ZMC-10  Childcare / Dependent Care Burden
ZMC-11  Ability to Afford Necessities
```

Potential placement:

```text
MSH
EVN
PID
ZMC
PV1
...
GT1
IN1
IN2
```

This is not yet implemented.

---

# 13. FHIR / Disco Inferno Next Direction

The next proposed experiment is transformation of the tested HL7 v2 artifacts into FHIR.

The current framing is:

```text
MediLacra
    generates reality

HL7 v2
    represents reality

FHIR converter
    transforms representation

Disco Inferno
    measures what survives
```

The manual user test provides concrete source artifacts for that experiment.

Candidate semantic assertions to inspect after transformation include:

```text
patient identity
employer
payer
plan
subscriber relationship
employment status
member identity
coverage period
```

The FHIR / Disco Inferno work remains a next-step design/build item and is not included in this test pass.

---

# 14. Decision Log

| Decision | Status | Reason |
|---|---|---|
| Test through normal Streamlit UI, not only demo script | Accepted | Validates real user path |
| Use generated ADT/DFT/ORU files as evidence | Accepted | Direct output from manual run |
| GT1 employer must match IN1/IN2 employer | Accepted and validated | Shared institutional reality |
| GT1 only for patient age >18 | Accepted | Family/dependent relationships intentionally out of scope |
| Manual test is sufficient to validate age boundary | Rejected | Current manual sample contained only adults; pytest remains authoritative for boundary |
| Add GT1 to ORU | Not required | Current ORU is narrative clinical result path |
| Replace Faker street addresses with obviously fake strings | Rejected | Faker-plausible is desired behavior |
| Manually construct synthetic addresses from real contextual addresses | Rejected | Risks leaking real contextual information into synthetic output |
| Put employer in an unrelated PID field | Rejected | Would corrupt HL7 semantics |
| Treat employer/material conditions as first-class MediLacra reality | Accepted direction | Employment is not merely an insurance property |
| Explore a custom material-context Z segment | Accepted direction | Makes SDOH/material context explicit near patient representation |
| Candidate Z fields include income, insurance, schedule, paid leave, occupational exposure, transportation, childcare, affordability | Accepted direction | User explicitly approved these dimensions |
| FHIR transformation is the next experiment | Proposed / next | Tests semantic survival across representations |
| Disco Inferno may be used to measure semantic preservation/loss | Proposed | Fits existing "what survives transformation?" experiment frame |

---

# 15. Outcome

**Manual UI smoke test: PASS**

Validated through the ordinary UI generation path:

```text
Patient
  |
  v
CoverageProfile
  |
  +--> GT1
  +--> IN1
  '--> IN2
```

The same employer identity survived into both ADT and DFT for all five submitted patients.

The test also produced two useful design findings:

1. Faker-plausible addresses are acceptable; contextual real-address construction is not.
2. Employment/material conditions are structurally peripheral in HL7 v2 core patient representation, motivating both a future Z segment and a FHIR semantic-survival experiment.

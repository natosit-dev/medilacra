# SHN MVP-0 — MediLacra side

This branch adds the MediLacra half of the first Smart Health Network experiment.

## Terms used in this experiment

### DTR

DTR = Documentation Templates and Rules.

It is an HL7 Da Vinci FHIR Implementation Guide used in prior authorization workflows. Very roughly, it defines how a system can ask for, collect, and represent the clinical documentation needed to support a coverage or prior-authorization decision—often using FHIR `Questionnaire` and `QuestionnaireResponse` resources.

### qr-context

`qr-context` is a FHIR extension used by DTR.

```text
QuestionnaireResponse
    |
    +-- qr-context --> Coverage/MBR-COVERED
    |
    +-- qr-context --> ServiceRequest/sr-MBR-COVERED
```

### chain

A chain is SHN's record of the transformation steps it used to get from one version to another.

For our first test:

```text
DTR 2.1
   ↓
DTR 2.2
```

there is only one step.

## What are we trying to do?

This is the smallest experiment connecting MediLacra, Smart Health Network (SHN), and PIQITT.

The basic idea is:

1. MediLacra creates synthetic healthcare data.
2. MediLacra turns part of that data into FHIR that SHN understands.
3. PIQITT sends that FHIR to SHN.
4. SHN changes the FHIR from one DTR version to another.
5. PIQITT evaluates what SHN sends back.

For this first version, we are deliberately keeping the test small.

We are not trying to run the entire Smart Health Network workflow yet.

## The workflow

```text
MediLacra
creates synthetic patient data
        |
        v
MediLacra
creates DTR 2.1 FHIR
        |
        v
PIQITT
sends it to SHN
        |
        | POST /demo/transform
        v
SHN
changes DTR 2.1 into DTR 2.2
        |
        v
PIQITT
evaluates the returned FHIR
```

Each project has one job.

### MediLacra

Creates the starting data.

### SHN

Changes one FHIR representation into another.

### PIQITT

Runs the test and evaluates the result.

## What does MediLacra create?

For MVP-0, MediLacra creates one small synthetic case.

The important relationships are:

```text
Patient
  |
  +---- has Coverage
  |
  +---- has ServiceRequest
```

There is also a payer connected to the Coverage.

So the synthetic data includes:

```text
Patient
Coverage
Payer
ServiceRequest
```

These are all supposed to describe the same synthetic situation.

That matters because later we want to ask whether those relationships still make sense after the data has been changed into another representation.

## What does MediLacra send toward SHN?

MediLacra creates a FHIR `QuestionnaireResponse` using the DTR 2.1 representation expected by SHN.

The important part looks roughly like this:

```text
QuestionnaireResponse
  |
  +---- Patient
  |
  +---- Coverage
  |
  +---- ServiceRequest
```

In DTR 2.1, both the Coverage reference and the ServiceRequest reference are represented using `qr-context`.

MediLacra then puts that FHIR inside the request SHN expects:

```json
{
  "contract": "pa.dtr",
  "from": "2.1",
  "to": "2.2",
  "payload": {
    "...FHIR QuestionnaireResponse..."
  }
}
```

That complete request is saved as:

```text
shn_transform_request.json
```

MediLacra does not have to send the request itself for the final workflow.

PIQITT will do that.

## What should SHN do?

PIQITT will send the request to:

```text
POST /demo/transform
```

The request tells SHN:

```text
This is DTR data.
It is currently version 2.1.
Change it into version 2.2.
```

SHN then applies its existing DTR transformation logic.

One of the changes we specifically expect is:

```text
DTR 2.1

qr-context
    |
    v
Coverage/C
```

becoming:

```text
DTR 2.2

qr-coverage
    |
    v
Coverage/C
```

The way the relationship is represented changes.

The Coverage itself should still be the same Coverage.

The ServiceRequest should also remain connected to the same case.

That gives us something concrete to test.

## What comes back from SHN?

If SHN can perform the transformation, it returns something shaped like:

```json
{
  "output": {
    "...DTR 2.2 FHIR..."
  },
  "lossReports": [],
  "chain": []
}
```

The important part for PIQITT is:

```text
output
```

That contains the transformed FHIR.

SHN also tells us which transformation steps it used and whether it had to carry or change anything.

We can save that information too, but PIQITT does not need to understand all of it before MVP-0 can work.

## What does PIQITT need to do?

PIQITT needs three new pieces for this workflow.

First, it needs to send:

```text
shn_transform_request.json
```

to SHN.

Second, it needs to take the FHIR out of:

```text
response.output
```

Third, it needs a new SAM profile for SHN-produced data.

That profile can evaluate the transformed FHIR just like PIQITT evaluates other data using SAMs.

The first profile only needs to cover this small DTR test.

We can expand it later.

## What MediLacra currently produces

Running the MVP-0 case creates:

```text
reality.json
dtr_2_1.fhir.json
shn_transform_request.json
expected_invariants.json

supporting/
  patient.fhir.json
  payer.fhir.json
  coverage.fhir.json
  service_request.fhir.json
```

### `reality.json`

Describes the synthetic situation MediLacra created.

This is our starting truth.

### `dtr_2_1.fhir.json`

The DTR 2.1 FHIR representation of that situation.

This is what goes into SHN.

### `shn_transform_request.json`

The complete POST body PIQITT can send to SHN.

### `expected_invariants.json`

Records the relationships we expect to remain true after transformation.

For example:

```text
the patient should still be the same patient

the Coverage should still be the same Coverage

the ServiceRequest should still be the same ServiceRequest

the Coverage relationship should survive even though
its DTR representation changes
```

### `supporting/`

Contains the individual FHIR resources used to describe the synthetic case.

## Running it

From the MediLacra repository:

```bash
python -m connectathon.shn_mvp0 --seed 43
```

The generated case is written under:

```text
connectathon/results/shn_mvp0/
```

There is also a Streamlit page for viewing and downloading the case.

Run MediLacra normally:

```bash
streamlit run medi_lacra_app.py
```

Then open:

```text
10 SHN MVP-0
```

## What is finished?

The MediLacra side of MVP-0 is built.

It can:

- create the synthetic case,
- create the DTR 2.1 FHIR,
- create the SHN request,
- record the relationships we expect to preserve,
- show the experiment in the UI,
- and package everything for PIQITT.

The MediLacra tests for this work are passing.

## What is not finished yet?

We have not yet run the complete live workflow:

```text
MediLacra
    ↓
PIQITT
    ↓
SHN
    ↓
PIQITT SAM evaluation
```

The remaining work is mostly on the PIQITT side:

```text
send POST to SHN

receive SHN response

extract response.output

evaluate it with a new SHN SAM profile
```

Once that works, MVP-0 is complete.

## The question this experiment asks

For the first test, the question is very simple:

> MediLacra created a relationship. SHN changed how that relationship was represented. Can PIQITT still recognize the relationship after the transformation?

Everything else can grow from there.


---

# 2026-10-09 update — live provider-network baseline

The original MVP-0 above targeted a demo DTR transformation boundary. On 2026-10-09, MediLacra completed a real authenticated provider-side workflow through the SHN provider test endpoint on route `00301`:

```text
CRD order-sign
  -> DTR $questionnaire-package
  -> PAS Claim/$submit
  -> PAS Claim/$inquire
```

All four calls returned HTTP 200, the PAS submit pended as expected, and the subsequent inquiry found the submitted authorization trace. A second complete run also succeeded and the inquiry matched both retained submissions.

The exact known-good reference fixtures and run harness are frozen at:

```text
connectathon/shn_live_baseline_00301/
```

Detailed live evidence is recorded in:

```text
docs/SHN_MVP0_LIVE_BASELINE_2026-10-09.md
```

This changes the next experiment boundary. We no longer need to prove that MediLacra can authenticate and move reference traffic across SHN. The next step is to project **MediLacra-generated reality** into CRD, DTR and PAS requests while keeping this transport baseline unchanged.


## 2026-10-09 — first MediLacra-generated CRD projection

After revalidating the frozen 00301 reference baseline, the next phase was added in
`connectathon/shn_medilacra_crd.py`.

This projection reuses `SHNMVP0Reality` and MediLacra's existing supporting FHIR rather than
copying the SHN reference fixture. It generates a CRD `order-sign` request containing the
synthetic MediLacra Patient, Coverage and ServiceRequest, then adds route `00301` only at the
SHN network-adapter boundary.

See `docs/SHN_MVP0_MEDILACRA_CRD_2026-10-09.md` for the model, invariants and run command.


### First generated CRD reached SHN

On 2026-10-09 at 16:49 UTC, the seed-43 MediLacra CRD for CPT `72148` was sent live through route `00301` and returned HTTP 200. SHN preserved the MediLacra Patient, Coverage and ServiceRequest references. The payer returned its no-rule/default CRD shape (`covered=conditional`, `info-needed=detail-code`) and did not return a questionnaire, so this case correctly stops before DTR.

See `docs/SHN_MVP0_MEDILACRA_CRD_2026-10-09.md` for the trace and semantic evidence.


## 2026-10-09 — coherent lumbar-fusion reality

A second generated clinical scenario now exercises a service with a documented route-00301 rule: CPT `22633`, lumbar spinal fusion.

For a given seed, the scenario preserves the same MediLacra patient and coverage as the first generated CRD experiment, but creates a new spine-clinic encounter and new ServiceRequest. This avoids changing the meaning of the earlier MRI order while isolating payer-rule selection as the changed variable.

Generate it with:

```bash
python -m connectathon.shn_lumbar_fusion --seed 43
```

See `docs/SHN_MVP0_LUMBAR_FUSION_2026-10-09.md`.


### Live lumbar-fusion rule selection and DTR handoff

The seed-43 lumbar-fusion CRD reached route `00301` at 16:59 UTC and returned the expected prior-authorization/documentation rule plus `http://example.org/fhir/Questionnaire/LumbarSpinalFusion`.

`connectathon/shn_lumbar_fusion_dtr.py` now builds the DTR package request from that **returned CRD canonical** and the same MediLacra patient/coverage reality. It refuses to generate DTR if CRD did not select exactly one questionnaire.


### First live MediLacra-derived DTR succeeded

At 17:06 UTC the DTR request derived from the live lumbar-fusion CRD returned HTTP 200 with the payer's `LumbarSpinalFusion` Questionnaire and an in-progress QuestionnaireResponse bound to the MediLacra Patient and Coverage.

This exposed the next semantic requirement: the payer asks whether imaging confirms instability or spondylolisthesis. MediLacra's existing `prior_imaging` fact only says imaging exists and must not be promoted into that stronger clinical assertion.


## 2026-10-09 — bulk CRD identity cohort

A batch generator and live runner now support repeated CRD testing across multiple independently generated MediLacra patients while holding the lumbar-fusion scenario and route 00301 constant.

Default cohort:

```text
seeds 100–109
10 distinct Patients
10 distinct Coverages
10 distinct encounters
10 distinct ServiceRequests
CPT 22633 for every case
```

The live runner records response semantics and checks that SHN returns the same Patient / Coverage / ServiceRequest identity for each case.

See `docs/SHN_MVP0_BULK_CRD_2026-10-09.md`.


### Bulk CRD cohort succeeded

The first seeds-100–109 cohort completed 10/10 with HTTP 200, 10/10 identity preservation, and 10/10 identical lumbar-fusion payer semantics/questionnaire selection.

This moves the useful next bulk axis from patient identity to clinical-rule diversity: different services and expected payer behaviors, while continuing to preserve case identity end to end.


## 2026-10-09 — mixed clinical-rule CRD matrix

After the 10/10 patient-identity cohort, the next batch varies clinical service and expected payer behavior instead of simply adding more patients to the same rule.

The default 9-case matrix repeats three evidence-backed behaviors three times each:

```text
22633  -> explicit lumbar-fusion prior-auth rule
42999  -> explicit not-covered rule
72148  -> no-rule/default response
```

The runner checks both identity preservation and partial semantic agreement with the documented expected CRD behavior.

See `docs/SHN_MVP0_RULE_MATRIX_2026-10-09.md`.

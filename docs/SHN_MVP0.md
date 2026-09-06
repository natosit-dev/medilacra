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

# SHN MVP-0 — MediLacra side

This branch adds the MediLacra half of the first Smart Health Network experiment.

## Boundary

MediLacra does only three things here:

1. establishes one coherent synthetic patient reality,
2. projects that reality into a DTR 2.1 `QuestionnaireResponse`,
3. packages the payload in SHN's `POST /demo/transform` request shape.

MediLacra does **not** perform the SHN transform and does **not** evaluate the result. PIQITT is the intended test driver/evaluator for those steps.

## Experiment

```text
MediLacra reality
      |
      v
DTR 2.1 QuestionnaireResponse
      |
      v
PIQITT
      |
      | POST /demo/transform
      v
SHN
 pa.dtr 2.1 -> 2.2
      |
      v
PIQITT SHN SAM profile
```

The initial relationship under test is deliberately small:

```text
Patient/<id>
  |-- hasCoverage --> Coverage/<id>
  `-- hasOrder ----> ServiceRequest/<id>
```

In DTR 2.1, Coverage and order references are carried in `qr-context`.
SHN's 2.1 -> 2.2 transform should move the Coverage reference to the DTR 2.2
`qr-coverage` representation while preserving the underlying Coverage identity.

## Files

`connectathon/shn_mvp0.py`

- builds the deterministic synthetic reality,
- projects supporting Patient/Coverage/Organization/ServiceRequest resources,
- builds the DTR 2.1 QuestionnaireResponse,
- builds the SHN transform request,
- records expected semantic invariants,
- writes or ZIPs the experiment artifacts.

`pages/10_SHN_MVP0.py`

- Streamlit operator surface for generating and inspecting the case,
- displays the reality relationships,
- displays the DTR input and SHN POST body,
- downloads the complete case pack or request JSON.

`tests/test_shn_mvp0.py`

- checks referential coherence,
- checks the DTR 2.1 representation,
- checks the SHN request envelope,
- checks deterministic generation,
- checks the PIQITT handoff ZIP.

## Run

From the repository root:

```bash
python -m connectathon.shn_mvp0 --seed 43
```

Artifacts are written under:

```text
connectathon/results/shn_mvp0/shn_mvp0_0043/
```

For the UI:

```bash
streamlit run medi_lacra_app.py
```

Then open **10 SHN MVP-0**.

## Handoff contract for PIQITT

The case pack contains:

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

For MVP-0, PIQITT only needs `shn_transform_request.json` to drive SHN and
`expected_invariants.json` / `reality.json` if it wants to compare the transformed
artifact against MediLacra's declared truth.

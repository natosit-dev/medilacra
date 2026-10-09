# SHN MVP-0 — DTR QuestionnaireResponse materialization

**Date:** 2026-10-09  
**Scenario:** lumbar spinal fusion  
**CPT:** 22633  
**Base diagnosis:** ICD-10-CM M43.16 — Spondylolisthesis, lumbar region

## Purpose

SHN has already selected and returned the payer's DTR Questionnaire.

This phase does not invent a form and does not ask SHN which answers to use. It takes the payer-returned Questionnaire as a semantic request and attempts to satisfy it from facts already present in MediLacra reality.

The boundary is:

```text
payer-returned Questionnaire
        ↓
exact semantic mapping
        ↓
existing MediLacra facts
        ↓
completed QuestionnaireResponse
```

## Reality additions

The lumbar-fusion scenario now includes:

```text
diagnosis:
  system:  http://hl7.org/fhir/sid/icd-10-cm
  code:    M43.16
  display: Spondylolisthesis, lumbar region

conservative_therapy_weeks: >= 12
prior_imaging: true
imaging_confirms_instability_or_spondylolisthesis: true
```

The diagnosis is synthetic scenario truth, not a value SHN required us to use.

The ServiceRequest projects the diagnosis as `reasonCode` for future PAS work. The DTR QuestionnaireResponse itself only contains facts the payer Questionnaire actually asks for.

## Current semantic map

| Questionnaire item | Payer question | MediLacra fact |
|---|---|---|
| 1.1 | Weeks of conservative therapy completed | conservative_therapy_weeks |
| 1.2 | Imaging confirms instability or spondylolisthesis | imaging_confirms_instability_or_spondylolisthesis |

`prior_imaging=true` is explicitly **not** accepted as evidence for item 1.2.

## Fail-closed behavior

Materialization stops if:

- the DTR package does not contain exactly one Questionnaire and one QuestionnaireResponse,
- Patient identity differs from MediLacra reality,
- Coverage identity differs from MediLacra reality,
- the QuestionnaireResponse references a different questionnaire,
- a known question changes text or datatype,
- a required question has no registered semantic mapping,
- the mapped fact is absent from reality.

Only after all required mapped facts are available is the QuestionnaireResponse marked `completed`.

## Materialize the 34-case live DTR cohort

```bash
DTR_BATCH="connectathon/results/shn_bulk_dtr/shn_bulk_dtr_0300_0399"

python -m connectathon.shn_dtr_questionnaire_response \
  --dtr-batch "$DTR_BATCH"
```

Output:

```text
connectathon/results/shn_bulk_dtr/shn_bulk_dtr_0300_0399/materialized/
  manifest.json
  shn_lumbar_fusion_0300/
    questionnaire_response.json
    materialization.json
  ...
```

The batch manifest records Patient/Coverage/ServiceRequest identity, diagnosis, questionnaire, completion status and answer count for every case.


## First 34-case materialization result

Local validation completed successfully:

```text
26 passed
```

The saved 34-case live DTR cohort was then materialized from the payer-returned Questionnaire packages.

Batch result:

```text
count:       34
completed:   34
two_answers: 34
diagnosis:   ICD-10-CM M43.16 — Spondylolisthesis, lumbar region
```

A spot-check of seed 300 confirmed that the completed QuestionnaireResponse preserved the payer-returned DTR profile, questionnaire canonical, Patient reference and qr-coverage reference, while materializing:

```text
1.1 = 12
1.2 = true
```

Both answers carry DTR information-origin metadata with `source=auto`.

This closes the QuestionnaireResponse materialization boundary for the current lumbar-fusion cohort. The next experiment is PAS construction from the same MediLacra reality plus the completed DTR response.

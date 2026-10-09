# SHN MVP-0 — MediLacra lumbar-fusion scenario

**Date:** 2026-10-09  
**Scenario:** lumbar spinal fusion  
**SHN route:** 00301  
**CPT:** 22633

## Why this scenario exists

The first independently generated MediLacra CRD used CPT `72148` and successfully crossed SHN, but route 00301 had no explicit payer rule for that service. The payer therefore returned its documented no-rule/default response and no DTR questionnaire.

This scenario changes the clinical service while keeping the experiment controlled.

For the same seed, MediLacra keeps the same:

- patient,
- coverage,
- synthetic source payer,
- SHN transport path,
- SHN test payer route.

It creates new identities for the:

- encounter,
- visit/account,
- ServiceRequest,
- transaction.

That avoids redefining the earlier MRI ServiceRequest as surgery.

## Synthetic reality

The lumbar-fusion encounter is generated as an outpatient spine-clinic ordering encounter:

```text
Patient
  -> spine-clinic Encounter
      specialty: Orthopaedic Surgery of the Spine
      taxonomy: 207XS0117X
  -> Coverage
  -> new ServiceRequest
      CPT 22633
      Lumbar spinal fusion
```

The reality also carries the existing clinical-history facts needed for later DTR work:

- at least 12 weeks of conservative therapy,
- prior imaging present,
- no neurologic deficit in this seed.

These facts are part of MediLacra reality. They are **not** inserted into the CRD response or used to manufacture a payer decision.

## SHN expectation

SHN's route-00301 test documentation records CPT `22633` as the lumbar-fusion case. The documented CRD response is expected to contain:

```text
covered      = conditional
pa-needed    = auth-needed
doc-needed   = clinical
doc-purpose  = withpa
info-needed  = OTH
questionnaire =
  http://example.org/fhir/Questionnaire/LumbarSpinalFusion
```

That expectation is written separately to `expected_shn_behavior.json`. It is not embedded in the outbound CRD request.

## Generate

```bash
python -m connectathon.shn_lumbar_fusion --seed 43
```

Artifacts:

```text
connectathon/results/shn_lumbar_fusion/shn_lumbar_fusion_0043/
  reality.json
  crd_request.json
  expected_invariants.json
  expected_shn_behavior.json
```

## Test boundary

Before any live send, local tests assert that:

- patient/coverage identity is unchanged from the seed-43 MediLacra control,
- the encounter and ServiceRequest have new identities,
- encounter context is spine/orthopaedic rather than radiology,
- the order is CPT 22633,
- the CRD projection preserves Patient -> Coverage -> ServiceRequest relationships,
- route 00301 is applied only at the network boundary,
- neither `MBR-COVERED` nor the old CPT `72148` appears,
- the expected questionnaire exists only in the expectation artifact, not the outbound request.

The live send is the next experiment.


## First live lumbar-fusion CRD — 2026-10-09 16:59 UTC

The generated lumbar-fusion CRD was sent through the same authenticated provider-test path.

**Network evidence**

- HTTP: `200`
- X-Correlation-Id: `medilacra-lumbar-fusion-crd-20261009T165957Z`
- X-SHN-Leg-Id: `6c6fe2654f1dbc9e27f5ab7991425dda`
- Trace: `https://admin.shn-preview.org/connectathon/trace/medilacra-lumbar-fusion-crd-20261009T165957Z`

**Returned semantics**

SHN returned the same MediLacra ServiceRequest `SR-8d46465f88045bdb`, still linked to:

- Patient `ML-c89f42c8921c52e7`
- Coverage `COV-cf3716e963a45256`
- CPT `22633`

The payer's coverage-information extension returned:

- `covered = conditional`
- `pa-needed = auth-needed`
- `doc-needed = clinical`
- `doc-purpose = withpa`
- `info-needed = OTH`
- `questionnaire = http://example.org/fhir/Questionnaire/LumbarSpinalFusion`
- billing code `22633`
- coverage assertion `lumbar-fusion-2026-10-09-COV-cf3716e963a45256`

This matches the documented 00301 lumbar-fusion rule exactly.

### DTR boundary

The next request is now data-driven:

```text
MediLacra reality
    ↓
generated CRD
    ↓
SHN payer rule
    ↓
returned questionnaire canonical
    ↓
generated DTR package request
```

The DTR generator refuses to proceed if the CRD response has no questionnaire or has more than one distinct questionnaire canonical. It does not hardcode a fallback questionnaire.


## First live MediLacra-derived DTR — 2026-10-09 17:06 UTC

The DTR package request generated from the live CRD response was sent through the same authenticated SHN provider-test path.

**Network evidence**

- HTTP: `200`
- X-Correlation-Id: `medilacra-lumbar-fusion-dtr-20261009T170631Z`
- X-SHN-Leg-Id: `16d3c96cb741b84eacf4cde5a21dfb55`
- Trace: `https://admin.shn-preview.org/connectathon/trace/medilacra-lumbar-fusion-dtr-20261009T170631Z`

**Returned package**

The payer returned a DTR `Parameters` response with:

- one `Questionnaire`, id `LumbarSpinalFusion`
- one `QuestionnaireResponse`, id `LumbarSpinalFusion-__unresolved-member`
- questionnaire canonical `http://example.org/fhir/Questionnaire/LumbarSpinalFusion`
- Questionnaire title `Lumbar Spinal Fusion Documentation`
- QuestionnaireResponse subject `Patient/ML-c89f42c8921c52e7`
- qr-coverage reference `Coverage/COV-cf3716e963a45256`

The Questionnaire asks two required questions:

1. `1.1` — Weeks of conservative therapy completed (integer)
2. `1.2` — Imaging confirms instability or spondylolisthesis (boolean)

The returned QuestionnaireResponse is `in-progress` with both items unfilled.

The payer also returned an informational warning that demographic pre-population was skipped because no payer-held member matched the sender-supplied MediLacra patient/member identifiers. This is expected for the independent synthetic member and did not prevent the questionnaire package from being returned.

### Important semantic boundary exposed by DTR

MediLacra already has:

- `conservative_therapy_weeks = 12`
- `prior_imaging = true`

Question `1.1` can be answered directly from the existing reality.

Question `1.2` **cannot** be answered from `prior_imaging = true`. Having prior imaging is not equivalent to imaging confirming instability or spondylolisthesis.

Do not map that existing boolean into the payer questionnaire.

The next reality change must add an explicit clinical fact for the finding the payer asks about (for example, `imaging_confirms_instability_or_spondylolisthesis`) and only then project that fact into QuestionnaireResponse item `1.2`.

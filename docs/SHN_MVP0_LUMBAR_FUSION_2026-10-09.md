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

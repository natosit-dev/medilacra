# SHN MVP-0 — MediLacra-generated CRD

**Date:** 2026-10-09  
**Phase:** first substitution after the live 00301 control baseline

## Purpose

The live baseline proves that MediLacra's authenticated client can send the SHN reference CRD, DTR and PAS fixtures through the provider test endpoint.

This phase changes exactly one thing:

> Generate the CRD request from MediLacra's synthetic reality instead of sending SHN's reference CRD fixture.

The frozen reference control under `connectathon/shn_live_baseline_00301/` is not modified.

## Ontology

The source of truth remains `SHNMVP0Reality`:

```text
MediLacra reality
  Patient
  Encounter
  Transaction
  Coverage identity
  ServiceRequest identity
       |
       v
supporting FHIR projection
       |
       v
SHN CRD adapter
       |
       +-- Patient prefetch
       +-- Coverage prefetch
       +-- draft ServiceRequest
       +-- empty history searchsets
       |
       v
CRD order-sign request
```

The SHN payer route is deliberately **not** written back into the MediLacra source reality.

MediLacra currently represents the synthetic payer with its own identifier. At the network boundary, the CRD adapter materializes:

```text
urn:oid:2.16.840.1.113883.6.300 | 00301
```

inside a contained payor Organization on Coverage so the SHN provider test endpoint can route the request.

The contained network Organization is named `SHN reference payer route 00301`. The source synthetic payer (for seed 43, `Blue Cross PPO`) remains recorded in the reality/invariant artifacts but is not mislabeled with the SHN route identifier.

This is an explicit **test-network payer substitution**. It is not a claim that MediLacra's synthetic insurance plan is intrinsically the SHN reference payer.

## What is generated

Run:

```bash
python -m connectathon.shn_medilacra_crd --seed 43
```

Output:

```text
connectathon/results/shn_medilacra_crd/shn_mvp0_0043/
  reality.json
  crd_request.json
  expected_invariants.json
```

For seed 43, the CRD request uses the actual MediLacra-generated patient id, coverage id and service-request id. It does **not** use the reference fixture's `MBR-COVERED` patient.

The ServiceRequest is the one already projected by MediLacra's MVP-0 supporting FHIR: CPT `72148`, MRI lumbar spine without contrast. The CRD adapter changes its status to `draft` because it is being sent in CDS Hooks `draftOrders`.

## Expected invariants

Before sending anything to SHN, local tests assert:

- CRD `context.patientId` is the MediLacra patient.
- Patient prefetch is that same patient.
- Coverage beneficiary is that same patient.
- The draft order is the same MediLacra ServiceRequest.
- The draft order still references the same Coverage.
- The service code is unchanged from MediLacra's supporting FHIR projection.
- The source MediLacra Coverage retains its own payer identity.
- Only the network projection receives the SHN route identifier.
- `MBR-COVERED` does not appear in the generated request.
- generation remains deterministic by seed.

## Decision point after generation

This request will almost certainly not produce the same payer decision as the frozen G0151 reference case. That is expected.

The control asks whether the network path works.

This request asks a different question:

> What does route 00301 do when an independently generated MediLacra patient and order are carried through the same proven CRD path?

The first live run should therefore be evaluated for routing, acceptance, returned semantics and trace behavior — not for equality with the reference fixture's HomeHealthAssessment response.


## Pre-send correction

The first generated artifact exposed an important semantic issue before any live request was sent: the adapter initially kept the synthetic payer's display name while assigning the contained Organization the SHN `00301` identifier. That would have made one Organization simultaneously claim to be the synthetic payer and the SHN reference payer.

The adapter was corrected so source payer identity and network test-payer identity are separate. Tests now assert this distinction.


## First live MediLacra-generated CRD send — 2026-10-09 16:49 UTC

The first request generated from MediLacra reality was sent through the same authenticated SHN provider-test path used by the frozen control.

**Request identity**

- Case: `shn_mvp0_0043`
- Patient: `Patient/ML-c89f42c8921c52e7`
- Coverage: `Coverage/COV-cf3716e963a45256`
- ServiceRequest: `ServiceRequest/SR-0c01d7a890005f67`
- Service: CPT `72148` — MRI lumbar spine without contrast
- Network test payer substitution: `urn:oid:2.16.840.1.113883.6.300|00301`

**Network evidence**

- HTTP: `200`
- X-Correlation-Id: `medilacra-generated-crd-20261009T164903Z`
- X-SHN-Leg-Id: `aed36514db53ec3c5de3a1cc5a47026d`
- Trace: `https://admin.shn-preview.org/connectathon/trace/medilacra-generated-crd-20261009T164903Z`

**Returned semantics**

The payer returned no cards and one `systemActions` update on the **same MediLacra ServiceRequest**. The returned resource preserved:

- ServiceRequest id `SR-0c01d7a890005f67`
- Patient reference `Patient/ML-c89f42c8921c52e7`
- Coverage reference `Coverage/COV-cf3716e963a45256`
- CPT `72148`
- status `draft`
- intent `order`

The coverage-information extension returned:

- `covered = conditional`
- `info-needed = detail-code`
- no `pa-needed`
- no `doc-needed`
- no questionnaire canonical
- `coverage-assertion-id = default-1791564543908`

This matches the 00301 reference payer's documented **no-rule default** shape: `covered=conditional` with `info-needed=detail-code`.

### Interpretation

This is a successful live MediLacra → SHN semantic round trip for CRD.

The generated patient, coverage and order were accepted, routed, and returned with their identity relationships intact. The service itself did not hit one of route 00301's explicit prior-authorization rules, so the CRD path ended in the payer's default coverage response rather than a DTR handoff.

That means DTR should **not** be fabricated from this response. There is no questionnaire canonical to follow.

The next controlled experiment should keep MediLacra-generated identity and transport unchanged while generating a clinically coherent MediLacra scenario whose service code is known to hit an explicit 00301 rule. That isolates payer-rule selection as the next changed variable.

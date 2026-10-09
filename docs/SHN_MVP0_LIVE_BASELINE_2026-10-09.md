# SHN MVP-0 live provider-network baseline — 2026-10-09

## Purpose

This freezes the first known-good live Smart Health Network provider workflow before MediLacra-generated clinical reality is substituted into the messages.

The important distinction is:

```text
baseline control:
SHN reference payloads
  -> MediLacra test-endpoint credentials
  -> SHN provider test endpoint
  -> route 00301 reference payer

next experiment:
MediLacra synthetic reality
  -> MediLacra CRD / DTR / PAS projections
  -> the same proven transport path
```

The baseline therefore proves transport, authentication, routing, workflow sequencing, payer persistence/matching and SHN observability. It does **not** yet prove that MediLacra-generated data survives the workflow.

## Frozen control kit

The runnable control is committed under:

```text
connectathon/shn_live_baseline_00301/
```

It contains the exact reference fixtures used for the successful run:

- `register-medilacra.json` — registration template only; no credential values.
- `crd-00301.json` — route 00301 CRD order-sign request.
- `dtr-00301.json` — DTR questionnaire-package request template.
- `pas-00301.json` — PAS submit reference Bundle.
- `run-00301.sh` — registration/auth/run harness.
- `README.md` — operator instructions and expected behavior.

Generated `client.json` credentials and `out/` artifacts are intentionally excluded from Git.

## Live run evidence

All calls below were made on 2026-10-09 against `https://pa-test.shn-preview.org`.

### Registration

- Client registration: HTTP 200.
- OAuth client-credentials token: HTTP 200, 300 second lifetime, scope `system/Davinci.write`.

No client secret or bearer token is recorded in this document.

### First complete workflow

| Step | HTTP | Correlation ID | SHN leg ID | Observed result |
|---|---:|---|---|---|
| CRD | 200 | `medilacra-crd-20261009T161834Z` | `277ad87b628083b2aa6a042df8d3c254` | 0 cards; 1 systemAction; covered conditional; PA required; clinical documentation required; HomeHealthAssessment questionnaire returned |
| DTR | 200 | `medilacra-dtr-20261009T162219Z` | `1c52edcc009dae153e0a1d78ce7784d6` | packagebundle: 3 Libraries, 1 Questionnaire, 1 QuestionnaireResponse, 1 ValueSet; expected demographic prepopulation warning |
| PAS submit | 200 | `medilacra-submit-20261009T162222Z` | `75f9b9d16bd708d424f8c552ac25e440` | ClaimResponse complete; A4 Pending; CommunicationRequest `AUTH-TRN0001`, payload `102089-0` |
| PAS inquire | 200 | `medilacra-inquire-20261009T162223Z` | `eb10a81ec87e3d01bab323454e420443` | one matching ClaimResponse; `AUTH-TRN0001` found |

The CRD trace showed the request traversing the provider test door, provider gateway, SHN hub, route 00301 payer gateway and the native reference payer, then returning through the network.

Trace pattern:

```text
https://admin.shn-preview.org/connectathon/trace/<X-Correlation-Id>
```

### Repeatability run

Immediately afterward, `./run-00301.sh all` completed the full sequence again:

| Step | HTTP | Correlation ID | SHN leg ID |
|---|---:|---|---|
| CRD | 200 | not captured in this record | `a8872b98945f6f0ecdef8c0e88ac0aa5` |
| DTR | 200 | not captured in this record | `283e89aa5eb90c3b1b2fc37f4be19b4d` |
| PAS submit | 200 | not captured in this record | `3b33f6846e912704e9a760bff7748dfd` |
| PAS inquire | 200 | not captured in this record | `257e0bcd997733e60c2d368bc72e9153` |

The second submit returned `AUTH-TRN0002`. The following inquiry returned two ClaimResponses and confirmed that `AUTH-TRN0002` was present.

That is useful evidence that the path is not merely stateless request/response plumbing: the payer retained and matched multiple submissions across calls.

## Known reference-payer behavior preserved as control

The following are expected in this baseline and should not be "fixed" while it remains the control:

- CRD returns an empty `cards` array and a `systemActions` update.
- Historical SHN reference documentation notes that route 00301 may omit `FHIRHelpers`; the first live baseline response returned three Library resources, but their identities were not inspected in this record, so this baseline does not claim whether `FHIRHelpers` was present.
- DTR may report demographic prepopulation skipped.
- PAS submit returns A4 Pending with a CommunicationRequest.
- PAS responses may use the payer's own Patient identity.
- Inquiry may return matching claims from other participants.
- Event-window payer data can be cleared overnight; submit again before inquiry after a clearing.

## Baseline rule

Do not turn these files into the MediLacra implementation in place.

When MediLacra begins producing the requests, build a separate projection/adapter path and compare it against this control. If a MediLacra-derived request fails, this baseline gives us a known-good answer to:

> Is the problem authentication/transport/routing, or did the meaning/representation of the generated healthcare data change?

That separation is the point of freezing the baseline.


## Baseline revalidation — 2026-10-09 16:31 UTC

The committed control was pulled into the MediLacra checkout and rerun from
`connectathon/shn_live_baseline_00301/`.

First, each operation was run individually:

| Step | HTTP | Correlation ID | SHN leg ID |
|---|---:|---|---|
| CRD | 200 | `medilacra-crd-20261009T163116Z` | `b3cdca1fc4cae3fec6a5abe5ff9a5fcc` |
| DTR | 200 | `medilacra-dtr-20261009T163116Z` | `ed3701815888c8db298a3ed740a9042b` |
| PAS submit | 200 | `medilacra-submit-20261009T163117Z` | `370d8799d313ecb398e755e3b680f1c3` |
| PAS inquire | 200 | `medilacra-inquire-20261009T163118Z` | `beea024d22e49c5cf3a9bb710ce338af` |

Immediately afterward, the single-command `./run-00301.sh all` path was run:

| Step | HTTP | Correlation ID | SHN leg ID |
|---|---:|---|---|
| CRD | 200 | `medilacra-crd-20261009T163125Z` | `0d7b5176ce8688ada3522f42fe8c655e` |
| DTR | 200 | `medilacra-dtr-20261009T163126Z` | `150aee34ef64088fe026a058b5512e98` |
| PAS submit | 200 | `medilacra-submit-20261009T163126Z` | `c60f35f2d18ca59460edc522f89f5f57` |
| PAS inquire | 200 | `medilacra-inquire-20261009T163127Z` | `a95665116ca91e37fb544a3f25490e47` |

Every provider-network operation returned HTTP 200 in both sequences. This is the
revalidated known-good transport baseline immediately before introducing a
MediLacra-generated CRD payload.

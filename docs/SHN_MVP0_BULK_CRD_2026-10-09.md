# SHN MVP-0 — bulk CRD identity test

**Date:** 2026-10-09  
**Default cohort:** 10 patients, seeds 100–109  
**Scenario held constant:** lumbar fusion / CPT 22633  
**Route held constant:** 00301

## Question

After proving one independently generated MediLacra patient can traverse CRD and DTR, this experiment asks:

> Does SHN preserve patient/coverage/order identity and apply the same payer rule across a cohort of independently generated synthetic patients?

The clinical scenario stays fixed. Synthetic patient identity is the experimental variable.

## Generation

```bash
python -m connectathon.shn_bulk_crd --start-seed 100 --count 10
```

This produces:

```text
connectathon/results/shn_bulk_crd/shn_bulk_lumbar_fusion_0100_0109/
  manifest.json
  cases/
    shn_lumbar_fusion_0100/
      reality.json
      crd_request.json
      expected_invariants.json
      expected_shn_behavior.json
    ...
    shn_lumbar_fusion_0109/
      ...
```

Every case has a distinct Patient, Coverage, encounter, member id and ServiceRequest. All cases use CPT 22633 and route 00301.

## Live runner

The live runner uses the existing local SHN credentials through the frozen baseline runner. It never reads or commits credentials itself.

```bash
connectathon/shn_bulk_crd_send.sh \
  connectathon/results/shn_bulk_crd/shn_bulk_lumbar_fusion_0100_0109
```

Each request receives its own correlation id:

```text
medilacra-bulk-crd-<seed>-<UTC timestamp>
```

Raw responses and headers are written under the batch's local `live/` directory.

The runner produces `live/run-log.tsv` with:

- expected Patient / Coverage / ServiceRequest ids,
- returned ServiceRequest / Patient / Coverage references,
- `identity_match`,
- HTTP status,
- CRD coverage semantics,
- returned questionnaire,
- X-Correlation-Id,
- X-SHN-Leg-Id,
- trace URL.

For this first cohort, the primary success criteria are:

1. every request returns 2xx,
2. every row has `identity_match=true`,
3. every row returns the lumbar-fusion rule,
4. every row returns the `LumbarSpinalFusion` questionnaire.

A divergent row should be investigated by correlation id before rerunning or changing the generator.


## First live bulk run — seeds 100–109

The first 10-patient cohort completed successfully.

**Aggregate result**

- 10/10 requests returned HTTP 200.
- 10/10 returned the same Patient, Coverage and ServiceRequest identities sent by MediLacra.
- 10/10 had `identity_match=true`.
- 10/10 returned `covered=conditional`.
- 10/10 returned `pa-needed=auth-needed`.
- 10/10 returned `doc-needed=clinical`.
- 10/10 returned `info-needed=OTH`.
- 10/10 returned `http://example.org/fhir/Questionnaire/LumbarSpinalFusion`.

No cohort member diverged.

| Seed | Correlation ID | SHN leg ID | HTTP | Identity |
|---:|---|---|---:|---|
| 100 | `medilacra-bulk-crd-100-20261009T171505Z` | `10f902f9625eed0833bc5b5886d4d442` | 200 | match |
| 101 | `medilacra-bulk-crd-101-20261009T171506Z` | `5d8a73d4783f62c2b744f88d28ac274a` | 200 | match |
| 102 | `medilacra-bulk-crd-102-20261009T171506Z` | `89bb10725eabf1110fbd6ec0b45f87e7` | 200 | match |
| 103 | `medilacra-bulk-crd-103-20261009T171507Z` | `29ee76d93b5edab0cd990bb532db5ac2` | 200 | match |
| 104 | `medilacra-bulk-crd-104-20261009T171507Z` | `ce0828de8aa08d5302e0545716814f00` | 200 | match |
| 105 | `medilacra-bulk-crd-105-20261009T171508Z` | `4551fe655d180d8ecf584198514ddb12` | 200 | match |
| 106 | `medilacra-bulk-crd-106-20261009T171508Z` | `9cfd8fb9de332f9e334ff9a73a30245a` | 200 | match |
| 107 | `medilacra-bulk-crd-107-20261009T171508Z` | `cdff191a8ad813eb19f084e8c0ad54b2` | 200 | match |
| 108 | `medilacra-bulk-crd-108-20261009T171509Z` | `7e54083b4bbd227ed6632e0094b77faf` | 200 | match |
| 109 | `medilacra-bulk-crd-109-20261009T171509Z` | `2052d5cf8942df766a8a2c06bcc35a31` | 200 | match |

### Interpretation

Within this cohort, patient identity was not a source of variability in the CRD result. Ten independently generated MediLacra patients traversed the same provider-test route, preserved their Patient/Coverage/ServiceRequest relationships, and selected the same payer rule.

This does **not** establish arbitrary-scale reliability or broader clinical-rule coverage. It establishes repeatability for this controlled 10-patient identity cohort.

The next useful bulk dimension is to vary **clinical service/rule behavior** rather than simply add more patients to the same rule.

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

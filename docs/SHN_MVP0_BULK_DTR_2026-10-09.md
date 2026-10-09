# SHN MVP-0 — bulk DTR continuation

**Date:** 2026-10-09  
**Source cohort:** CRD seeds 300–399  
**DTR-eligible cases:** 34  
**Route:** 00301

## Boundary

The 100-patient CRD experiment produced three different payer behaviors.

Only the cases whose **live CRD response** selected a questionnaire continue into DTR. For this cohort that means the 34 CPT 22633 lumbar-fusion cases.

The 33 explicit not-covered cases and 33 no-rule/default cases stop at CRD.

This is intentional workflow branching, not skipped coverage.

## Build from live CRD responses

The first 100-case CRD run admitted seeds 300–359 and throttled seeds 360–399. The retry matrix later admitted 360–399.

The DTR planner accepts both source directories and deduplicates cases by seed. It ignores failed/throttled response bodies and requires a successful questionnaire-bearing CRD response for every DTR-eligible case.

```bash
python -m connectathon.shn_bulk_dtr \
  --source-matrix connectathon/results/shn_rule_matrix/shn_rule_matrix_0300_0399 \
  --source-matrix connectathon/results/shn_rule_matrix/shn_rule_matrix_0360_0399
```

Expected output:

```text
connectathon/results/shn_bulk_dtr/shn_bulk_dtr_0300_0399/
```

The manifest should contain 34 cases.

## Live send

```bash
connectathon/shn_bulk_dtr_send.sh \
  connectathon/results/shn_bulk_dtr/shn_bulk_dtr_0300_0399
```

The sender records:

- HTTP status
- retry count
- returned Questionnaire canonical
- returned QuestionnaireResponse subject
- returned qr-coverage
- identity match
- package match
- warning count
- correlation id
- SHN leg id

Because the CRD load test exposed HTTP 429 throttling, this runner retries 429 responses up to three attempts, respecting `Retry-After` when present and otherwise backing off 65 seconds.

## Success condition

For all 34 DTR-eligible cases:

```text
HTTP 2xx
identity_match=true
package_match=true
```

A demographic prepopulation warning is expected for independent synthetic members and does not count as failure.

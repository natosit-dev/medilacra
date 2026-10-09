# SHN MVP-0 — mixed CRD payer-rule matrix

**Date:** 2026-10-09  
**Default cohort:** 9 independent synthetic patients  
**Route:** 00301  
**Experimental variable:** clinical service / payer-rule selection

## Why this test

The prior bulk run held CPT 22633 constant and varied patient identity. Ten of ten cases preserved identity and selected the same lumbar-fusion rule.

This matrix now changes the clinical service itself.

Only behaviors with exact code/outcome evidence available to this experiment are included. The matrix deliberately does not infer or guess codes for other SHN test cases.

## Matrix

Three scenarios repeat three times each:

| Scenario | Code | Expected CRD behavior |
|---|---:|---|
| lumbar-fusion-auth | 22633 | conditional; auth-needed; clinical docs; OTH; LumbarSpinalFusion questionnaire |
| explicit-not-covered | 42999 | not-covered; no pa-needed |
| no-rule-default | 72148 | conditional; no pa-needed; detail-code; no questionnaire |

The 42999 expectation comes from the SHN reference payer's explicit not-covered rule. The 72148 default expectation was observed in MediLacra's first live generated CRD and matches the documented no-rule fallback shape.

## Generation

```bash
python -m connectathon.shn_rule_matrix --start-seed 200 --repeats 3
```

Output:

```text
connectathon/results/shn_rule_matrix/shn_rule_matrix_0200_0208/
  manifest.json
  cases/
    ...
```

Every case has a distinct Patient, Coverage, encounter, member id and ServiceRequest.

## Live run

```bash
connectathon/shn_rule_matrix_send.sh \
  connectathon/results/shn_rule_matrix/shn_rule_matrix_0200_0208
```

The runner records both:

- `identity_match`: the returned ServiceRequest, Patient and Coverage match the outbound case.
- `behavior_match`: every response field documented for that scenario matches its expected value.

Expected fields are compared partially: the payer may return additional coverage-information fields without failing the test.

A useful success condition is therefore:

```text
9/9 HTTP 2xx
9/9 identity_match=true
9/9 behavior_match=true
```

If any row diverges, use that row's correlation id and SHN leg id before changing the generator.

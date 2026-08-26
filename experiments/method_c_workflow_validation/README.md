# Method C — Workflow Validation and Correction

## Question

When the reconstructed workflow model is tested against its underlying synthetic evidence, which assumptions are confirmed, which are wrong, and which questions cannot actually be answered?

This branch is stacked on `experiment/method-b-workflow-reconstruction`. It validates the same synthetic workflow world rather than copying it into a second fixture set.

## Validation principle

A validation result and its interpretation are separate fields.

Statuses:

- `PASS`
- `FAIL`
- `WARN`
- `NOT_TESTABLE`

Interpretation classes:

- `EXPECTED_BEHAVIOR`
- `PIPELINE_DEFECT`
- `SOURCE_QUALITY`
- `DOCUMENTATION_CORRECTION`
- `VALIDATOR_LIMITATION`
- `UNKNOWN`

The important rule is simple:

> `FAIL` does not mean `PIPELINE_DEFECT` unless the evidence establishes that interpretation.

## Checks

The MVP runs eleven small checks:

- `VAL-0` grain uniqueness
- `VAL-1` documented lifecycle vs observed lifecycle
- `VAL-2` workflow type mapping
- `VAL-3` type-specific assignment precedence
- `VAL-4` appointment assignment reconciliation
- `VAL-5` two-hop closure relationship
- `VAL-6` closure/state consistency
- `VAL-7` due-status derivation
- `VAL-8` source population reconciliation
- `VAL-9` critical field coverage
- `VAL-10` effective-dated staff activity evidence boundary

`VAL-1` is intentionally expected to fail: the original source notes omit the valid `canceled` state. The correct action is to update documentation, not remove valid data.

`VAL-10` is intentionally `NOT_TESTABLE`: the current synthetic staff evidence has no effective-dated employment history.

## Correction artifact

`CORRECTED_SOURCE_NOTES.md` records the evidence-backed corrections while preserving the original `SOURCE_NOTES.md` as provenance.

That gives the experiment an explicit loop:

```text
initial documentation
        ↓
reconstructed model
        ↓
validation
        ↓
contradiction classified
        ↓
corrected documentation
```

## Run

From the repository root:

```bash
python experiments/method_c_workflow_validation/run_validation.py
```

By default the validator first reruns Method B so it tests a freshly generated reconstruction.

To validate existing outputs:

```bash
python experiments/method_c_workflow_validation/run_validation.py --skip-reconstruct
```

Generated outputs:

```text
experiments/method_c_workflow_validation/output/
    validation_results.csv
    validation_history.csv
    validation_summary.json
    VALIDATION_RESULTS.md
```

## What this establishes

Validation is not a cosmetic pass/fail layer. It is a mechanism for distinguishing confirmed behavior, implementation defects, source-quality observations, incorrect documentation, and questions that the available evidence cannot answer.

## What this does not establish

This fixture is deterministic and intentionally tiny. It does not test statistical thresholds, large-scale anomaly detection, production metadata behavior, or clinical correctness. Those would be separate experiments.

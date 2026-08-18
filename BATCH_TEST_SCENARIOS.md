# MediLacra Batch Test Scenarios and Scale Commands

Branch: `agent/connectathon-fast-generation-prep`

This document provides a reusable CLI test suite for the batch-generation path. It separates behavioral/semantic checks from scale/performance runs so changes can be validated at small size before committing to long benchmarks.

All commands assume the current working directory is the MediLacra repository root and the branch above is checked out.

## Behavioral and Semantic Test Scenarios

### 1. Tiny smoke test

Fastest full-pipeline check.

```bash
python -m hl7_demo.batch_cli --patients 10 --encounters-per-patient 2 --observations-per-encounter 3 --transactions-per-encounter 2 --seed 42 --bulk --out-dir ./output/test_smoke
```

Expected shape:

- 10 patients
- 20 encounters
- 60 observations
- 40 transactions

### 2. Standard regression test

General-purpose validation after code changes.

```bash
python -m hl7_demo.batch_cli --patients 100 --encounters-per-patient 2 --observations-per-encounter 5 --transactions-per-encounter 2 --seed 42 --bulk --out-dir ./output/test_regression
```

Expected shape:

- 100 patients
- 200 encounters
- 1,000 observations
- 400 transactions
- 1,700 total entities
- 1,000 HL7 messages with labs enabled

### 3. Bulk writer test

Exercises the persistent bulk-file-handle path.

```bash
python -m hl7_demo.batch_cli --patients 1000 --encounters-per-patient 2 --observations-per-encounter 5 --transactions-per-encounter 2 --seed 42 --bulk --out-dir ./output/test_bulk_writer
```

Use this to compare against previous 1,000-patient timing results.

### 4. Per-encounter file test

Checks the individual-file output path independently of bulk mode.

```bash
python -m hl7_demo.batch_cli --patients 10 --encounters-per-patient 2 --observations-per-encounter 3 --transactions-per-encounter 2 --seed 42 --per-encounter --out-dir ./output/test_per_encounter
```

### 5. No observations

Tests missing clinical observations while preserving patient, encounter, and financial activity.

```bash
python -m hl7_demo.batch_cli --patients 100 --encounters-per-patient 2 --observations-per-encounter 0 --transactions-per-encounter 2 --seed 42 --bulk --out-dir ./output/test_no_observations
```

Useful for checking empty ORU and diagnosis behavior.

### 6. No transactions

Tests clinical activity without financial activity.

```bash
python -m hl7_demo.batch_cli --patients 100 --encounters-per-patient 2 --observations-per-encounter 5 --transactions-per-encounter 0 --seed 42 --bulk --out-dir ./output/test_no_transactions
```

### 7. Sparse encounter

Near-minimum dataset shape.

```bash
python -m hl7_demo.batch_cli --patients 100 --encounters-per-patient 1 --observations-per-encounter 0 --transactions-per-encounter 0 --seed 42 --bulk --out-dir ./output/test_sparse
```

Useful for inspecting the minimum patient/encounter representation produced by the batch path.

### 8. Gender Harmony off

Control run with Gender Harmony projection disabled.

```bash
python -m hl7_demo.batch_cli --patients 1000 --encounters-per-patient 2 --observations-per-encounter 5 --transactions-per-encounter 2 --seed 42 --bulk --no-gender-harmony --out-dir ./output/test_no_gender_harmony
```

### 9. Labs off

Isolates the cost and behavior of the separate synthetic lab path.

```bash
python -m hl7_demo.batch_cli --patients 1000 --encounters-per-patient 2 --observations-per-encounter 5 --transactions-per-encounter 2 --seed 42 --bulk --no-labs --out-dir ./output/test_no_labs
```

### 10. Vitals off

Isolates the local vitals-prediction path.

```bash
python -m hl7_demo.batch_cli --patients 1000 --encounters-per-patient 2 --observations-per-encounter 5 --transactions-per-encounter 2 --seed 42 --bulk --no-vitals --out-dir ./output/test_no_vitals
```

### 11. Minimal projection overhead

Turns off labs, vitals, and Gender Harmony while keeping the core entity and message path.

```bash
python -m hl7_demo.batch_cli --patients 1000 --encounters-per-patient 2 --observations-per-encounter 5 --transactions-per-encounter 2 --seed 42 --bulk --no-labs --no-vitals --no-gender-harmony --out-dir ./output/test_core_only
```

This provides a useful lower bound for the current architecture.

### 12. Determinism test A/B

Run the same shape twice with the same seed.

```bash
python -m hl7_demo.batch_cli --patients 100 --encounters-per-patient 2 --observations-per-encounter 5 --transactions-per-encounter 2 --seed 8675309 --bulk --out-dir ./output/test_seed_a
```

```bash
python -m hl7_demo.batch_cli --patients 100 --encounters-per-patient 2 --observations-per-encounter 5 --transactions-per-encounter 2 --seed 8675309 --bulk --out-dir ./output/test_seed_b
```

Timestamps and message-control identifiers may prevent byte-for-byte equality, but seeded reality and aggregate distributions should be comparable.

### 13. Different-seed test

Same shape with deliberately different generated reality.

```bash
python -m hl7_demo.batch_cli --patients 100 --encounters-per-patient 2 --observations-per-encounter 5 --transactions-per-encounter 2 --seed 666 --bulk --out-dir ./output/test_seed_different
```

### 14. Verbose debugging

Use when a small run needs detailed per-entity and per-segment logging.

```bash
python -m hl7_demo.batch_cli --patients 5 --encounters-per-patient 1 --observations-per-encounter 2 --transactions-per-encounter 1 --seed 42 --bulk --verbose --out-dir ./output/test_verbose
```

### 15. Clean benchmark mode

Disables progress rendering for the cleanest timing comparison.

```bash
python -m hl7_demo.batch_cli --patients 1000 --encounters-per-patient 2 --observations-per-encounter 5 --transactions-per-encounter 2 --seed 42 --bulk --no-progress --out-dir ./output/test_benchmark_clean
```

## Scale and Performance Runs

The established workload ratio is:

```text
1 patient
2 encounters
10 observations
4 transactions
```

That produces 17 entities per patient and, with labs enabled, 10 HL7 messages per patient.

### 10K-scale run

```bash
python -m hl7_demo.batch_cli --patients 588 --encounters-per-patient 2 --observations-per-encounter 5 --transactions-per-encounter 2 --seed 42 --bulk --out-dir ./output/scale_10k
```

Approximate total: 9,996 entities.

### 100K-scale run

```bash
python -m hl7_demo.batch_cli --patients 5882 --encounters-per-patient 2 --observations-per-encounter 5 --transactions-per-encounter 2 --seed 42 --bulk --out-dir ./output/scale_100k
```

Approximate total: 99,994 entities.

### 250K-scale run

```bash
python -m hl7_demo.batch_cli --patients 14706 --encounters-per-patient 2 --observations-per-encounter 5 --transactions-per-encounter 2 --seed 42 --bulk --out-dir ./output/scale_250k
```

Approximate total: 250,002 entities.

### 500K-scale run

```bash
python -m hl7_demo.batch_cli --patients 29412 --encounters-per-patient 2 --observations-per-encounter 5 --transactions-per-encounter 2 --seed 42 --bulk --out-dir ./output/scale_500k
```

Approximate total: 500,004 entities.

### 1 million entities

Established large benchmark shape.

```bash
python -m hl7_demo.batch_cli --patients 58824 --encounters-per-patient 2 --observations-per-encounter 5 --transactions-per-encounter 2 --seed 42 --bulk --out-dir ./output/scale_1m
```

Expected totals:

- 58,824 patients
- 117,648 encounters
- 588,240 observations
- 235,296 transactions
- 1,000,008 total entities
- 588,240 HL7 messages with labs enabled

### 1 million entities, clean benchmark

Same workload with progress rendering disabled.

```bash
python -m hl7_demo.batch_cli --patients 58824 --encounters-per-patient 2 --observations-per-encounter 5 --transactions-per-encounter 2 --seed 42 --bulk --no-progress --out-dir ./output/scale_1m_clean
```

### 1 million entities, core-only

Large-scale lower-bound test with labs, vitals, and Gender Harmony disabled.

```bash
python -m hl7_demo.batch_cli --patients 58824 --encounters-per-patient 2 --observations-per-encounter 5 --transactions-per-encounter 2 --seed 42 --bulk --no-labs --no-vitals --no-gender-harmony --out-dir ./output/scale_1m_core_only
```

## Recommended Working Ladder

For normal development:

1. `100 x 2 x 5 x 2` for regression testing.
2. `1,000 x 2 x 5 x 2` for performance comparisons.
3. `10K -> 100K -> 500K -> 1M` for scale testing.

This ladder gives enough points to see whether runtime remains roughly linear or whether file size, generation, projection, or I/O begins to dominate at larger scales.

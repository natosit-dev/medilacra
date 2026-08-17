# MediLacra Batch Generation Prep

This branch adds an experiment-oriented generation path without changing the existing MediLacra pipeline.

## Purpose

Generate linked MediLacra healthcare data with explicit cardinality controls, measure throughput, and avoid external SDOH API calls during batch runs.

The current Patient / Encounter / Transaction / Observation generators remain authoritative. Gender Harmony generation remains enabled by default.

## Run

```bash
python -m hl7_demo.batch_cli \
  --patients 1000 \
  --encounters-per-patient 2 \
  --observations-per-encounter 5 \
  --transactions-per-encounter 2 \
  --seed 42 \
  --bulk \
  --out-dir ./output/batch_001
```

That shape requests:

- 1,000 patients
- 2,000 encounters
- 10,000 observations
- 4,000 transactions
- one ADT, narrative ORU, and DFT per encounter
- one lab ORM/ORU pair per encounter unless `--no-labs` is supplied

## Cardinality controls

```text
--patients N
--encounters-per-patient N
--observations-per-encounter N
--transactions-per-encounter N
```

Patients and encounters must be at least 1. Observations and transactions may be 0 for missing-data/completeness experiments.

## Output controls

```text
--bulk             one run-level file per message type (default)
--per-encounter    one file per encounter/message type
--out-dir PATH
```

## Feature controls

```text
--no-labs
--no-vitals
--no-gender-harmony
```

Gender Harmony remains on by default. The batch ADT includes Gender Identity, Pronouns, and SPCU observations using the existing MediLacra selection logic.

## SDOH behavior

The batch path does not call AirNow, Census ACS, PLACES, or BLS APIs.

For components that historically depended on SDOH enrichment:

- vitals use the existing missing-enrichment fallback inputs (`poverty=0`, `AQI=50`)
- lab generation uses the same fallback inputs locally

The legacy pipeline and `hl7_demo/sdoh.py` are untouched on this prep branch; they are simply outside the batch execution path.

## Performance output

Each run prints entity counts, message counts, elapsed wall-clock time, and generated entity throughput so later optimization work can be measured rather than guessed.

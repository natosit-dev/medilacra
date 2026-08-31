# Disco Inferno

> **Status: GOOD ENOUGH — MVP COMPLETE (2026-08-31)**
>
> The experiment harness, Streamlit control surface, detached worker/stop controls, offline-by-default SDOH boundary, timestamped DuckDB/HL7 artifacts, Beatrice/Inferno comparison, and first recorded evidence run are complete. Further expansion is deferred until a new experiment requires it.

**Disco Inferno** is MediLacra's controlled entropy experiment.

It holds the generated reality and model constant, preserves an untouched reference representation named **Beatrice**, then produces deterministic cursed copies of the same model.

```text
MediLacra reality
      |
      v
   Beatrice
      |
      +--------------------+
      |                    |
      v                    v
  untouched            Disco Inferno
                           |
                         Minos
                           |
              +------------+------------+
              |            |            |
            Charon        Null        Cerberus
              |            |            |
        drop identifier  null field  duplicate record
```

Beatrice is **not** reality itself. Beatrice is the faithful tabular representation of the generated MediLacra reality. Inferno outputs are corrupted copies of Beatrice.

## Core experiment

Structured Sparsity holds reality constant while changing representation structure. Disco Inferno holds both reality and representation structure constant while changing information quality.

```text
STRUCTURED SPARSITY
same reality
    ↓
representation A ↔ representation B
    ↓
what relationships survive structural transformation?

DISCO INFERNO
same reality
same model
    ↓
Beatrice ↔ cursed representation
    ↓
what knowledge survives information degradation?
```

## MVP operators

| Name | Machine operator | Default target | Meaning |
|---|---|---|---|
| Control | `control` | none | Proves the comparison harness reports zero damage. |
| Charon | `drop_identifier` | `observations.encounter_id` | Removes the explicit encounter relationship from the representation. |
| Null | `null_field` | 10% of `observations.observation_text` | Removes generated facts while retaining rows and identifiers. |
| Cerberus | `duplicate_record` | 10% of `transactions` | Adds exact copies, increasing represented cardinality without increasing reality entities. |

## Seeds

Defaults are intentionally separate:

- Reality seed: `42` — which universe exists.
- Inferno seed: `666` — which parts of that universe are cursed.

The same pair must produce the same reality and the same corruption selections.

## Recorded MVP result

Canonical good-enough evidence record:

- [`results/DISCO_INFERNO_MVP_RESULTS_20260831T082301-0400.md`](results/DISCO_INFERNO_MVP_RESULTS_20260831T082301-0400.md)

Recorded run `20260831T082301-0400`:

| Measure | Result |
|---|---:|
| Patients | 100 |
| Encounters | 200 |
| Observations | 400 |
| Transactions | 400 |
| Charon affected | 400 observations / 100% |
| Null affected | 68 observations / 17% |
| Cerberus affected | 24 transactions / 6% |
| Control delta | 0 |

That run used Reality seed `42`, Inferno seed `666`, Charon on `observations.encounter_id`, Null on `observations.icd_code`, Cerberus on `transactions`, external SDOH enrichment OFF, and lab ORM/ORU exports OFF.

The result record preserves the observed measurements, artifact inventory, and interpretation boundary without committing generated binary output as source code.

## Streamlit UI

From the repository root:

```bash
streamlit run medi_lacra_app.py
```

Open the **Disco Inferno** page in the Streamlit page list.

The baseline controls default to:

- 100 patients
- 2 encounters per patient
- 2 observations per encounter
- 2 transactions per encounter
- Reality seed `42`
- Inferno seed `666`
- Charon: `observations.encounter_id`
- Null: 10% of `observations.observation_text`
- Cerberus: 10% of `transactions`
- external SDOH enrichment: **OFF**

The UI exposes the cohort size, both seeds, Charon table/identifier target, Null table/field/intensity, Cerberus table/intensity, lab-message export toggle, and explicit SDOH opt-in.

### Process control

Generation runs in a detached worker process rather than inside Streamlit's execution thread.

Only one Disco Inferno worker may hold the generator lock at a time. The UI exposes the active PID/job state, live worker log, and a **Stop active run** control that terminates the worker without killing Streamlit.

Terminal fallback:

```bash
python -m experiments.disco_inferno.process_control status
python -m experiments.disco_inferno.process_control stop
```

Stale locks are cleared when the recorded PID is no longer alive.

## Offline SDOH boundary

Disco Inferno is local/offline by default. When SDOH is disabled, the worker installs an offline boundary before generation/projection begins so Census, AirNow, PLACES, and BLS lookup paths cannot reach the network.

This is deliberate: external enrichment is not part of the core entropy experiment and should not make deterministic local generation depend on public API latency or availability.

Enable SDOH only when it is actually part of the experiment.

## CLI

Default local/offline run:

```bash
python experiments/disco_inferno/run_experiment.py
```

Explicit external SDOH enrichment:

```bash
python experiments/disco_inferno/run_experiment.py --with-sdoh
```

Useful overrides:

```bash
python experiments/disco_inferno/run_experiment.py \
  --reality-seed 42 \
  --inferno-seed 666 \
  --charon-table observations \
  --charon-field encounter_id \
  --null-table observations \
  --null-field observation_text \
  --null-fraction 0.10 \
  --duplicate-table transactions \
  --duplicate-fraction 0.10
```

## Timestamped output bundle

Each run writes a timestamped directory under `experiments/disco_inferno/output/`. The files themselves also carry the same run timestamp.

```text
<run-id>/
├── beatrice/
│   ├── patients_<run-id>.csv
│   ├── encounters_<run-id>.csv
│   ├── observations_<run-id>.csv
│   └── transactions_<run-id>.csv
├── inferno/
│   ├── control/*.csv
│   ├── charon/*.csv
│   ├── null/*.csv
│   └── cerberus/*.csv
├── hl7/
│   ├── ADT_A01_<run-id>.hl7
│   ├── ORU_R01_<run-id>.hl7
│   ├── DFT_P03_<run-id>.hl7
│   ├── ORM_O01_LABS_<run-id>.hl7       # when labs enabled
│   └── ORU_R01_LABS_<run-id>.hl7       # when labs enabled
├── source_reality_<run-id>.duckdb
├── metrics_<run-id>.csv
├── manifest_<run-id>.json
├── DISCO_INFERNO_REPORT_<run-id>.md
└── DISCO_INFERNO_<run-id>.zip
```

The source DuckDB contains the full untouched Beatrice tables: patients, encounters, observations, and transactions.

HL7 is projected from the same untouched generated cases using MediLacra's existing message builders. One bulk file is produced for each enabled message family. Narrative ORU and laboratory ORU remain separate products, matching the existing MediLacra pipeline convention.

The manifest is the corruption receipt: exact operator, target, intensity, selected positions/record identifiers, source counts, HL7 counts/files, and source DuckDB filename.

The Streamlit UI exposes both a single ZIP download for the complete experiment bundle and individual downloads for the report, manifest, metrics, DuckDB, and HL7 files.

## Tests

```bash
pytest -q \
  tests/test_disco_inferno.py \
  tests/test_disco_inferno_process_control.py \
  tests/test_disco_inferno_offline_sdoh.py
```

The tests protect the central boundaries:

- **Beatrice is never mutated in place.**
- corruption selection is deterministic;
- control delta is zero;
- corruption counts are exact;
- timestamped CSV and DuckDB artifacts materialize;
- worker locking/stopping/stale-lock recovery behave predictably;
- offline SDOH mode does not enter external enrichment paths.

## Good-enough boundary

This phase intentionally stops here.

The MVP does **not** calculate a universal entropy score. It measures direct representational damage first.

Deferred until demanded by a future experiment:

- reconstruction / recoverability scoring;
- universal or weighted entropy metrics;
- compound corruption (reserved name: **Lucifer**);
- direct HL7/FHIR corruption;
- cognition experiments;
- larger corruption catalogs;
- additional productization.

The next research question is deliberately left open:

> **Given only the cursed side, what parts of the original reality can still be known?**

For now, Disco Inferno is accepted as a reusable Medilacra experimental primitive.

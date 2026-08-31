# Disco Inferno

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

## MVP operators

| Name | Machine operator | Default target | Meaning |
|---|---|---|---|
| Control | `control` | none | Proves the comparison harness reports zero damage. |
| Charon | `drop_identifier` | `observations.encounter_id` | Removes the explicit encounter relationship from the representation. |
| Null | `null_field` | 10% of `observations.observation_text` | Removes generated result facts while retaining rows and identifiers. |
| Cerberus | `duplicate_record` | 10% of `transactions` | Adds exact copies, increasing represented cardinality without increasing reality entities. |

Beatrice is **not** reality itself. Beatrice is the faithful tabular representation of the generated MediLacra reality. Inferno outputs are corrupted copies of Beatrice.

## Seeds

Defaults are intentionally separate:

- Reality seed: `42` — which universe exists.
- Inferno seed: `666` — which parts of that universe are cursed.

The same pair must produce the same reality and the same corruption selections.

## Streamlit UI

From the repository root:

```bash
streamlit run medi_lacra_app.py
```

Open the **Disco Inferno** page in the Streamlit page list.

The default UI settings reproduce the validated MVP run:

- 100 patients
- 2 encounters per patient
- 2 observations per encounter
- 2 transactions per encounter
- Reality seed `42`
- Inferno seed `666`
- Charon: `observations.encounter_id`
- Null: 10% of `observations.observation_text`
- Cerberus: 10% of `transactions`

The UI also exposes the cohort size, both seeds, Charon table/identifier target, Null table/field/intensity, Cerberus table/intensity, and lab-message export toggle.

## CLI

```bash
python experiments/disco_inferno/run_experiment.py
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
│   ├── ORM_O01_LABS_<run-id>.hl7
│   └── ORU_R01_LABS_<run-id>.hl7
├── source_reality_<run-id>.duckdb
├── metrics_<run-id>.csv
├── manifest_<run-id>.json
├── DISCO_INFERNO_REPORT_<run-id>.md
└── DISCO_INFERNO_<run-id>.zip
```

The source DuckDB contains the full untouched Beatrice tables: patients, encounters, observations, and transactions.

HL7 is projected from the same untouched generated cases using MediLacra's existing message builders. One bulk file is produced for each message family already emitted by the main pipeline. Narrative ORU and laboratory ORU remain separate products, matching the existing MediLacra pipeline convention.

The manifest is the corruption receipt: exact operator, target, intensity, selected positions/record identifiers, source counts, HL7 counts/files, and source DuckDB filename.

The Streamlit UI exposes both a single ZIP download for the complete experiment bundle and individual downloads for the report, manifest, metrics, DuckDB, and HL7 files.

## Tests

```bash
pytest -q tests/test_disco_inferno.py
```

The tests enforce the central invariant: **Beatrice is never mutated in place.** They also verify deterministic victim selection, exact corruption counts, a zero-delta control, timestamped CSV naming, and source-reality DuckDB materialization.

## Interpretation boundary

This MVP still does not calculate a universal entropy score. It measures direct representational damage first. Reconstruction, recoverability, compound corruption (reserved name: **Lucifer**), HL7/FHIR corruption, cognition tests, and entropy theory come later.

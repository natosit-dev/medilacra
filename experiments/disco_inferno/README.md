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

## Run the MVP

From the repository root in the normal Medilacra environment (for example `dev310`):

```bash
python experiments/disco_inferno/run_experiment.py
```

Default cohort:

- 100 patients
- 2 encounters per patient
- 2 observations per encounter
- 2 transactions per encounter

Expected source counts:

- 100 patients
- 200 encounters
- 400 observations
- 400 transactions

Useful overrides:

```bash
python experiments/disco_inferno/run_experiment.py \
  --reality-seed 42 \
  --inferno-seed 666 \
  --null-fraction 0.10 \
  --duplicate-fraction 0.10
```

## Output

Each run writes a timestamped directory under `experiments/disco_inferno/output/` containing:

```text
<run-id>/
├── beatrice/
│   ├── patients.csv
│   ├── encounters.csv
│   ├── observations.csv
│   └── transactions.csv
├── inferno/
│   ├── control/
│   ├── charon/
│   ├── null/
│   └── cerberus/
├── metrics.csv
├── manifest.json
└── DISCO_INFERNO_REPORT.md
```

The manifest is the corruption receipt: exact operator, target, intensity, selected positions/record identifiers, and output counts.

## Tests

```bash
pytest -q tests/test_disco_inferno.py
```

The MVP tests enforce the central invariant: **Beatrice is never mutated in place.** They also verify deterministic victim selection, exact corruption counts, and a zero-delta control.

## Interpretation boundary

This MVP does not calculate a universal entropy score. It measures direct representational damage first. Reconstruction, recoverability, compound corruption (reserved name: **Lucifer**), HL7/FHIR corruption, cognition tests, and entropy theory come later.

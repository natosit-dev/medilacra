# MediLacra

> **FHIR does not care whether reality entered the information system through a $14,000 medical appliance or a water-bottle cap and electrical tape. It cares what observation is being represented, how it was obtained, and whether the semantics survive.**

**Synthetic healthcare data generator, HL7 v2 sandbox, SDOH-enriched patient simulation lab, and Reality Interface experiment.**

| Field | Value |
|---|---|
| README version | v0.1 |
| Updated | 2026-08-25 |
| Branch | `feature/reality-interface` |
| Status | Active prototype / implementation branch |
| Change focus | Physical reality → WAV → measured periodicity → human validation → synthetic clinical context → HL7 v2 → FHIR |

MediLacra generates realistic-but-fake healthcare data for integration testing, analytics demos, and health data quality experiments. It creates synthetic patients, encounters, charges, reports, observations, vitals, labs, and HL7 v2 messages, then optionally persists the generated entities and raw messages into DuckDB for local inspection.

On the Reality Interface branch, MediLacra can also accept a user-controlled physical source artifact — initially an acoustic WAV captured through a computer-connected stethoscope — derive a measured periodicity, let a human validate what that pattern represents, bind the validated observation to synthetic clinical context, generate HL7 v2, and transform that message into FHIR JSON.

The core idea: use synthetic patients plus real-world public SDOH context and inspectable source evidence to create safer, richer test data without touching production PHI.

> **Important:** MediLacra's generated patient identities and clinical context are synthetic. Reality Interface may ingest user-controlled source artifacts such as local WAV recordings for experimentation. Never commit or load real PHI, client data, production extracts, credentials, or proprietary schemas into this repository.

---

## What MediLacra does

MediLacra can:

- Generate synthetic patients, encounters, observations, transactions, providers, and order identifiers.
- Build HL7 v2.5-style messages, including ADT, ORU, DFT, ORM, and lab ORU messages.
- Use ZIP-based reference data to assign plausible city/state geography.
- Pull or cache public SDOH indicators such as air quality, ACS poverty percentage, CDC PLACES obesity, and BLS unemployment.
- Use SDOH signals to skew synthetic vitals and lab values for more realistic population-level variation.
- Persist generated entities and raw HL7 messages into a local DuckDB database.
- Provide a Streamlit UI for running generation scenarios and reviewing data-source readiness.
- Support reusable scenario profiles stored as YAML.
- Accept a WAV source artifact through Reality Interface, visualize it, derive a repeating cycle/rate, capture human validation, attach the validated measurement to synthetic clinical context, and project the same fact through HL7 v2 and FHIR.

MediLacra is not a clinical prediction system. The vitals and lab generation logic is deliberately lightweight and demonstrative. It is intended to create useful test data, not medically authoritative patient simulations.

---

## Why this exists

Healthcare data testing is usually trapped between two bad options:

1. **Toy data** that is clean, tiny, and unrealistic.
2. **Real production data** that is sensitive, risky, and hard to share.

MediLacra tries to occupy the middle ground: synthetic data with enough clinical, operational, geographic, and socioeconomic texture to test pipelines, message parsing, semantic mapping, quality checks, and analytics workflows.

Reality Interface extends the same experiment one step upstream: instead of always generating the initial observation synthetically, a measured fact can enter from a physical source, be interpreted explicitly, and then move through the same representation machinery.

This makes it useful for:

- HL7 interface testing.
- Synthetic demo environments.
- Data-quality rule development.
- FHIR / HL7 mapping experiments.
- SDOH and patient-information-quality prototypes.
- Reality → representation experiments with inspectable provenance.
- Analytics and BI demos where real PHI would be inappropriate.
- Local DuckDB-based inspection before moving patterns into larger platforms.

---

## Current status

MediLacra is an active prototype / sandbox. It is useful now, but it is not packaged as a production application yet.

Expect:

- rough edges,
- evolving module names,
- local-file assumptions,
- synthetic/demo model logic,
- and intentionally ignored output artifacts.

That is by design. The repo is a working lab, not a polished vendor product.

The `feature/reality-interface` branch adds the first physical-source ingestion path. Its implementation plan is versioned under `docs/001_reality_interface_project_plan.md`.

---

## Architecture

```text
                         +-----------------------------+
                         | Reality Interface           |
                         | WAV → measured periodicity |
                         | → human validation          |
                         +-------------+---------------+
                                       |
                                       v
Streamlit UI / CLI              Validated Observation
        |                              |
        v                              |
Generation Pipeline <-----------------+
        |
        +--> Synthetic patients / encounters / transactions / observations
        +--> ZIP reference lookup
        +--> SDOH enrichment and YAML caches
        +--> Vitals and lab generation
        +--> HL7 segment/message builders
        |
        +--> HL7 files in ./output
        |
        +--> HL7 → FHIR transformation
        |
        +--> Optional DuckDB persistence
                 |
                 +--> patients
                 +--> encounters
                 +--> observations
                 +--> transactions
                 +--> orders
                 +--> messages
```

---

## Main components

### Streamlit app

`medi_lacra_app.py` is the primary UI.

It allows you to choose:

- number of patients to generate,
- deterministic seed behavior,
- per-encounter versus bulk HL7 file output,
- report CSV input location,
- output folder,
- AirNow radius,
- optional SDOH OBXs,
- optional lab ORM/ORU messages,
- DuckDB persistence,
- and scenario profiles.

Run it with:

```bash
streamlit run medi_lacra_app.py
```

Reality Interface is being added as a separate thin Streamlit page on `feature/reality-interface`. Signal processing, artifact persistence, semantic validation, clinical binding, HL7 generation, and FHIR transformation remain ordinary Python modules/functions rather than being implemented inside the page.

### Pipeline

`hl7_demo/pipeline.py` orchestrates the full generation flow:

1. load report templates,
2. generate synthetic entities,
3. build ADT / ORU / DFT messages,
4. optionally build lab ORM / lab ORU messages,
5. write HL7 files,
6. optionally persist entities and messages to DuckDB.

CLI example:

```bash
python -m hl7_demo.pipeline \
  --n 10 \
  --reports ./input/reports/*.csv \
  --out ./output \
  --persist duckdb \
  --add-places-obesity-obx \
  --add-unemployment-obx
```

### Reality Interface

The Reality Interface branch adds a second entrance into MediLacra's representation pipeline:

```text
physical reality
    ↓
computer-connected stethoscope
    ↓
WAV
    ↓
periodicity measurement
    ↓
human semantic validation
    ↓
synthetic Patient + Encounter + validated Observation
    ↓
HL7 v2 ORU^R01
    ↓
FHIR Bundle
```

The first prototype computer-connected stethoscope was assembled from reclaimed or already-available parts because building it was easier and cheaper than buying a dedicated digital device: tubing recovered from a construction dumpster, a random USB headset with microphone, the top of a water bottle, tubing salvaged from a broken washing machine, and electrical tape.

The physical build is deliberately simple. The useful boundary for MediLacra is the WAV: an inspectable source artifact from which a measured repeating cycle/rate can be derived before a human supplies clinical semantics.

See `docs/001_reality_interface_project_plan.md` for the implementation plan, decision log, artifact model, raw prompt history, and acceptance criteria.

### Synthetic entities

`hl7_demo/generators.py` creates synthetic patients, encounters, transactions, and observations.

The generated patient record includes:

- synthetic patient ID,
- name,
- date of birth,
- administrative sex,
- race,
- SSN,
- address,
- phone,
- ZIP,
- city,
- and state.

The encounter generator can use scenario profiles to derive PV1 fields such as patient class, assigned patient location, and hospital service.

### HL7 message builders

`hl7_demo/messages.py` and `hl7_demo/segments.py` build HL7 v2.5-style message structures.

Supported message families include:

- `ADT^A01` admission-style messages,
- `ORU^R01` observation result messages,
- `DFT^P03` financial transaction messages,
- `ORM^O01` synthetic lab orders,
- and lab-focused `ORU^R01` results.

The ADT builder can also append OBX segments for SDOH, vitals, gender identity, pronouns, and Sex Parameter for Clinical Use style values.

### FHIR transformation

`fhir/fhir_convert_backend.py` parses generated HL7 and projects supported messages into FHIR JSON Bundles. The Reality Interface path reuses this transformation rather than generating FHIR independently from UI state, so the HL7 → FHIR bridge remains visible and testable.

### SDOH enrichment

`hl7_demo/sdoh.py` provides ZIP/ZCTA-based enrichment helpers.

Current public-data integrations include:

- AirNow air quality observations,
- Census ACS poverty percentage by ZCTA,
- Census/FCC ZIP-to-county resolution,
- CDC PLACES obesity by ZCTA,
- and BLS LAUS unemployment by county.

Results are cached locally in YAML files under `data/` to reduce repeated API calls.

### Vitals model

`hl7_demo/vitals.py` trains or loads a small multi-output linear regression model.

Inputs:

- age,
- poverty index,
- air quality index.

Outputs:

- systolic blood pressure,
- heart rate,
- oxygen saturation,
- BMI.

These are emitted as LOINC-coded OBX segments.

### Lab generation

`hl7_demo/labs.py` defines a small panel of common LOINC-coded labs and shifts values using poverty and AQI signals.

Current example lab families include:

- metabolic / diabetes markers,
- lipids,
- liver function tests,
- and inflammation markers.

The model uses simple coefficients and random variation to produce plausible synthetic distributions. It is not clinically validated.

### DuckDB persistence

`storage_duckdb_entities.py` creates and writes to a local DuckDB schema.

Current tables include:

- `patients`,
- `encounters`,
- `observations`,
- `transactions`,
- `orders`,
- and `messages`.

The `messages` table stores raw HL7 payloads and written file paths, making it useful as a local bronze-style message log.

---

## Inputs you need

### 1. ZIP reference file

MediLacra expects a local ZIP reference file:

```text
./ref/address.csv
```

Required columns:

```text
zip, city, state
```

Example:

```csv
zip,city,state
01854,Lowell,MA
02139,Cambridge,MA
10001,New York,NY
```

### 2. Report CSV files

MediLacra expects one or more report CSVs under:

```text
./input/reports/*.csv
```

Required columns:

```text
report_uid
cpt_code
cpt_description
icd_code
icd_description
procedure_description
report_text
```

Example:

```csv
report_uid,cpt_code,cpt_description,icd_code,icd_description,procedure_description,report_text
RPT001,71045,Chest x-ray,R05.9,Cough,Chest radiograph,No acute cardiopulmonary abnormality.
```

### 3. Optional Reality Interface WAV

On `feature/reality-interface`, the Reality Interface accepts a local `.wav` source artifact. The initial experiment records approximately 10–300 Hz acoustic content from the prototype computer-connected stethoscope.

The WAV is source evidence. The generated patient and encounter remain synthetic. Source filename/location and a content hash are preserved in the run artifacts; the WAV itself is not embedded in the HL7 payload.

### 4. Optional environment variables

Create a local `.env` file if you want to use APIs that require credentials.

```bash
AIRNOW_API_KEY=your_airnow_key_here
```

Do not commit `.env` files.

---

## Quick start

### Windows / PowerShell

```powershell
git clone https://github.com/natosit-dev/medilacra.git
cd medilacra

py -m venv .venv
.\.venv\Scripts\Activate.ps1

pip install -U pip
pip install -r requirements.txt

streamlit run medi_lacra_app.py
```

### macOS / Linux

```bash
git clone https://github.com/natosit-dev/medilacra.git
cd medilacra

python3 -m venv .venv
source .venv/bin/activate

pip install -U pip
pip install -r requirements.txt

streamlit run medi_lacra_app.py
```

### Conda

```bash
conda create -y -n medilacra python=3.11
conda activate medilacra
pip install -r requirements.txt
streamlit run medi_lacra_app.py
```

---

## Example workflow

### Synthetic generation

1. Add `ref/address.csv`.
2. Add one or more report CSV files to `input/reports/`.
3. Start the Streamlit app.
4. Choose generation settings in the sidebar.
5. Generate messages.
6. Inspect HL7 files in `output/`.
7. If DuckDB persistence is enabled, inspect generated entities and messages in the local DuckDB database.

Example DuckDB inspection:

```python
import duckdb

con = duckdb.connect("medilacra.duckdb")
print(con.sql("select * from patients limit 5").df())
print(con.sql("select message_type, count(*) from messages group by 1").df())
```

### Reality Interface target flow

```text
Drop WAV
  ↓
visualize waveform / periodicity
  ↓
estimated_cycle_period_seconds
estimated_rate_per_minute
  ↓
human validates interpretation / adds notes
  ↓
generate synthetic patient + encounter
  ↓
create Observation from validated measured value
  ↓
generate ORU^R01 with source filename/location reference
  ↓
transform generated HL7 to FHIR JSON Bundle
```

---

## Output artifacts

Typical generated artifacts include:

```text
./output/*.hl7
medilacra.duckdb
logs/
data/*.yaml
vitals_model.pkl
```

Reality Interface runs are intended to persist the transformation chain together:

```text
artifacts/
  reality_interface/
    <run_id>/
      source.wav
      manifest.json
      validation.json
      message.hl7
      bundle.json
```

Most generated artifacts are intentionally ignored by git.

---

## Safety and privacy

MediLacra's generated clinical identities and contexts are synthetic. Reality Interface can additionally use user-controlled local source artifacts for experimentation.

Do not commit:

- PHI,
- production extracts,
- client files,
- real patient records,
- source recordings containing information you do not intend to publish,
- API keys,
- `.env` files,
- local DuckDB databases,
- generated HL7 output,
- or cached public-data artifacts that you do not want in source control.

The repository `.gitignore` is configured to exclude common generated outputs, local databases, logs, caches, data folders, environments, and scratch artifacts.

---

## Limitations

MediLacra is intentionally a sandbox.

Current limitations:

- synthetic clinical values are plausible but not clinically validated,
- Reality Interface periodicity analysis is experimental and intentionally small,
- SDOH effects are simplified and demonstrative,
- public API availability may vary,
- some generated values use local code systems rather than full standard vocabulary binding,
- Streamlit and CLI paths assume a local development environment,
- and the project is not yet packaged as an installable library.

Use it to test pipelines, mappings, validation, provenance, and demos — not to make clinical claims.

---

## Development notes

Common commands:

```bash
git status
git add -A
git commit -m "Describe the change"
git pull --rebase
git push
```

Run the app:

```bash
streamlit run medi_lacra_app.py
```

Run the pipeline directly:

```bash
python -m hl7_demo.pipeline --n 5 --reports ./input/reports/*.csv --out ./output --persist duckdb
```

Reality Interface implementation starts from `docs/001_reality_interface_project_plan.md`. The Streamlit page is intentionally last-mile UI; reusable mechanics belong in ordinary Python modules.

---

## Roadmap ideas

Potential next steps:

- Complete Reality Interface v0.1: WAV → measured periodicity → validation → ORU → FHIR.
- Package the project as an installable Python module.
- Add unit tests for segment builders and pipeline outputs.
- Add sample synthetic input files that are safe to commit.
- Add richer FHIR mapping examples.
- Add formal data-quality checks for generated HL7.
- Add deterministic scenario packs for demo reproducibility.
- Add a semantic conformance layer over generated messages.
- Add synthetic CCLF / claims-style datasets.
- Add SDOH validation profiles for PIQI / Project Gravity-style experiments.

---

## Name

**MediLacra** suggests medical simulacra: synthetic representations of healthcare data that are not real patients, but are structured enough to test how systems behave.

The fake patients are fake. The data problems are very real.

---

## Version and provenance

### Version log

| Version | Date | Status | Changes |
|---|---|---|---|
| v0.1 | 2026-08-25 | Current | First formally versioned README. Added Reality Interface framing at the top; documented physical-source WAV ingestion, explicit human semantic validation, synthetic clinical binding, HL7 → FHIR transformation, prototype stethoscope provenance, run artifact model, updated safety language, branch status, and implementation-plan link. |

### Raw prompt provenance

> FHIR does not care whether reality entered the information system through a $14,000 medical appliance or a water-bottle cap and electrical tape. It cares what observation is being represented, how it was obtained, and whether the semantics survive.
>
> Add this to the top of the README, version with all the trimmings

**Branch:** `feature/reality-interface`  
**Updated:** 2026-08-25  
**Primary design document:** `docs/001_reality_interface_project_plan.md`

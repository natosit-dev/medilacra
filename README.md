# MediLacra

> **FHIR does not care whether reality entered the information system through a $14,000 medical appliance or a water-bottle cap and electrical tape. It cares what observation is being represented, how it was obtained, and whether the semantics survive.**

**Synthetic healthcare data generator, HL7 v2 sandbox, SDOH-enriched patient simulation lab, and physical-reality interoperability experiment.**

| Field | Value |
|---|---|
| README version | v0.2 |
| Updated | 2026-08-27 |
| Branch | `feature/reality-interface` |
| Reality Interface status | End-to-end experiment demonstrated; complete enough for Connectathon/demo use |
| Core path | Physical signal → WAV → measured periodicity → human semantic validation → synthetic context → HL7 v2 → independent re-ingestion → FHIR → PIQI |

MediLacra generates realistic-but-fake healthcare data for integration testing, analytics demos, health data quality experiments, and representation/conformance work. It creates synthetic patients, encounters, charges, reports, observations, vitals, labs, and HL7 v2 messages, and can persist generated entities and raw messages into DuckDB for local inspection.

The Reality Interface adds another entrance into that machinery: a user-controlled physical source artifact can become a measured fact, receive explicit human semantics, bind to synthetic clinical context, and move through ordinary healthcare representations without hiding where it came from.

> **Important:** generated patient identities and encounter context are synthetic. Reality Interface may ingest user-controlled local source artifacts such as WAV recordings. Do not commit PHI, client data, production extracts, credentials, proprietary schemas, or source recordings you do not intend to publish.

---

## What MediLacra does

MediLacra can:

- Generate synthetic patients, encounters, observations, transactions, providers, and order identifiers.
- Build HL7 v2.5-style ADT, ORU, DFT, ORM, and lab-result messages.
- Enrich synthetic context with public SDOH/reference data.
- Persist entities and raw messages into local DuckDB tables.
- Transform supported HL7 v2 messages into FHIR JSON Bundles.
- Score converted output through PIQI surfaces.
- Provide Streamlit control surfaces for generation, inspection, conversion, and Reality Interface work.
- Accept a WAV through Reality Interface, visualize it, derive periodicity, capture human interpretation/notes, bind the validated value to synthetic context, generate a downloadable ORU^R01, and transform that artifact into FHIR.

MediLacra is a working lab, not a polished vendor product. Its synthetic clinical models and Reality Interface signal analysis are deliberately small and demonstrative.

---

## Reality Interface

The Reality Interface is the first MediLacra path where the originating fact is measured from physical reality rather than generated synthetically.

```text
body-origin acoustic/mechanical activity
        ↓
computer-connected stethoscope
        ↓
WAV source artifact
        ↓
SciPy / NumPy periodicity measurement
        ↓
human semantic validation
        ↓
validated Heart rate Observation
        +
synthetic Patient + Encounter
        ↓
HL7 v2 ORU^R01
        ↓
downloaded .hl7 artifact
        ↓
independent HL7 → FHIR converter
        ↓
FHIR Bundle
        ↓
PIQI scorecard
```

### The hardware

The first computer-connected stethoscope was assembled because building it was faster and cheaper than buying a dedicated digital device. It uses:

- tubing recovered from a construction dumpster;
- a random USB headset with microphone as the computer audio interface;
- the top of a water bottle as the chestpiece/acoustic chamber;
- tubing salvaged from a broken washing machine;
- electrical tape for mechanical coupling and sealing.

Mechanically, it is a stethoscope whose endpoint is a USB microphone instead of a pair of earpieces.

```text
chest
  ↓
water-bottle chestpiece
  ↓
reclaimed tubing
  ↓
sealed coupling
  ↓
USB headset microphone
  ↓
computer
  ↓
WAV
```

The software boundary begins at the WAV. The original source artifact is preserved unchanged; normalization/downsampling happens only in the analysis copy.

### Signal analysis

The v0.1 measurement path intentionally stays small:

```text
scipy.io.wavfile.read
        ↓
NumPy mono float signal
        ↓
DC removal / analysis normalization
        ↓
scipy.signal.resample_poly (when needed)
        ↓
scipy.signal.hilbert
        ↓
smoothed amplitude envelope
        ↓
FFT autocorrelation
        ↓
dominant plausible repeating period
        ↓
estimated_cycle_period_seconds
estimated_rate_per_minute
```

The machine output remains a generic repeating rate until a human binds it to a healthcare concept.

### Human semantic binding

The Streamlit page exposes the distinction directly:

```text
machine: estimated repeating rate
        ↓
human: “Heart rate” + accept/override + optional note
        ↓
LOINC 8867-4 / Heart rate / /min
```

The generated Patient and Encounter are synthetic. The Observation value comes from the validated external measurement rather than from MediLacra's synthetic vital generator.

### HL7 v2 output

Reality Interface generates an `ORU^R01` containing:

```text
MSH  message metadata
PID  synthetic patient
PV1  synthetic encounter
OBR  observation context
OBX  NM  8867-4^Heart rate^LN  <validated value> /min
OBX  ST  source WAV filename + project-relative location
NTE  optional human note
```

The page displays the generated message and provides a **Download HL7 v2 ORU^R01** button. The WAV bytes are not embedded in the message.

### FHIR transformation

FHIR is produced from the generated HL7 artifact, not independently regenerated from Streamlit state. This makes the representation bridge itself observable and testable.

The expected FHIR-side chain contains a synthetic Patient, synthetic Encounter, the validated Heart rate Observation, and the source-reference observation supported by the current converter.

---

## Demonstrated result

The experiment has now crossed the application boundary, not just the in-page rendering boundary.

A fresh WAV was processed through Reality Interface and produced a measured rate of approximately:

```text
86.957 /min
```

The human selected **Heart rate**, accepted the measured value, and added the note:

```text
Excited to share this, HR reflects that
```

The resulting ORU contained the heart-rate value, source WAV reference, and NTE note. The `.hl7` file was downloaded from Reality Interface and uploaded into the separate **HL7 v2 → FHIR Converter + PIQI Scorecard** surface.

That independent consumer:

- recognized the artifact as `ORU^R01`;
- generated a FHIR Bundle containing the expected resource family;
- ran PIQI against the converted result;
- produced a PIQI score of **75** for that observed run;
- reported **6 / 8** applicable checks passed;
- reported **0 critical failures**.

The PIQI 75 is evidence from one demonstrated run, not a general quality claim about every generated message. It also gives the next concrete debugging target if PIQI conformance becomes important: identify the two non-passing applicable assertions rather than redesigning the Reality Interface.

### What survived

Across the demonstrated chain, the following remained traceable:

- measured numeric value;
- `/min` unit;
- semantic identity as Heart rate / LOINC `8867-4`;
- synthetic patient linkage;
- synthetic encounter linkage;
- source WAV filename/location reference;
- human note;
- message identity as `ORU^R01`;
- downstream FHIR representation.

That answers the experiment's primary question.

---

## Thin-client architecture

The Reality Interface Streamlit page owns interaction and display only. Reusable mechanics live outside Streamlit:

```text
reality_interface/
  __init__.py
  audio.py
  periodicity.py
  artifacts.py
  validation.py
  binding.py
  hl7.py
  pipeline.py

pages/
  8_Reality_Interface.py

tests/
  test_reality_interface_periodicity.py
  test_reality_interface_hl7_fhir.py
```

Visualization currently uses Streamlit-native charts. Matplotlib was intentionally not added because the native waveform and energy-envelope views are sufficient for the human-validation step.

---

## Run artifacts

Each Reality Interface run persists its transformation chain together:

```text
artifacts/
  reality_interface/
    <run_id>/
      <source_filename>.wav
      manifest.json
      validation.json
      message.hl7
      bundle.json
```

`pathlib.Path` is used for cross-platform artifact handling. Source files are hashed and copied unchanged. The artifact directory is gitignored.

---

## Main synthetic-data architecture

Outside Reality Interface, MediLacra continues to use its existing synthetic generation pipeline:

```text
Streamlit UI / CLI
        ↓
Generation Pipeline
        ↓
Synthetic Patient / Encounter / Observation / Transaction
        ↓
reference + SDOH enrichment
        ↓
HL7 segment/message builders
        ↓
HL7 files / optional DuckDB
        ↓
FHIR / validation / analysis surfaces
```

Key implementation areas include:

- `hl7_demo/generators.py` — synthetic entities;
- `hl7_demo/messages.py` and `hl7_demo/segments.py` — HL7 v2 projection;
- `fhir/fhir_convert_backend.py` — supported HL7 → FHIR conversion;
- `storage_duckdb_entities.py` — local entity/message persistence;
- `hl7_demo/sdoh.py`, `vitals.py`, and `labs.py` — demonstrative enrichments/models.

---

## Quick start

### Windows / PowerShell

```powershell
git clone https://github.com/natosit-dev/medilacra.git
cd medilacra
git checkout feature/reality-interface

py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -U pip
pip install -r requirements.txt
pip install -r requirements-dev.txt

pytest -q tests/test_reality_interface_periodicity.py tests/test_reality_interface_hl7_fhir.py
streamlit run medi_lacra_app.py
```

### macOS / Linux

```bash
git clone https://github.com/natosit-dev/medilacra.git
cd medilacra
git checkout feature/reality-interface

python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
pip install -r requirements-dev.txt

pytest -q tests/test_reality_interface_periodicity.py tests/test_reality_interface_hl7_fhir.py
streamlit run medi_lacra_app.py
```

For the broader synthetic generator, provide the local reference/input files expected by the existing pipeline (for example `ref/address.csv` and report CSVs) and use the normal generation pages/CLI.

---

## Safety and privacy

Do not commit:

- PHI;
- production extracts or client files;
- real patient records;
- source recordings containing information you do not intend to publish;
- credentials or `.env` files;
- local DuckDB databases;
- generated artifacts that should remain local.

Reality Interface deliberately preserves the distinction between the real physical source artifact and the synthetic clinical identity/context attached for interoperability testing.

---

## Known rough edges / deferred work

The project stops here unless a concrete use case forces another change.

Known rough edges include:

- periodicity analysis is intentionally primitive and optimized for the demonstration rather than general physiological signal processing;
- source WAV reference uses a simple `ST` representation in the current ORU path;
- the existing FHIR converter exposed an MSH-field indexing mismatch, handled by a localized Reality Interface compatibility step;
- one observed PIQI run scored 75 (6/8 applicable checks, 0 critical failures), leaving two non-passing assertions to inspect if PIQI optimization becomes useful;
- Streamlit visualization remains intentionally simple.

None of these prevented the experiment from answering its question.

---

## Documentation

- `docs/001_reality_interface_project_plan.md` — original plan, decisions, raw prompt history, and completion status.
- `docs/002_reality_interface_build_log.md` — implementation choices, baseline measurements, build findings, and demonstrated end-to-end run.
- `docs/003_reality_interface_experiment_result.md` — concise final result/evidence record.

---

## Stop condition

The Reality Interface experiment is complete when the same fact can be traced from physical reality, through measurement and human interpretation, into HL7 v2, through an independent consumer, and into FHIR without losing what it means.

**That happened.**

Future work should be driven by a concrete interoperability, validation, or Connectathon need rather than by polishing the demonstration for its own sake.

---

## Name

**MediLacra** suggests medical simulacra: synthetic representations of healthcare data that are not real patients, but are structured enough to test how systems behave.

The fake patients are fake. The data problems are very real.

---

## Version and provenance

### Version log

| Version | Date | Status | Changes |
|---|---|---|---|
| v0.1 | 2026-08-25 | Superseded | First formally versioned README. Added Reality Interface framing, physical-source WAV ingestion, human semantic validation, synthetic clinical binding, HL7 → FHIR transformation, prototype stethoscope provenance, run artifact model, safety language, and implementation-plan link. |
| v0.2 | 2026-08-27 | Current | Closed the Reality Interface documentation pass. Promoted the feature from planned/active experiment to demonstrated capability; documented the fresh 86.957/min run, downloadable ORU, independent re-ingestion, FHIR conversion, PIQI 75 result (6/8 applicable, 0 critical), thin-client/module implementation, known rough edges, documentation index, and explicit stop condition. |

### Raw prompt provenance

> FHIR does not care whether reality entered the information system through a $14,000 medical appliance or a water-bottle cap and electrical tape. It cares what observation is being represented, how it was obtained, and whether the semantics survive.
>
> Add this to the top of the README, version with all the trimmings

> Looking good! Used a fresh WAV

> Should we do a final documentation pass? This project is done ish

> Ok, go make the final updates

**Branch:** `feature/reality-interface`  
**Updated:** 2026-08-27  
**Primary result record:** `docs/003_reality_interface_experiment_result.md`

# MediLacra Reality Interface — Build Log

**Build Log v0.1 — Backend + thin Streamlit client**

| Field | Value |
|---|---|
| Date | 2026-08-26 |
| Branch | `feature/reality-interface` |
| Status | Initial implementation committed; local real-WAV analysis validated; repository tests added |
| UI rule | Streamlit remains a thin client. Signal processing, artifact handling, validation, clinical binding, HL7 projection, and FHIR transformation are ordinary Python modules. |

---

## Raw prompt additions

> 1 + 2- let's use scipy + numPy  
> 2- hilbert looks good  
> 3 + 10- pytest looks good  
> 4- I've used pathlib before, would that make sense here?  
> 11- Fine, as long as we actually need matplotlib. Don't want to make this fancier than needed  
>  
> What else do you need from me before going to build this?

> Here's the file

The supplied local WAV is used for development validation only and is **not committed to the repository**.

---

## Locked implementation choices

| Concern | Choice | Why |
|---|---|---|
| WAV loading | `scipy.io.wavfile.read` | SciPy is already required for signal analysis; no extra audio framework needed. |
| Working signal | NumPy arrays | Direct, inspectable numeric representation. |
| Resampling | `scipy.signal.resample_poly` | Anti-aliased reduction from normal audio sample rates to a cheaper analysis rate. |
| Envelope | `scipy.signal.hilbert` | Converts the oscillating waveform into an amplitude envelope without inventing a larger DSP framework. |
| Periodicity | `scipy.signal.correlate(..., method="fft")` | Finds repeating structure across the full acoustic cycle rather than blindly counting transients. |
| Tests | `pytest` | Matches the repository's lightweight function-test style and gives `tmp_path` / `approx`. |
| Artifact paths | `pathlib.Path` | Clean cross-platform handling for run directories, relative source references, copying, hashing, and tests. |
| Validation state | Pydantic | Already a MediLacra dependency; convenient validation and JSON serialization at the semantic boundary. |
| Visualization | Streamlit native charts first | No Matplotlib dependency unless native charts prove insufficient. |
| HL7 | Existing MediLacra segment machinery + a small Reality Interface ORU projection | Reuse Patient/PV1/MSH rendering while adding the numeric measurement/source-reference OBXs needed by the experiment. |
| FHIR | Existing MediLacra ORU converter | Preserve the intended HL7 → FHIR transformation path rather than regenerating FHIR from UI state. |

New runtime dependencies: `numpy`, `scipy`.

New development dependency: `pytest` in `requirements-dev.txt`.

Matplotlib was intentionally **not** added.

---

## Real WAV baseline

Development file supplied outside the repository:

```text
Nat_heart_8.25.wav
```

Observed file properties:

```text
source sample rate: 44,100 Hz
channels:           1
duration:           17.836 s
```

The backend downsamples the analysis copy to 2,000 Hz. The original WAV is never rewritten.

Initial Reality Interface analysis using:

```text
Hilbert amplitude envelope
50 ms smoothing window
FFT autocorrelation
search window: 40–140 repeating cycles/minute
```

produced:

```text
estimated_cycle_period_seconds = 0.657
estimated_rate_per_minute      = 91.3
periodicity_score              ≈ 0.345
```

This result is intentionally still a **machine periodicity measurement**. The later human-validation step is what binds that repeating rate to the semantic concept `heart_rate`.

The synthetic pytest fixture contains a two-transient repeating acoustic pattern every 0.80 seconds. The same algorithm recovers approximately:

```text
estimated_cycle_period_seconds = 0.800
estimated_rate_per_minute      = 75.0
```

---

## Implemented module order

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

### `audio.py`

```text
WAV
 ↓ scipy.io.wavfile.read
mono float copy
 ↓
DC removal + analysis normalization
 ↓
scipy.signal.resample_poly when needed
 ↓
AudioSignal
```

Default analysis sample rate: 2 kHz. This comfortably preserves the initial 10–300 Hz acquisition context while avoiding 44.1 kHz autocorrelation work.

### `periodicity.py`

```text
AudioSignal
 ↓
Hilbert transform
 ↓
amplitude envelope
 ↓
50 ms moving average
 ↓
autocorrelation
 ↓
strongest plausible lag
 ↓
cycle period
 ↓
60 / period
 ↓
rate per minute
```

The module can also be invoked independently:

```bash
python -m reality_interface.periodicity path/to/recording.wav
```

### `artifacts.py`

Uses `pathlib`, `hashlib`, `shutil`, and `json`.

Each run creates:

```text
artifacts/reality_interface/<run_id>/
  <original_filename>.wav
  manifest.json
  validation.json
  message.hl7
  bundle.json
```

`artifacts/reality_interface/` is ignored by Git so real local source recordings do not get committed accidentally.

### `validation.py`

Preserves the distinction between:

```text
machine:
  repeating rate = X /min

human:
  interpretation = heart_rate
  accepted / overridden
  notes
```

### `binding.py`

Reuses existing:

```python
gen_patient()
gen_encounter(patient_id)
```

The synthetic encounter window is aligned around the observed measurement time so the external measurement does not land outside its generated encounter context.

For v0.1, accepted `heart_rate` is bound to:

```text
LOINC 8867-4
Heart rate
/min
```

### `hl7.py`

Builds a small ORU^R01 using existing MediLacra MSH/PID/PV1 segment builders, then adds:

```text
OBR  8867-4^Heart rate^LN
OBX  NM heart-rate value
OBX  ST source WAV filename + project-relative location
NTE  optional human note
```

The WAV bytes are not embedded in HL7.

### `pipeline.py`

Provides two stages for the thin client:

```text
analyze_uploaded_bytes(...)
        ↓
AnalysisRun
        ↓ human interaction
finalize_run(...)
        ↓
synthetic context → ORU → FHIR Bundle
```

This keeps Streamlit state out of the underlying mechanics.

---

## Existing FHIR converter compatibility finding

While wiring the round trip, the existing FHIR converter exposed an MSH indexing mismatch: the generic `split("|")` parser omits MSH-1 (the field separator) from its indexed field array, while downstream MSH accessors use normal HL7 field numbers.

Reality Interface currently handles this with a localized compatibility step in `convert_reality_oru_to_fhir()`:

```text
parse existing ORU
 ↓
restore MSH-1 slot
 ↓
call existing convert_oru(...)
```

This keeps the Reality Interface implementation moving without silently building a parallel FHIR converter. The underlying generic MSH parser can be corrected separately once regression coverage is broad enough.

---

## Tests added

### Periodicity

`tests/test_reality_interface_periodicity.py`

- Generates a known repeating two-transient waveform.
- Expected cycle: ~0.80 s.
- Expected rate: ~75/min.
- Verifies 44.1 kHz WAVs are downsampled for analysis.
- Verifies the source WAV bytes are unchanged by loading/analysis.

### HL7 → FHIR

`tests/test_reality_interface_hl7_fhir.py`

- Creates deterministic synthetic Patient/Encounter objects.
- Creates a validated 75/min heart-rate measurement.
- Generates Reality Interface ORU^R01.
- Checks the numeric OBX and source filename reference.
- Sends the ORU through the existing FHIR conversion code via the MSH compatibility adapter.
- Asserts the FHIR heart-rate Observation still contains `75 /min`.
- Asserts the source-recording Observation still references the WAV filename.

---

## Thin Streamlit page

`pages/8_Reality_Interface.py` currently does only interface work:

```text
Drop WAV
 ↓
call backend analysis
 ↓
show source metadata + waveform + envelope + measured period/rate
 ↓
human chooses interpretation / accepts / overrides / notes
 ↓
call backend finalize
 ↓
show synthetic context
 ↓
show HL7
 ↓
show FHIR
```

Waveform and envelope use Streamlit-native `st.line_chart()` with display thinning. No Matplotlib dependency has been introduced.

---

## Current stop condition

The implemented path is structurally complete when run in the MediLacra environment:

```text
WAV
 ↓
0.657 s / 91.3 per minute on the supplied development recording
 ↓
human validates as heart rate
 ↓
synthetic Patient + Encounter
 ↓
ORU^R01
 ↓
FHIR Bundle
```

The next mechanical step is running the repository pytest suite and the Streamlit page on the development machine, then fixing whatever the real environment exposes rather than adding more architecture in advance.

---

## Version log

| Version | Date | Changes |
|---|---|---|
| v0.1 | 2026-08-26 | Locked SciPy/NumPy/Hilbert/pytest/pathlib choices; implemented modular backend, run artifacts, human validation, synthetic binding, ORU projection, FHIR compatibility adapter, two regression-test files, native Streamlit page, runtime/dev dependencies, and real-WAV baseline. |

# MediLacra: Soul Window

**Technical subtitle:** Visual Acuity Reality Interface  
**Branch:** `feature/soul-window`  
**Version:** 0.1  
**Status:** Planned / initial experiment definition  

## Raw Prompt History

> "One idea I had was using this for a crude eye test"

> "We could record audio and have them say the characters out loud"

> "Oh shit I could run the app ON THE PHONE. No tumbling E, we keep it stupid simple. Show me a project plan for a Medilacra feature"

> "SOUL WINDOW"

## 1. Experiment Question

Can an obsolete commodity phone mounted in a simple VR shell act as both the visual stimulus source and the response-capture instrument for a crude, inspectable visual-acuity experiment, then carry the resulting measurement through MediLacra into HL7 v2 and FHIR without hiding how the result was produced?

The v0.1 experiment is deliberately narrow:

> **Can a Pixel 3 display progressively smaller random characters, record the participant saying each character aloud, score those responses, and produce a traceable minimum reliable character size?**

The first result is a measured threshold in rendered character size. It is **not** yet a calibrated Snellen or logMAR result.

## 2. Physical Interface

Initial hardware:

- Google Pixel 3
- Utopia 360 VR shell
- phone display
- phone microphone
- human eye / visual perception
- spoken response

The phone is both the stimulus generator and the response recorder.

```text
Pixel display
    ↓
random character
    ↓
human visual perception
    ↓
spoken character
    ↓
Pixel microphone
    ↓
recorded audio
    ↓
response scoring
    ↓
measured visual threshold
```

The VR shell provides useful physical constraints without adding much technology:

- fixed phone position
- relatively fixed viewing geometry
- reduced ambient visual distraction
- repeatable physical setup

## 3. Core Design Rule

Keep the measurement chain explicit.

These are different facts and must remain different:

```text
character displayed
≠
character spoken
≠
character inferred by software
≠
final human-validated response
```

The raw evidence should survive every transformation.

Automatic speech recognition may assist scoring, but the project must preserve the audio so a machine transcription error cannot silently become a visual-acuity error.

## 4. v0.1 Test Flow

### Setup

The operator selects:

- eye tested: left / right / both
- optional participant note
- start test

For v0.1, the unused eye may be physically obscured rather than introducing stereoscopic rendering logic.

### Trial

For each trial:

1. Select one random uppercase character.
2. Render it centered on a simple high-contrast background.
3. Record the exact rendered character size in pixels.
4. Record stimulus presentation timestamp.
5. Listen for and record the spoken response.
6. Store the raw audio artifact.
7. Attempt simple transcription if available.
8. Score expected versus recognized response.
9. Allow later human correction without deleting the original machine result.

### Initial character set

Keep the set small and visually distinct enough for the first experiment. Exact membership can change during implementation without changing the architecture.

Example starting set:

```text
A F H K M N R S X Z
```

No tumbling E, no chart layout, no complex optotype system in v0.1.

## 5. Size Sequence

Start with a fixed descending set of rendered character heights rather than an adaptive psychophysics algorithm.

Example:

```text
96 px
80 px
64 px
52 px
44 px
36 px
28 px
22 px
```

Run a small number of trials at each level, initially 2–3.

A level may be considered reliable if a simple configurable threshold is met, initially:

```text
2 of 3 correct
```

The primary machine result is:

```text
minimum_reliable_character_height_px
```

Do not convert this to `20/20`, Snellen fraction, or logMAR until the phone/headset optical geometry has been separately characterized.

## 6. Trial Record

Every trial should be independently auditable.

Example internal structure:

```json
{
  "trial": 4,
  "eye": "right",
  "character": "H",
  "character_size_px": 42,
  "stimulus_timestamp": "...",
  "audio_start_timestamp": "...",
  "response_audio": "audio/trial_004.wav",
  "recognized_response": "H",
  "human_validated_response": "H",
  "correct_machine": true,
  "correct_validated": true,
  "response_time_seconds": 0.91
}
```

The original values should never be overwritten when a human corrects interpretation. Store the correction as another layer of provenance.

## 7. Measurement Output

Initial result structure:

```json
{
  "eye": "right",
  "minimum_reliable_character_height_px": 36,
  "correct_trials": 18,
  "total_trials": 24,
  "accuracy": 0.75,
  "median_response_seconds": 0.91
}
```

The result should be described mechanically first:

> Minimum reliable rendered character height under this apparatus and test configuration.

Clinical interpretation is a later semantic step.

## 8. Human Validation

Follow the existing Reality Interface pattern.

After machine scoring, present a small validation surface:

```text
What does this experiment represent?

Visual acuity threshold

[ ] Accept measured threshold

Optional override:
____________

Notes:
____________
```

The human validation step binds the mechanical measurement to its intended meaning.

## 9. MediLacra Integration

Reuse the existing MediLacra machinery wherever possible.

Existing capabilities to reuse:

- synthetic Patient generation
- synthetic Encounter generation
- Observation representation
- HL7 v2 ORU generation
- HL7 → FHIR conversion
- artifact/run conventions from Reality Interface
- provenance distinction between real measurement and synthetic context

The physical measurement is real experiment evidence. Patient and encounter context remain synthetic demo context.

Internal metadata should preserve that distinction, for example:

```text
measurement_source = external
subject_binding = synthetic_demo
```

## 10. Proposed Module Layout

Keep Streamlit thin and the mechanics independently callable.

```text
soul_window/
├── __init__.py
├── stimulus.py
├── audio.py
├── scoring.py
├── artifacts.py
├── validation.py
├── binding.py
└── pipeline.py

pages/
└── 9_Soul_Window.py

tests/
├── test_soul_window_scoring.py
├── test_soul_window_threshold.py
└── test_soul_window_hl7_fhir.py
```

### Responsibilities

**`stimulus.py`**
- choose characters
- manage size sequence
- trial timing metadata

**`audio.py`**
- capture or ingest response audio
- preserve WAV artifacts
- expose simple transcription helper if used

**`scoring.py`**
- compare expected and recognized/validated responses
- calculate level pass/fail
- calculate minimum reliable character height
- calculate response latency summaries

**`artifacts.py`**
- create run directory
- write manifests and trial records
- maintain file hashes where appropriate

**`validation.py`**
- human validation models
- preserve machine result and human correction separately

**`binding.py`**
- bind validated measurement to synthetic Patient / Encounter / Observation context

**`pipeline.py`**
- orchestration only

**Streamlit page**
- mobile-friendly thin client
- run experiment
- show progress
- review results
- validate result
- generate/download HL7 and show FHIR output

## 11. Mobile UI Requirement

The experiment should run directly on the Pixel 3 through the MediLacra web UI.

Once the test starts, the participant should not need to touch the phone until the run is complete.

Minimum active-test view:

```text

             H

         Listening...

          Trial 4 / 24
```

Large high-contrast rendering is more important than visual polish.

## 12. Artifact Structure

Reuse the Reality Interface run-artifact pattern.

```text
artifacts/
  soul_window/
    <run_id>/
      manifest.json
      trials.json
      validation.json
      audio/
        trial_001.wav
        trial_002.wav
        ...
      message.hl7
      bundle.json
```

Source audio should remain outside git by default.

## 13. HL7 / FHIR Boundary

The validated measurement should enter the existing MediLacra interoperability path rather than generating FHIR independently from UI state.

```text
validated visual threshold
        ↓
MediLacra Observation
        ↓
HL7 v2 ORU^R01
        ↓
downloaded HL7 artifact
        ↓
existing HL7 → FHIR converter
        ↓
FHIR Bundle
```

The final implementation should preserve at minimum:

- eye tested
- measured threshold
- unit / representation of threshold (`px` for v0.1)
- method / apparatus context where practical
- measurement timestamp
- provenance linking back to the run artifacts

## 14. Work Packets

### WP1 — Mobile Stimulus

Build the simplest possible phone-friendly stimulus runner.

Acceptance:
- runs on Pixel 3 browser
- displays one centered random character
- steps through configured sizes
- records exact character and size for every trial

### WP2 — Audio Evidence

Capture spoken response evidence.

Acceptance:
- each trial has a recoverable audio artifact or an accurately timestamped segment of a continuous recording
- trial record links to the evidence

### WP3 — Scoring

Implement expected-versus-response scoring and threshold calculation.

Acceptance:
- deterministic unit tests cover correct, incorrect, and corrected responses
- smallest reliable passing size is reproducibly calculated

### WP4 — Review and Human Validation

Provide a compact post-test review.

Acceptance:
- machine interpretation remains visible
- human can correct a response
- original machine result is preserved
- threshold recalculates from validated responses

### WP5 — MediLacra Binding

Create synthetic clinical context around the externally measured result.

Acceptance:
- synthetic Patient and Encounter are generated
- validated measurement becomes an Observation
- physical measurement provenance is not represented as synthetic

### WP6 — HL7 / FHIR

Run the result through the existing interoperability path.

Acceptance:
- downloadable HL7 ORU is generated
- the downloaded HL7 can be independently consumed by the existing converter
- resulting FHIR preserves the intended measurement meaning

### WP7 — Physical Experiment

Run a fresh test with the Pixel 3 mounted in the Utopia 360 headset.

Acceptance:
- complete physical run succeeds without touching the phone during active testing
- trial evidence is preserved
- threshold is produced
- result survives HL7 → FHIR conversion

## 15. Testing

Minimum automated tests:

- random stimulus always comes from configured character set
- size sequence is deterministic when configured
- response scoring distinguishes expected, machine, and validated values
- human corrections do not destroy original machine values
- pass/fail calculation works at boundary conditions
- threshold selection works with mixed passing/failing levels
- artifact manifest references existing trial evidence
- Observation binding preserves eye and measured threshold
- HL7 → FHIR round trip preserves the intended result

Physical/browser behavior should be verified manually on the Pixel 3.

## 16. Explicit Non-Goals for v0.1

Do not build these unless the simple experiment proves they are necessary:

- Snellen calibration
- logMAR calibration
- optical lens calibration
- tumbling E
- full eye charts
- eye tracking
- pupil tracking
- saccade analysis
- stereoscopic left/right stimulus rendering
- automated diagnosis
- complex speech recognition
- ML vision models
- polished mobile application packaging

## 17. Stop Condition

The experiment is complete when:

1. the Pixel displays progressively smaller randomized characters inside the headset;
2. spoken responses are preserved as evidence;
3. the system produces a reproducible minimum reliable rendered character size;
4. a human can inspect and validate the result;
5. the measurement is bound to synthetic MediLacra context;
6. an HL7 v2 artifact is produced and downloaded;
7. that artifact is consumed independently and transformed into FHIR without losing what was measured.

At that point, stop. Optical calibration and richer ophthalmic measurements become separate experiments.

## 18. Decision Log

### 2026-08-28 — Name

**Decision:** Call the feature **Soul Window** with technical subtitle **Visual Acuity Reality Interface**.

### 2026-08-28 — Run on the phone

**Decision:** Run the experiment directly on the Pixel rather than using the phone only as a remote display/sensor.

**Reason:** The phone can generate the stimulus, capture the response, timestamp both, and preserve the evidence in one physical apparatus.

### 2026-08-28 — Keep the optotype primitive

**Decision:** Use ordinary single uppercase characters. Do not use tumbling E for v0.1.

**Reason:** The experiment is about the measurement and provenance chain, not building a standards-complete eye exam.

### 2026-08-28 — Preserve raw speech evidence

**Decision:** Keep raw audio and distinguish spoken evidence, machine transcription, and human validation.

**Reason:** A speech-recognition failure must not silently become a vision-measurement failure.

### 2026-08-28 — Pixels first

**Decision:** Report the initial threshold in rendered pixels.

**Reason:** Conventional visual-acuity units require optical/viewing-angle calibration that is outside the first experiment.

## 19. Version Log

### v0.1 — 2026-08-28

Initial project plan. Defines the Pixel 3 + Utopia 360 apparatus, simple spoken-character test, trial provenance model, threshold calculation, MediLacra binding, HL7/FHIR boundary, work packets, and stop condition.

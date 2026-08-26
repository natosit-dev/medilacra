# MediLacra Reality Interface

**Project Plan v0.2 — WAV → measured periodicity → human validation → synthetic clinical context → HL7 v2 → FHIR**

| Field | Value |
|---|---|
| Document version | v0.2 |
| Date | 2026-08-25 |
| Status | Implementation-ready; feature branch initialized |
| Target branch | `feature/reality-interface` |
| UI rule | Streamlit is a thin client; processing and transformation logic live in reusable modules. |
| Primary demo | Load a WAV recorded through the computer-connected stethoscope, derive a repeating rate, validate the interpretation, attach it to a synthetic patient/encounter, generate HL7 v2 ORU^R01, then transform the message to a FHIR JSON Bundle. |
| Source context | Current conversation plus the existing MediLacra functionality overview. Existing generators, dataclasses, HL7 builders, schema knowledge, and transformation machinery are to be reused rather than duplicated. |

---

# Raw Prompt History (verbatim)

Prompts below are preserved in chronological order. Image-only turns are represented as `[Image uploaded]` or `[Images uploaded]`.

1. We were talking about making a contact mic attached to a computer last week. Can you find that?
2. Yeah we said piezo. I was going shop to shop, eventually concluded I needed to go to guitar center
3. That's fine, the idea is simple- hook a contact mic to the computer as an additional sensor to record heartbeat or other audio signals
4. Yeah, obviously it's not medical grade, but it's going to put on a show at the connection 😁
5. *connectathon
6. What's the most basic, cheapest way to do this?
7. `[Image uploaded]`  
   Hmmm .. could I use this? Tear it apart, the ear speakers should have what I need
8. Heh, it works as a microphone in audacity but it only picks up voice. Too much noise filtering
9. `[Images uploaded]`  
   Much better, but not quite the yet
10. `[Images uploaded]`  
    This is with the updated configs and normalization
11. Huh, I may have a stethoscope around here...
12. Explain what stethoscope is in Nat terms
13. `[Images uploaded]`  
    I'm sure I've got one somewhere, but it may take a while to find 😅 can I just build a primitive one?
14. `[Image uploaded]`  
    Damn I thought the plastic lemon was hollow but it's got foam in it. I'm assuming I can just use the top of a small bottle to start until I find something cool to replace it with?
15. `[Image uploaded]`  
    Lol I found this in a dumpster, sadly stethoscope is not included 😭
16. `[Image uploaded]`  
    How should I attach the tube to the mic? 
17. What do you mean by cut the tube and square
18. `[Image uploaded]`  
    The hole is on the side
19. `[Image uploaded]`  
    They are the same size
20. `[Images uploaded]`  
    Bit of progress
21. `[Image uploaded]`  
    🤡😹
22. I'm thinking glue, tape or liquid latex might be good for the coupling. It's too small for the balloon
23. Oh I'm not even going straight to skin yet, I was over my shirt 
24. `[Images uploaded]`  
    V0.2
25. Oh, this was direct skin. I think it's good enough for now. We should figure out how to turn this into health data
26. Let's think about how to get from wav to measured data
27. I only recorded 10-300 hz
28. estimated_cycle_period_seconds = 0.80  
    estimated_rate_per_minute = 75

    I think that's good enough. How do we produce that from a WAV file
29. How are normal analog stethoscope reading recorded in FHIR?
30. I'm thinking a new page for Medilacra on a new branch. Reality interface. Have a drag and drop place to load a WAV. Visualize it. Find the pattern. Human validates or adds notes. A synthetic patient is generated, attached to the data. HL7 v2 message generated, then transformed into FHIR JSON bundle
31. Yeah we don't need the file in the HL7 message, just the file name and location. 
32. Ok, I think we've got it. Let's see the project plan, Nat style and focused on the mechanics. You don't need to over explain what this is NOT. This is clearly not a standard medical device. It's a fancy stethoscope that has a computer interface instead of ear piece
33. Yeah, Streamlit should be a thin client. We'll separate scripts to make it modular. Print to doc, add all the usual trimmings and version logging, raw prompts at the top
34. Create the reality interface branch  of Medilacra and add that as the first entry in docs as an MD.

    Lol also add a section about how I built the digital stethoscope from trash because it was easier and cheaper than buying one 😋 It's made from tubing I found in a construction dumpster, random USB headset with mic, the top of a water bottle, tubing from a broken washing machine, and electrical tape. Include this in the prompt history.

---

# 1. Project Definition

**Purpose.** Create a small MediLacra Reality Interface that can accept an acoustic WAV from the computer-connected stethoscope, derive a repeating cycle and rate, let a human validate what the pattern represents, bind the validated measurement to synthetic patient/encounter context, generate HL7 v2, and transform that message into FHIR JSON.

```text
physical reality
    ↓
computer-connected stethoscope
    ↓
WAV artifact
    ↓
periodicity measurement
    ↓
human semantic validation
    ↓
synthetic Patient + Encounter + Observation
    ↓
HL7 v2 ORU^R01
    ↓
HL7 → FHIR transform
    ↓
FHIR Bundle
```

**Primary implementation rule.** The Streamlit page owns interaction and display only. All mechanics that can be tested or reused without Streamlit live in ordinary Python modules.

## 1.1 Prototype digital stethoscope: built from trash

The physical interface was assembled from reclaimed or already-available material because building it was easier and cheaper than buying a digital stethoscope or dedicated contact-mic interface.

Current prototype components:

- tubing recovered from a construction dumpster;
- a random USB headset with microphone, used as the computer audio interface;
- the top of a water bottle, used as the chestpiece / acoustic chamber;
- tubing salvaged from a broken washing machine;
- electrical tape for mechanical coupling and air sealing.

Mechanically, the prototype is simply a stethoscope whose endpoint is a USB microphone rather than a pair of earpieces:

```text
chest
  ↓
water-bottle chestpiece / air chamber
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

The useful engineering fact is not the specific junk used. The interface creates a repeatable path from body-origin acoustic/mechanical activity into a digital waveform. The Reality Interface begins at that WAV boundary.

---

# 2. Branch and Integration Strategy

Branch:

```bash
git checkout main
git pull
git checkout -b feature/reality-interface
```

Repository branch created: `feature/reality-interface`.

Integration rules:

- Reuse current MediLacra patient and encounter generators rather than creating alternate demo-only generators.
- Reuse current HL7 v2 builders/schema machinery; extend only where the externally measured observation or artifact reference requires it.
- Reuse the existing HL7 → FHIR path. The FHIR Bundle is produced from the HL7 message, not independently regenerated from the UI state.
- Keep Reality Interface code isolated enough that the signal-processing path can be invoked from tests, CLI scripts, notebooks, or future interfaces without importing Streamlit.

---

# 3. Proposed Module Layout

```text
medilacra/
  reality_interface/
    __init__.py
    artifacts.py        # run directories, hashes, manifests, source file handling
    audio.py            # WAV load + metadata normalization
    periodicity.py      # envelope + autocorrelation + cycle/rate estimate
    binding.py          # validated measurement → existing clinical objects
    pipeline.py         # small orchestration layer for non-UI execution

pages/
  Reality_Interface.py  # thin Streamlit client only
```

Keep existing machinery where it already lives. HL7 builders, FHIR transformation, patient/encounter generators, reference data, and schema registries should remain in their current packages. Reality Interface imports them; it does not fork them.

## Thin-client boundary

| Streamlit page does | Python modules do |
|---|---|
| Accept file upload / drag-drop | Copy/persist source WAV and create artifact metadata |
| Render waveform / spectrogram / results | Load WAV and return analysis-ready arrays |
| Collect interpretation, accept/override, notes | Calculate envelope, autocorrelation, dominant period, rate |
| Show generated Patient/Encounter/Observation | Bind validated measurement to existing clinical objects |
| Buttons: Generate HL7 / Transform to FHIR | Call existing HL7 and FHIR transformation code |
| Display raw HL7 and JSON | Persist run artifacts and manifest |

---

# 4. Run Artifact Model

Each upload becomes one durable run directory. The directory is the simplest provenance package: raw evidence, metadata, human decision, HL7, and FHIR stay together.

```text
artifacts/
  reality_interface/
    20260825_213500_ab12cd/
      source.wav
      manifest.json
      validation.json
      message.hl7
      bundle.json
```

Example `manifest.json`:

```json
{
  "run_id": "20260825_213500_ab12cd",
  "source": {
    "filename": "source.wav",
    "location": "artifacts/reality_interface/20260825_213500_ab12cd/source.wav",
    "sha256": "...",
    "sample_rate_hz": 48000,
    "channels": 1,
    "duration_seconds": 10.0,
    "acquisition_band_hz": [10, 300]
  },
  "analysis": {
    "estimated_cycle_period_seconds": 0.80,
    "estimated_rate_per_minute": 75.0
  }
}
```

**Important mechanical detail.** The 10–300 Hz band is acquisition/context metadata supplied by the experiment; a WAV header by itself does not prove that band limit. Preserve it in the manifest rather than pretending it was inferred from the file format.

---

# 5. WAV Analysis Mechanics

Target output for v0.1:

```text
estimated_cycle_period_seconds = 0.80
estimated_rate_per_minute = 75.0
```

## Function contract

```text
analyze_periodicity(wav_path) -> PeriodicityResult

PeriodicityResult:
  estimated_cycle_period_seconds: float
  estimated_rate_per_minute: float
  time: array
  waveform: array
  envelope: array
  autocorrelation: array
  dominant_lag_seconds: float
```

## Algorithm

1. Load the WAV and retain original file untouched.
2. Convert stereo to mono if necessary.
3. Normalize for analysis; do not reinterpret normalized amplitude as calibrated physical pressure.
4. Create a smoothed energy envelope from the waveform.
5. Calculate autocorrelation of the envelope.
6. Search a plausible cycle window for the strongest repeating lag.
7. Convert lag to seconds: `cycle_period = lag_samples / sample_rate`.
8. Convert period to rate: `rate_per_minute = 60 / cycle_period`.
9. Return both numeric results plus the arrays needed for visual inspection.

```text
WAV
 ↓
mono waveform
 ↓
energy envelope
 ↓
autocorrelation
 ↓
dominant repeating lag
 ↓
cycle seconds
 ↓
60 / cycle seconds
 ↓
rate per minute
```

**Reason for the envelope/autocorrelation path.** A cardiac acoustic cycle can contain multiple transients. The first implementation should recover the repeating cycle rather than blindly count every visible peak.

---

# 6. Reality Interface Page Flow

## 6.1 Drop WAV

Accept `.wav`. Persist immediately. Display filename, duration, sample rate, channels, source location, and hash.

## 6.2 Visualize

Render waveform plus a useful low-frequency spectrogram or envelope view. Overlay the inferred cycle spacing so the human can inspect what the algorithm is calling periodic.

## 6.3 Measure

Display only the core v0.1 result prominently:

- estimated cycle period;
- estimated rate per minute.

## 6.4 Human validation

Human chooses what the periodicity represents — initial option `Heart rate`, fallback `Other/unspecified` — accepts or overrides the result, and may add notes.

## 6.5 Generate clinical context

Generate a synthetic Patient and Encounter using existing MediLacra generators. Bind the validated measurement to an Observation object instead of generating a synthetic heart-rate value.

## 6.6 Generate HL7 v2

Build an ORU^R01 from the synthetic clinical context and externally measured Observation. Add a reference to the WAV by filename and project-relative location; do not embed the file.

## 6.7 Transform to FHIR

Run the generated HL7 message through the existing HL7 → FHIR transformation path. Display and persist the resulting Bundle.

---

# 7. Human Validation Data

The machine output remains generic until the human binds semantics to it. The first version only needs enough structure to preserve the decision.

```json
{
  "machine_measurement": {
    "estimated_cycle_period_seconds": 0.80,
    "estimated_rate_per_minute": 75.0
  },
  "human_validation": {
    "interpretation": "heart_rate",
    "accepted": true,
    "override_rate_per_minute": null,
    "notes": null
  }
}
```

**Resulting canonical value.** If accepted without override, the validated clinical measurement is `75 /min`. If overridden, the human-supplied value becomes the clinical value while the original machine estimate remains preserved in the run metadata.

---

# 8. Synthetic Clinical Binding

```text
source.wav
    ↓
measured periodicity
    ↓
human: "heart rate"
    ↓
validated measurement
    +
existing gen_patient()
    +
existing gen_encounter()
    ↓
Observation
  code = 8867-4
  value = 75
  unit = /min
  source = external measurement
  subject_binding = synthetic_demo
```

- The WAV is real source evidence from the experiment.
- The Patient and Encounter are synthetic MediLacra context.
- The Observation value comes from the validated external measurement, not from the synthetic observation generator.
- Preserve this distinction in run metadata so provenance remains explicit.

---

# 9. HL7 v2 Output

Message type: `ORU^R01`.

```text
MSH  message metadata
PID  synthetic patient
PV1  synthetic encounter
OBR  observation/report context
OBX  numeric heart-rate result
OBX  source WAV reference (filename + location)
NTE  optional validated human note
```

Core measurement OBX, conceptually:

```text
OBX|1|NM|8867-4^Heart rate^LN||75|/min|||||F
```

## Source reference

Prefer an RP-style reference OBX if the existing serializer supports it cleanly. Otherwise use a simple textual reference in v0.1. The content is the project-relative filename/location, not the WAV payload.

```text
source_filename = source.wav
source_location = artifacts/reality_interface/<run_id>/source.wav
```

---

# 10. HL7 → FHIR Transformation

**Transformation rule.** The FHIR Bundle is derived from the generated HL7 message. Do not create a parallel UI-to-FHIR path.

```text
validated measurement
      ↓
ORU^R01
      ↓
existing transformer
      ↓
FHIR Bundle
```

Expected core Bundle contents:

- **Patient** — synthetic subject.
- **Encounter** — synthetic clinical context.
- **Observation** — heart rate `75 /min`.
- **Source artifact reference** — preserve the filename/location through the transform when the current mapping supports it. A `DocumentReference`/`Attachment` URL is the natural FHIR-side representation if implemented in v0.1; otherwise preserve it in the Observation output and promote later.

---

# 11. Pipeline API

A tiny orchestration layer keeps Streamlit thin and makes the full path callable elsewhere.

```python
run = create_run(wav_path, acquisition_band_hz=(10, 300))
measurement = analyze_periodicity(run.source_path)

validated = validate_measurement(
    measurement,
    interpretation="heart_rate",
    accepted=True,
    notes=None,
)

clinical = bind_to_synthetic_context(validated)
hl7 = generate_oru(clinical, run.source_reference)
fhir = transform_hl7_to_fhir(hl7)

persist(run, validated, hl7, fhir)
```

**UI behavior.** The page may call these functions stepwise so each transformation is visible, but the functions themselves remain independent of Streamlit state.

---

# 12. Build Order

| Work packet | Mechanics | Done when |
|---|---|---|
| WP1 — Branch + skeleton | Create branch, package folder, thin Streamlit page, and run-artifact directory helper. | Page imports successfully; empty workflow renders. |
| WP2 — WAV → periodicity | Implement WAV loader, envelope, autocorrelation, cycle/rate result, and unit tests against one known recording. | Known WAV prints a plausible cycle and rate; analysis code has no Streamlit dependency. |
| WP3 — Visualization | Return arrays from analysis and render waveform/envelope/spectrogram plus inferred cycle spacing. | Human can inspect why the result was produced. |
| WP4 — Validation | Add semantic choice, accept/override, notes; persist `validation.json`. | Machine estimate and human decision are both preserved. |
| WP5 — Synthetic binding | Call existing Patient/Encounter generators and construct Observation from validated external value. | Clinical objects contain the measured value without re-generating it. |
| WP6 — ORU | Feed objects into existing ORU path; add source filename/location reference. | `message.hl7` is valid enough for current MediLacra parser/validator and contains patient, encounter, heart rate, source reference. |
| WP7 — FHIR | Run ORU through existing transformer; persist `bundle.json`. | Bundle contains the same heart-rate fact after transformation. |
| WP8 — Linear demo polish | Render each stage in order with clear artifact/result panels. | One upload can be followed from WAV to FHIR without opening code. |
| WP9 — Freeze v0.1 | Add regression fixture, README/demo notes, tag/document exact branch state. | Repeatable demo; no hidden manual edits required. |

---

# 13. Acceptance Criteria — Reality Interface v0.1

- A WAV can be drag-dropped into the Streamlit page.
- The original file is persisted unchanged with filename, relative location, hash, and basic WAV metadata.
- The page visualizes the signal.
- Independent Python analysis returns `estimated_cycle_period_seconds` and `estimated_rate_per_minute`.
- The human can validate/override the measured rate and add notes.
- Existing MediLacra generators create a synthetic patient and encounter.
- The validated external measurement becomes the Observation value.
- An ORU^R01 is generated containing the synthetic context, numeric heart-rate result, and WAV filename/location reference.
- The ORU is transformed through the existing path into a FHIR JSON Bundle.
- WAV, manifest, validation record, HL7, and FHIR are persisted together under one run ID.
- The same numeric fact can be traced from measured periodicity → validated observation → HL7 → FHIR.
- The Streamlit page contains no signal-processing, HL7-construction, or FHIR-transformation implementation logic.

**Stop condition:** drag in a WAV → see the pattern → validate the measured rate as heart rate → generate synthetic context → generate ORU → transform to FHIR → inspect the same fact at every stage.

---

# 14. Test Strategy

- Unit test the periodicity function with a synthetic periodic waveform whose expected cycle is known exactly.
- Regression-test at least one real WAV captured with the prototype stethoscope. Use a tolerance band rather than requiring one exact BPM from noisy source material.
- Test stereo → mono handling and short/empty/corrupt WAV failure paths.
- Test that `source.wav` hash does not change after analysis.
- Test that a human override changes the clinical Observation but does not overwrite the machine estimate in manifest/validation metadata.
- Round-trip assertion: validated rate in canonical state == numeric OBX value == FHIR Observation value.
- Reference assertion: source filename/location emitted into HL7 can be traced back to the run artifact directory.

---

# 15. Demo Mechanics

1. Place chestpiece.
2. Record ~10 seconds through the USB headset path.
3. Save/export WAV.
4. Drag WAV into Reality Interface.
5. Watch waveform appear.
6. Read: cycle ≈ `0.80 s`; rate ≈ `75 /min`.
7. Human selects **Heart rate** and accepts/adds note.
8. Generate synthetic patient + encounter.
9. Generate ORU^R01.
10. Transform ORU to FHIR Bundle.
11. Show the same `75 /min` fact surviving every representation.

**Useful artifact after the demo.** The run directory itself is a durable record of the demonstration and can be checked into an examples/fixtures area later if the WAV is appropriate for publication.

---

# 16. Decisions Locked for v0.1

| ID | Decision | Reason |
|---|---|---|
| D-001 | Reality Interface is a new feature branch: `feature/reality-interface`. | Keeps the experiment isolated and reviewable. |
| D-002 | Streamlit is a thin client. | UI is replaceable; mechanics remain reusable and testable. |
| D-003 | WAV is the raw source artifact and stays unchanged. | Preserves provenance and reproducibility. |
| D-004 | v0.1 derives only cycle period and rate. | Enough to demonstrate physical signal → measured fact without building a signal-analysis cathedral. |
| D-005 | Human performs the semantic binding to heart rate. | Separates machine pattern measurement from clinical interpretation. |
| D-006 | Patient and encounter are generated synthetically after validation. | Keeps the measured physical source distinct from the demo identity/context. |
| D-007 | Observation value comes from the validated external measurement. | Prevents the generator from replacing measured reality with synthetic reality. |
| D-008 | HL7 message contains source filename/location, not the WAV bytes. | Keeps transport lightweight while preserving source traceability. |
| D-009 | FHIR is transformed from HL7, not regenerated independently. | Makes the bridge itself testable and exposes what survives transformation. |
| D-010 | One run directory holds WAV, manifest, validation, HL7, and FHIR. | Creates a simple durable provenance package. |
| D-011 | The prototype computer-connected stethoscope is built from reclaimed components rather than purchased as a dedicated device. | It was faster and cheaper, and the resulting interface is sufficient to create the WAV boundary needed for the experiment. |

---

# 17. Open Implementation Decisions

- Exact current package names/entry points for the existing ORU builder and HL7 → FHIR transformer should be resolved from the checked-out branch before coding. Reuse the existing paths rather than naming new wrappers prematurely.
- Choose the simplest source-reference OBX encoding supported by the existing HL7 serializer: RP if cleanly supported; textual fallback if not.
- Choose waveform/spectrogram plotting library based on what MediLacra already depends on; avoid introducing a visualization dependency solely for this page if Streamlit/native plotting is sufficient.
- Decide whether `acquisition_band_hz` is fixed to `[10, 300]` for the first demo or exposed as metadata input. It should not silently be inferred from the WAV header.

---

# 18. Version Log

| Version | Date | Status | Changes |
|---|---|---|---|
| v0.1 | 2026-08-25 | Superseded | Initial implementation plan. Incorporated computer-connected stethoscope prototype, WAV periodicity extraction, human semantic validation, synthetic patient/encounter binding, HL7 ORU generation, HL7 → FHIR transformation, source filename/location provenance, thin Streamlit client, modular Python scripts, work packets, acceptance criteria, tests, decision log, and raw prompt history. |
| v0.2 | 2026-08-25 | Current | Created `feature/reality-interface`; materialized the plan as the first Markdown entry under `docs/`; added explicit documentation of the trash-built digital stethoscope and its reclaimed components; appended the branch/documentation prompt verbatim; added D-011. |

---

# 19. Handoff Notes

- Start implementation at WP1/WP2. Do not touch the UI beyond enough scaffolding to exercise the independent analysis function.
- Before adding new abstractions, inspect existing MediLacra function names and object contracts and bind to them directly.
- Keep every transformation inspectable: raw source, machine measurement, human validation, canonical clinical object, HL7, FHIR.
- Version the document when mechanics materially change. Append decisions rather than rewriting history where the old decision remains relevant.
- For Connectathon readiness, favor repeatability and visible provenance over UI polish.

**Source note:** This plan was derived from the raw prompt history above and the current MediLacra functionality overview. It intentionally reuses existing generators, data classes, HL7 builders/schema knowledge, and transformation machinery rather than inventing replacement architecture.

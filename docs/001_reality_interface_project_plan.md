# MediLacra Reality Interface

**Project Plan v0.3 — completed experiment record**

| Field | Value |
|---|---|
| Document version | v0.3 |
| Original plan date | 2026-08-25 |
| Completion pass | 2026-08-27 |
| Status | Implemented; experiment complete enough for Connectathon/demo use |
| Target branch | `feature/reality-interface` |
| UI rule | Streamlit is a thin client; processing and transformation logic live in reusable modules. |
| Primary demonstrated path | Physical acoustic signal → WAV → periodicity measurement → human semantic validation → synthetic patient/encounter → HL7 v2 ORU^R01 → downloadable artifact → independent re-ingestion → FHIR Bundle → PIQI |
| Result record | `docs/003_reality_interface_experiment_result.md` |

> **FHIR does not care whether reality entered the information system through a $14,000 medical appliance or a water-bottle cap and electrical tape. It cares what observation is being represented, how it was obtained, and whether the semantics survive.**

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
35. Print the updated doc
36. Ok, what are the scripts we need to write, in order
37. Add the package options or functions for each script, with your top recommendation and why
38. FHIR does not care whether reality entered the information system through a $14,000 medical appliance or a water-bottle cap and electrical tape. It cares what observation is being represented, how it was obtained, and whether the semantics survive.

    Add this to the top of the README, version with all the trimmings
39. 1 + 2- let's use scipy + numPy  
    2- hilbert looks good  
    3 + 10- pytest looks good  
    4- I've used pathlib before, would that make sense here?  
    11- Fine, as long as we actually need matplotlib. Don't want to make this fancier than needed

    What else do you need from me before going to build this?
40. Here's the file
41. Can you add an HL7 v2 output that's downloadable from a Streamlit button? If it doesn't exist yet
42. `[Images uploaded]`  
    Looking good! Used a fresh WAV
43. Should we do a final documentation pass? This project is done ish
44. Ok, go make the final updates

---

# 1. Question

Can a physical acoustic signal enter MediLacra, become a measured fact, receive explicit human healthcare semantics, attach to synthetic clinical context, and survive HL7 v2 → FHIR transformation while retaining provenance?

**Result: yes.**

The experiment is now documented as complete enough. Further work should be driven by an actual interoperability/Connectathon need rather than by extending the demo for its own sake.

---

# 2. Physical Interface

The prototype computer-connected stethoscope was assembled from reclaimed or already-available material because building it was easier and cheaper than buying a dedicated digital stethoscope or contact-mic interface.

Components:

- tubing recovered from a construction dumpster;
- a random USB headset with microphone;
- the top of a water bottle as the chestpiece/acoustic chamber;
- tubing salvaged from a broken washing machine;
- electrical tape for coupling and sealing.

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

The exact trash is not the software dependency. The useful boundary is the WAV: an inspectable source artifact carrying body-origin acoustic/mechanical activity into a computer-readable representation.

---

# 3. Final Architecture

```text
physical reality
    ↓
computer-connected stethoscope
    ↓
WAV source artifact
    ↓
SciPy / NumPy periodicity analysis
    ↓
measured cycle + rate
    ↓
human semantic validation
    ↓
validated Heart rate
    +
synthetic Patient + Encounter
    ↓
HL7 v2 ORU^R01
    ↓
downloadable .hl7 artifact
    ↓
existing / independent HL7 → FHIR consumer
    ↓
FHIR Bundle
    ↓
PIQI
```

The critical boundary remains explicit:

```text
machine measurement: repeating rate
        ≠
human semantic interpretation: heart rate
```

The machine does not silently promote acoustic periodicity into a clinical concept.

---

# 4. Implemented Module Layout

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

## Thin-client boundary

| Streamlit page does | Backend modules do |
|---|---|
| Accept WAV upload | Preserve/copy source and create run artifacts |
| Display waveform / envelope | Load, normalize analysis copy, downsample, analyze periodicity |
| Show measured cycle/rate | Return deterministic measurement state |
| Collect interpretation / accept / override / notes | Validate and serialize semantic decision |
| Show synthetic Patient/Encounter/Observation | Bind validated measurement to existing MediLacra generators/models |
| Show/download HL7 | Build/persist ORU^R01 |
| Show FHIR | Transform the generated HL7 artifact through the existing converter |

No signal-processing, HL7-construction, or FHIR-mapping implementation lives in the Streamlit page.

---

# 5. Signal Analysis

Locked choices:

| Concern | Implementation |
|---|---|
| WAV load | `scipy.io.wavfile.read` |
| Working signal | NumPy arrays |
| Downsampling | `scipy.signal.resample_poly` when needed |
| Envelope | `scipy.signal.hilbert` |
| Smoothing | short moving average (~50 ms in v0.1) |
| Periodicity | `scipy.signal.correlate(..., method="fft")` |
| Search | plausible repeating-rate window |
| Tests | pytest |
| File handling | `pathlib.Path` + stdlib hashing/copy/JSON |
| Visualization | Streamlit-native charts; no Matplotlib dependency |

Conceptual algorithm:

```text
WAV
 ↓
mono analysis copy
 ↓
DC removal + normalization
 ↓
Hilbert amplitude envelope
 ↓
smoothing
 ↓
autocorrelation
 ↓
dominant plausible lag
 ↓
cycle seconds
 ↓
60 / cycle seconds
 ↓
rate per minute
```

The source WAV is not normalized or rewritten. Analysis transformations happen to a working copy.

---

# 6. Human Validation

Machine output is preserved separately from human interpretation.

```json
{
  "machine_measurement": {
    "estimated_cycle_period_seconds": 0.69,
    "estimated_rate_per_minute": 86.96
  },
  "human_validation": {
    "interpretation": "heart_rate",
    "accepted": true,
    "override_rate_per_minute": null,
    "notes": "Excited to share this, HR reflects that"
  }
}
```

If the human overrides the value, the machine estimate remains preserved while the approved value becomes the clinical Observation value.

---

# 7. Synthetic Clinical Binding

After validation, existing MediLacra generators create the demo identity/context:

```text
gen_patient()
gen_encounter(patient_id)
        +
validated external measurement
        ↓
clinical binding
```

For the v0.1 heart-rate path:

```text
LOINC:   8867-4
Display: Heart rate
Unit:    /min
Source:  validated external measurement
Subject: synthetic demo patient
Context: synthetic demo encounter
```

The source physical signal and generated clinical identity have different provenance and remain distinguishable.

---

# 8. Run Artifact Model

Each run keeps source evidence and representations together:

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

The run directory uses `pathlib.Path`. The WAV is copied unchanged and hashed. Reality Interface artifacts are gitignored.

---

# 9. HL7 v2 Output

Message type: `ORU^R01`.

Implemented shape:

```text
MSH  message metadata
PID  synthetic patient
PV1  synthetic encounter
OBR  observation context
OBX  NM  8867-4^Heart rate^LN  <validated rate> /min
OBX  ST  SOURCE-WAV^Source WAV recording^99MEDILACRA  filename/location
NTE  optional human note
```

The source file is referenced, not embedded.

The Streamlit page displays the ORU and provides a run-specific **Download HL7 v2 ORU^R01** button.

---

# 10. HL7 → FHIR

The FHIR Bundle is derived from the generated HL7 artifact rather than regenerated directly from Streamlit state.

```text
validated measurement
      ↓
ORU^R01
      ↓
existing FHIR conversion path
      ↓
FHIR Bundle
```

During implementation, the existing converter exposed an MSH indexing mismatch: the generic pipe-split representation omits MSH-1 while downstream accessors expect normal HL7 field numbering. Reality Interface handles this with a localized compatibility step rather than implementing a second FHIR converter.

---

# 11. Demonstrated Runs

## Development WAV baseline

A development recording supplied outside the repository produced approximately:

```text
source sample rate:              44,100 Hz
channels:                        1
duration:                        17.836 s
estimated_cycle_period_seconds:  0.657
estimated_rate_per_minute:       91.3
periodicity_score:               ~0.345
```

This established that the SciPy/NumPy path could recover repeating structure from an actual prototype-stethoscope WAV.

## Fresh end-to-end run

A later fresh recording was run through the complete Streamlit workflow and produced approximately:

```text
estimated_rate_per_minute = 86.957
```

The human selected **Heart rate**, accepted the measurement, and entered:

```text
Excited to share this, HR reflects that
```

The generated ORU visibly contained:

```text
OBX|1|NM|8867-4^Heart rate^LN||86.957|/min...
OBX|2|ST|SOURCE-WAV^Source WAV recording^99MEDILACRA|...
NTE|1||Excited to share this, HR reflects that
```

The `.hl7` file was downloaded from Reality Interface and uploaded into the separate **HL7 v2 → FHIR Converter + PIQI Scorecard** surface.

The independent consumer:

- recognized the message as `ORU^R01`;
- produced a FHIR Bundle with the expected resource family;
- ran PIQI;
- returned PIQI **75** for the observed message;
- passed **6 / 8** applicable checks;
- reported **0 critical failures**.

That PIQI score describes the demonstrated run only. It is not treated as a universal score for Reality Interface output.

---

# 12. Acceptance Criteria — Final Status

| Criterion | Status |
|---|---|
| Drag/drop WAV into Streamlit | Demonstrated |
| Preserve original source artifact | Implemented |
| Visualize source signal | Demonstrated |
| Visualize energy envelope | Demonstrated |
| Derive cycle/rate outside Streamlit | Implemented |
| Human accept/override/notes | Demonstrated |
| Generate synthetic Patient + Encounter | Demonstrated |
| Bind validated external value as Heart rate | Demonstrated |
| Generate ORU^R01 | Demonstrated |
| Reference WAV filename/location without embedding bytes | Demonstrated |
| Include human note in NTE | Demonstrated |
| Display generated HL7 | Demonstrated |
| Download `.hl7` from Streamlit | Demonstrated |
| Transform ORU into FHIR | Demonstrated |
| Re-ingest downloaded artifact through separate consumer | Demonstrated |
| Run PIQI on independently converted output | Demonstrated |
| Keep Streamlit thin | Implemented |

**Original stop condition:** drag in a WAV → see the pattern → validate measured rate as heart rate → generate synthetic context → generate ORU → transform to FHIR → inspect the same fact at every stage.

**Expanded demonstrated stop condition:** the downloadable ORU also left the producing interface, entered a separate converter, became FHIR, and was scored by PIQI.

---

# 13. Decisions Locked

| ID | Decision | Reason |
|---|---|---|
| D-001 | Reality Interface lives on `feature/reality-interface`. | Keeps the experiment isolated/reviewable. |
| D-002 | Streamlit is a thin client. | Mechanics remain reusable and testable. |
| D-003 | WAV is raw source evidence and stays unchanged. | Preserves provenance/replay. |
| D-004 | v0.1 derives cycle period and rate only. | Enough to test the representation chain without building a signal-analysis cathedral. |
| D-005 | Human performs the semantic binding to Heart rate. | Separates measurement from interpretation. |
| D-006 | Patient and Encounter are synthetic. | Keeps source physical provenance distinct from demo identity/context. |
| D-007 | Observation value comes from validated external measurement. | Prevents synthetic generation from replacing measured reality. |
| D-008 | HL7 carries source filename/location, not WAV bytes. | Lightweight traceability. |
| D-009 | FHIR is transformed from HL7, not generated in parallel. | Makes semantic survival testable. |
| D-010 | One run directory keeps source, manifest, validation, HL7, and FHIR together. | Simple durable provenance package. |
| D-011 | Prototype hardware uses reclaimed components. | Faster/cheaper and sufficient to establish the WAV boundary. |
| D-012 | SciPy + NumPy + Hilbert/autocorrelation are the v0.1 signal path. | Minimal dependency surface for the needed mechanics. |
| D-013 | pytest is the regression-test framework. | Lightweight and already aligned with repo test style. |
| D-014 | `pathlib.Path` owns artifact paths. | Clear cross-platform filesystem semantics. |
| D-015 | No Matplotlib unless native Streamlit charts become insufficient. | Avoid unnecessary visualization complexity. |
| D-016 | Source reference uses a simple `ST` OBX in v0.1. | Existing converter already handles the representation. |
| D-017 | Downloaded HL7 is a first-class output artifact. | Lets the representation leave the producing UI and be tested by independent consumers. |

---

# 14. Known Rough Edges / Deferred Work

- Periodicity measurement is intentionally primitive and not a general physiological-signal framework.
- Source WAV reference uses a simple `ST` representation rather than a richer pointer/provenance structure.
- The generic FHIR converter's MSH indexing issue remains a separate cleanup candidate; Reality Interface uses a localized compatibility step.
- The observed PIQI score of 75 leaves two non-passing applicable assertions to inspect if PIQI optimization becomes useful.
- Native Streamlit charts are intentionally simple; no plotting dependency is added unless a real need appears.

These are not open requirements for this experiment. They are possible next steps if a concrete consumer demands them.

---

# 15. Completion Rule

The experiment is complete when the same fact can be traced from physical reality, through measurement and human interpretation, into HL7 v2, through an independent consumer, and into FHIR without losing what it means.

**That happened.**

---

# 16. Version Log

| Version | Date | Status | Changes |
|---|---|---|---|
| v0.1 | 2026-08-25 | Superseded | Initial implementation plan: physical-source WAV, periodicity extraction, human validation, synthetic binding, ORU generation, HL7 → FHIR transformation, provenance package, thin Streamlit client, tests, decisions, and raw prompt history. |
| v0.2 | 2026-08-25 | Superseded | Created `feature/reality-interface`; materialized plan as first Markdown entry under `docs/`; documented trash-built stethoscope and reclaimed components; added D-011. |
| v0.3 | 2026-08-27 | Current / completed | Final documentation pass. Preserved raw prompt history; replaced planned module names with implemented layout; recorded SciPy/NumPy/Hilbert/pytest/pathlib decisions; documented downloadable HL7, real-WAV baseline, fresh 86.957/min end-to-end run, independent re-ingestion, FHIR conversion, PIQI 75 (6/8 applicable, 0 critical), completed acceptance criteria, deferred rough edges, and explicit stop condition. |

---

# 17. Related Documentation

- `docs/002_reality_interface_build_log.md` — implementation record and discovered mechanics.
- `docs/003_reality_interface_experiment_result.md` — concise final evidence/result record.
- `README.md` — project-level capability summary and quick start.

**Source note:** the design grew from the raw prompt history above and the existing MediLacra generation/HL7/FHIR machinery. The final implementation reuses those existing seams rather than creating a parallel healthcare-data architecture.

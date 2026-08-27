# MediLacra Reality Interface — Experiment Result

**Result Record v1.0**

| Field | Value |
|---|---|
| Date closed | 2026-08-27 |
| Branch | `feature/reality-interface` |
| Status | Experiment complete enough; demonstrated end to end |
| Primary question | Can a physical acoustic signal become a human-validated healthcare observation and survive HL7 v2 → FHIR transformation without losing its meaning or source traceability? |
| Result | **Yes** |

> **FHIR does not care whether reality entered the information system through a $14,000 medical appliance or a water-bottle cap and electrical tape. It cares what observation is being represented, how it was obtained, and whether the semantics survive.**

---

## Question

Can a physical acoustic signal enter MediLacra, be reduced to a measured repeating rate, receive explicit human semantics, attach to synthetic clinical context, move into HL7 v2, leave the producing application as an actual artifact, enter an independent consumer, and emerge as FHIR without losing what the observation means?

## Result

**Yes.**

The complete demonstrated path was:

```text
body-origin signal
        ↓
trash-built computer stethoscope
        ↓
WAV source artifact
        ↓
SciPy / NumPy periodicity measurement
        ↓
human validation: Heart rate
        ↓
synthetic Patient + Encounter
        ↓
LOINC 8867-4 Heart rate Observation
        ↓
HL7 v2 ORU^R01
        ↓
downloaded .hl7 file
        ↓
separate HL7 v2 → FHIR converter
        ↓
FHIR Bundle
        ↓
PIQI scorecard
```

---

## Physical source

The first source interface was assembled from reclaimed/available material because it was easier and cheaper than buying a dedicated computer-connected stethoscope:

- construction-dumpster tubing;
- random USB headset with microphone;
- water-bottle top used as a chestpiece/acoustic chamber;
- tubing salvaged from a broken washing machine;
- electrical tape.

The software does not depend on those exact materials. The meaningful technical boundary is the WAV produced by the interface.

---

## Measurement

Reality Interface uses a small signal-processing path:

```text
WAV
 ↓
mono working signal
 ↓
DC removal / normalization
 ↓
resample for analysis when needed
 ↓
Hilbert amplitude envelope
 ↓
smoothing
 ↓
autocorrelation
 ↓
dominant repeating lag
 ↓
cycle period + rate per minute
```

The source WAV is preserved unchanged. The machine result remains a generic periodicity measurement until a human supplies clinical semantics.

---

## Human semantic transformation

The human-validation step is explicit:

```text
machine: ~86.96 repeating cycles/minute
        ↓
human: Heart rate
        ↓
LOINC 8867-4
unit: /min
```

The demonstrated fresh run was accepted without override and included the human note:

```text
Excited to share this, HR reflects that
```

This is the semantic transformation bridge in the experiment: the software measures a pattern; the human states what that pattern represents.

---

## Demonstrated HL7 v2 artifact

The generated ORU visibly included:

```text
OBX|1|NM|8867-4^Heart rate^LN||86.957|/min...
OBX|2|ST|SOURCE-WAV^Source WAV recording^99MEDILACRA|...
NTE|1||Excited to share this, HR reflects that
```

The Patient and Encounter were synthetic. The heart-rate value came from the validated external measurement. The source WAV was referenced by filename/location rather than embedded.

Reality Interface exposed the message as a downloadable `.hl7` artifact from Streamlit.

---

## Independent consumption

The downloaded `.hl7` file was uploaded to the separate **HL7 v2 → FHIR Converter + PIQI Scorecard** interface.

Observed result:

```text
recognized type:        ORU^R01
FHIR Bundle:            generated
PIQI profile:           Clinical-Minimal
PIQI index:             75
applicable checks:      8
passed checks:          6
critical failure count: 0
```

The downstream UI showed the expected FHIR resource family, including Patient, Encounter, MessageHeader, DiagnosticReport, and Observation resources.

This independent re-ingestion is the key external boundary test. The producing Reality Interface did not merely render its own FHIR JSON; the actual HL7 representation left that interface and was accepted by another consumer.

The PIQI score of 75 is evidence from this specific run only. It is not treated as a universal score for Reality Interface output.

---

## What survived the transformation

The demonstrated chain preserved or retained traceability to:

- the measured numeric value;
- `/min` unit;
- semantic identity as Heart rate;
- LOINC `8867-4`;
- synthetic Patient linkage;
- synthetic Encounter linkage;
- source WAV filename/location reference;
- human validation note;
- HL7 message identity as `ORU^R01`;
- downstream FHIR representation.

The source artifact and synthetic clinical identity remained intentionally distinct.

---

## What the experiment does not need to resolve

The following are known rough edges, not blockers to the experimental result:

- periodicity analysis is intentionally small rather than a general physiological-signal framework;
- source WAV provenance currently uses a simple `ST` OBX representation;
- the existing generic FHIR converter has an MSH indexing mismatch handled by a localized Reality Interface compatibility step;
- two of eight applicable PIQI assertions did not pass in the observed run;
- Streamlit visualization remains intentionally simple and does not currently justify a Matplotlib dependency.

These become work only if a real consumer, validator, or Connectathon interaction makes them relevant.

---

## Stop condition

The experiment is complete when the same fact can be traced:

```text
physical reality
 ↓
measurement
 ↓
human interpretation
 ↓
healthcare semantics
 ↓
HL7 v2
 ↓
independent consumer
 ↓
FHIR
```

without losing what the observation means.

**That happened.**

---

## Decision

Close the Reality Interface experiment in its current state.

Do not extend it merely to make the demo more elaborate. Reopen the branch when a concrete interoperability need, validator failure, Connectathon interaction, or new physical-signal experiment produces a reason to change the mechanics.

---

## Related records

- `README.md` — project-level capability summary.
- `docs/001_reality_interface_project_plan.md` — plan, raw prompts, final acceptance status, and locked decisions.
- `docs/002_reality_interface_build_log.md` — implementation record, baseline analysis, compatibility findings, and final validation run.

---

## Version log

| Version | Date | Status | Changes |
|---|---|---|---|
| v1.0 | 2026-08-27 | Final result record | Captured the experiment question, physical source, measurement/semantic boundary, demonstrated ~86.96/min run, downloadable ORU, independent re-ingestion, FHIR conversion, PIQI 75 result (6/8 applicable, 0 critical), semantic/provenance survival, known rough edges, and explicit stop decision. |

---

## Raw prompt provenance

> `[Images uploaded]`  
> Looking good! Used a fresh WAV

> Should we do a final documentation pass? This project is done ish

> Ok, go make the final updates

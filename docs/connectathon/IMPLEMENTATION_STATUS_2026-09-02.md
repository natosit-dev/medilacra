# PIQI Connectathon 43 — First Implementation Pass

**Date:** 2026-09-02  
**MediLacra branch:** `connectathon/piqi-43`  
**PIQITT branch:** `connectathon/piqi-43`  
**Status:** LOCAL EXPERIMENT PATH IMPLEMENTED; EXTERNAL PIQI ENDPOINT CONTRACT PENDING TRACK KICKOFF

---

## What exists now

The first implementation pass closes the local half of the MVP path:

```text
MediLacra / Disco Inferno HL7
        ↓
existing PIQITT HL7 → FHIR converter
        ↓
FHIR baseline
        ↓
controlled one-defect FHIR mutations
        ↓
baseline + mutant + mutation manifest + local preflight
        ↓
timestamped local evidence pack
```

The implementation deliberately stops before external PIQI endpoint submission. The September 2 track kickoff is expected to clarify the current submission mechanics and the Evaluation/Audit Report structures. Raw response capture should be built from that observed contract rather than guessed now.

---

## Reuse boundary

### PIQITT remains authoritative for HL7 → FHIR

MediLacra does not contain a copied FHIR mapping implementation. `connectathon/piqitt_bridge.py` loads the existing local PIQITT converter from:

```text
<piqitt checkout>/scripts/fhir_convert_backend.py
```

The checkout defaults to a sibling `../piqitt` repository and can be overridden with `PIQITT_REPO` or through the Streamlit page.

PIQITT also has a thin Connectathon CLI wrapper on its matching branch:

```bash
python -m scripts.fhir_convert \
  --input source.hl7 \
  --output baseline.fhir.json \
  --message-index 1
```

### Disco Inferno supplies the mutation discipline

FHIR-level corruption lives under the existing Disco Inferno experiment namespace:

```text
experiments/disco_inferno/fhir_corruptions.py
```

The first pass preserves the same experimental boundary used by Disco Inferno:

- baseline is deep-copied and never mutated in place;
- mutation selection is seeded;
- a non-control mutant must differ at exactly one JSON path;
- before/after state and artifact hashes are recorded;
- control produces zero delta.

---

## Current local scenario pack

The three non-control targets remain provisional until confirmed with the PIQI track leads.

| Case | Mutation | Provisional PIQI target |
|---|---|---|
| `case_000_control` | no change | control |
| `case_001_availability` | remove `Patient.identifier` | `ATTR_ISPOPULATED` / `AV_UNPOP` |
| `case_002_code_system` | remove `Observation.code.coding[0].system` | `CONCEPT_HASCODESYSTEM` / `AV_UNPOP` |
| `case_003_invalid_member` | replace `Observation.code.coding[0].code` with a known non-member | `CONCEPT_ISVALIDMEMBER` / `CONF_INCOMP` |

The UI hides cases that cannot be applied to the selected baseline. For example, Observation-targeting cases are not offered for an ADT bundle with no OBX-derived Observations.

---

## Streamlit workflow

Run MediLacra normally:

```bash
conda activate dev310
cd ~/medilacra
git checkout connectathon/piqi-43
git pull
streamlit run medi_lacra_app.py
```

The app now includes:

```text
PIQI Connectathon 43
```

The page supports:

1. selecting an existing MediLacra/Disco Inferno HL7 file or uploading one;
2. locating a local PIQITT checkout;
3. inspecting multiple HL7 messages through PIQITT;
4. choosing the exact message to convert;
5. materializing and inspecting a FHIR baseline;
6. viewing resource counts and local preflight status;
7. preserving source provenance and repository revisions when locally available;
8. selecting applicable Connectathon cases;
9. building the timestamped local evidence pack;
10. inspecting baseline, mutant, manifest, and preflight side by side;
11. downloading individual FHIR artifacts or the entire ZIP pack.

There are direct page links back to ordinary MediLacra generation and Disco Inferno so the workbench does not duplicate those controls.

---

## CLI workflow

With MediLacra and PIQITT checked out as sibling directories:

```bash
cd ~/medilacra
conda activate dev310
git checkout connectathon/piqi-43

python -m connectathon.run \
  --input experiments/disco_inferno/output/<run-id>/hl7/ORU_R01_<run-id>.hl7 \
  --piqitt-repo ../piqitt \
  --message-index 1
```

Output is written under:

```text
connectathon/results/<run-id>/
├── run_manifest.json
└── cases/
    ├── case_000_control/
    │   ├── baseline.fhir.json
    │   ├── mutant.fhir.json
    │   ├── manifest.json
    │   └── preflight.json
    └── ...
```

---

## Provenance currently captured

When available locally, the pack records:

- source HL7 SHA-256;
- MediLacra git revision;
- PIQITT git revision;
- PIQITT converter path;
- selected HL7 message index/type;
- Disco Inferno run ID when source material came from a Disco run;
- Disco manifest path and hash;
- relevant Disco settings when present;
- FHIR baseline hash;
- FHIR mutant hash;
- mutation seed;
- exact resource, resource ID, entry index, FHIR path, before value, and after value;
- local preflight results.

This is sufficient to trace a local test artifact back through its materialization lineage without treating the comparison UI as the evidence source.

---

## Validation status

MediLacra now has a branch-scoped GitHub Actions smoke workflow covering:

- compilation of the Connectathon modules and Streamlit page;
- FHIR corruption invariants;
- scenario-pack materialization.

The first MediLacra Connectathon smoke run passed.

PIQITT has a matching smoke workflow for the CLI wrapper and converter. Its first run exposed that `scripts/` was not an importable package under clean CI; `scripts/__init__.py` was then added on the Connectathon branch. The follow-up run should be treated as the authoritative PIQITT status.

---

## Deliberately unresolved until the PIQI kickoff

The following work should not be implemented from assumptions:

1. live PIQI endpoint URLs and authentication mechanics;
2. exact FHIR payload expectations at the provided test clients/services;
3. rubric/model selection request shape;
4. actual Evaluation Report and Audit Report response structures;
5. identifiers/version metadata that must be preserved for comparison;
6. final choice of the three PIQI SAM targets in the challenge pack.

The disabled **Submit pack to PIQI endpoints** area is intentional. Once the live contract is known, the next implementation slice is:

```text
raw endpoint submission/capture
        ↓
minimal per-endpoint normalization
        ↓
A ↔ B and endpoint ↔ mutation-ground-truth comparator
```

Raw responses remain primary evidence and must be preserved before normalization.

---

## Known limitation

PIQITT's existing converter currently uses generated UUIDs and current timestamps in FHIR resources. The resulting Bundle is therefore not byte-identical across separate conversions of the same HL7 input. The experiment does not currently require cross-run byte determinism because each run preserves and hashes its exact baseline before mutation.

If cross-run FHIR identity becomes useful for the Connectathon experiment, deterministic ID/timestamp injection can be added later without changing the current mutation contract.

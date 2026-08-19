# MediLacra Data Dumper — Branch Documentation

**Working folder / project name:** `medilacra_data_dumper`  
**GitHub repository:** `natosit-dev/medilacra`  
**Branch:** `agent/connectathon-fast-generation-prep`  
**Status:** Active experiment / performance-prep branch  
**Updated:** 2026-08-19

## Purpose

This branch adds an experiment-oriented batch generation path to MediLacra without replacing the existing pipeline.

The working name for this branch effort is now **MediLacra Data Dumper**, with the local repository folder named `medilacra_data_dumper`. The upstream GitHub repository and Python module names are intentionally unchanged for now. The new name describes the actual root behavior more clearly: generate a synthetic healthcare reality at configurable scale and dump linked representations to usable output files.

The immediate goal is simple: make MediLacra capable of generating large, linked synthetic healthcare datasets with experiment-style CLI controls, while preserving the existing Patient / Encounter / Observation / Transaction generators and the HL7 message-building behavior.

The branch is designed around three practical requirements:

1. Explicit cardinality controls similar to prior MediLacra experiments.
2. No external SDOH API calls during high-volume generation.
3. Enough instrumentation to measure scale, distributions, and performance without manually parsing the output afterward.

Gender Harmony remains enabled by default and is treated as intentional semantic content rather than noise to be normalized away.

---

## Prompt History

The following prompts capture the main decisions that shaped this branch.

> “I liked how quickly we generated data for the sparsity experiment. Could be do the same for Medilacra?”

This established the main goal: bring the fast, explicit, experiment-style generation controls into MediLacra.

> “Let's fork Medilacra and do initial prep for this. Let's start with the CLI type controls like we did for the experiments. Cut the SDOH API stuff”

This led to the isolated branch and the first batch-specific modules. The existing legacy pipeline remains intact; the new batch path avoids AirNow, Census ACS, PLACES, and BLS network calls.

> “Ok, let's test 1000x2x5x2. Give me the command”

This established the first meaningful benchmark shape:

- 1,000 patients
- 2 encounters per patient
- 5 observations per encounter
- 2 transactions per encounter

> “At the end, let's add: PID Sex distribution / Top 5 Diagnoses / Gender Harmony Distribution”

This added lightweight in-flight counters so summary statistics are generated during the run rather than by rereading HL7 afterward.

> “I think our next benchmark should be 1 million entities, same as the experiment last week”

This established the first large-scale benchmark target while keeping the same 1:2:10:4 entity proportions.

> “Go ahead and add the log suppression if we need to update the code.”

Batch mode was changed to suppress routine INFO logging by default. `--verbose` restores detailed logging for debugging.

> “I don't love that there's not a status bar, maybe we can add that if this is successful”

A Rich patient-level progress bar was added, with `--no-progress` available for clean automated runs.

> “Ok, make the updates to the repo. I'll try a smaller batch run to test the changes when it's ready”

Bulk output was changed from repeated open/append/close cycles to persistent file handles, with periodic flushing. This optimization is committed but still pending a fresh benchmark at the time of this documentation update.

> “Give me a suite of CLI commands for various testing scenarios and separate ones for scale”

This produced a repeatable CLI test suite covering smoke, regression, sparse/missing-data shapes, feature isolation, determinism, verbose debugging, clean benchmarking, and a 10K → 1M scale ladder.

> “Add them all to an MD and drop it in the branch”

The full command suite was added as `BATCH_TEST_SCENARIOS.md` so testing can be repeated without reconstructing commands from conversation history.

> “Let's leave everything else the same, but we're going to change the name of this to medilacra_data_dumper for the repo folder. You can note the update in the documentation decision log. The old name was boring and didn't explain the root of what it does. Names are important. Also update the prompt history with the latest prompts in the main documentation”

This changed the working folder/project name to `medilacra_data_dumper` while intentionally leaving the upstream GitHub repository, branch, package/module paths, and functional behavior unchanged. The name now describes the primitive directly: MediLacra generates linked synthetic healthcare data and dumps representations for downstream use and experimentation.

---

## Current Architecture

### Batch CLI

Entry point:

```bash
python -m hl7_demo.batch_cli
```

Primary modules added for this branch:

- `hl7_demo/batch_cli.py`
- `hl7_demo/batch_pipeline.py`
- `hl7_demo/batch_messages.py`
- `hl7_demo/offline_adt.py`

The batch path reuses the existing MediLacra entity generators and segment/message construction wherever practical.

### Cardinality controls

```text
--patients N
--encounters-per-patient N
--observations-per-encounter N
--transactions-per-encounter N
```

Patients and encounters must be at least 1. Observations and transactions may be 0 so the same harness can later support missing-data and completeness experiments.

### Output controls

```text
--bulk
--per-encounter
--out-dir PATH
```

`--bulk` is the normal performance-oriented mode. One output file is produced per HL7 message family.

`--per-encounter` preserves one-file-per-encounter/message-type behavior for inspection and debugging.

### Feature controls

```text
--no-labs
--no-vitals
--no-gender-harmony
--verbose
--no-progress
```

Default batch behavior keeps labs, vitals, and Gender Harmony enabled while suppressing routine INFO logging and showing a progress bar.

---

## SDOH / Network Behavior

The batch path intentionally does **not** call:

- AirNow
- Census ACS
- CDC PLACES
- BLS

The legacy SDOH implementation remains in the repository for the existing pipeline, but the batch path does not use those external enrichment calls.

For components that historically depended on SDOH-derived values:

- vitals use the existing fallback assumptions: `poverty=0.0`, `AQI=50.0`
- lab generation uses the same local fallback inputs

This keeps batch generation deterministic and network-independent while preserving the existing local prediction mechanics.

---

## Gender Harmony Behavior

Gender Harmony remains enabled by default.

The batch ADT includes separate observations for:

- Gender Identity
- Pronouns
- Sex Parameter for Clinical Use (SPCU)

The branch preserves the existing MediLacra selection logic, including deliberately non-1:1 combinations. The batch pipeline makes the Gender Harmony selection once per encounter, counts that exact selection for summary output, and passes the same values into the ADT builder. This avoids counting a second random draw that differs from what was actually written.

---

## Summary Statistics

Each run prints:

- entity counts
- HL7 message counts
- PID Sex distribution
- Top 5 Diagnoses
- Gender Harmony distribution
- elapsed wall-clock time
- generated entity throughput
- output path

These statistics are accumulated during generation. They do not require a second pass over the generated HL7 files.

---

## Logging and Progress

### Quiet mode

Batch mode suppresses detailed Python INFO logging by default so high-volume runs do not spend time printing per-entity and per-segment messages.

Use:

```text
--verbose
```

to restore the original detailed logging when debugging.

### Progress bar

Interactive batch runs show a Rich progress bar at the patient level. The progress bar tracks completion of the outer patient loop, so each increment represents a patient whose encounters, observations, transactions, HL7 messages, and writes have completed.

Use:

```text
--no-progress
```

to suppress the progress UI for automated or clean benchmark runs.

---

## Bulk Write Optimization

The first implementation of bulk mode opened, appended to, and closed an output file for every generated message.

At the million-entity scale this meant roughly 588,240 open/write/close cycles.

The current branch now keeps the active bulk HL7 files open for the duration of the run:

```text
open ADT
open ORU
open DFT
open ORM
open ORU_LABS

for each patient / encounter:
    generate entities
    build messages
    write to existing handles
    update counters / progress

periodically flush
close all files at end
```

Bulk handles are flushed periodically (every 1,000 patients) and again before close. This preserves visible file growth and reduces the risk of holding a large amount of unwritten buffered output while avoiding hundreds of thousands of repeated file-open operations.

`--per-encounter` mode is unchanged.

**Status:** implementation committed; fresh performance validation pending.

---

# Test Runs

## 1. Smoke Test

Command shape:

```text
10 patients × 2 encounters × 3 observations × 2 transactions
```

Result:

```text
Generated:
  patients:     10
  encounters:   20
  observations: 60
  transactions: 40

Messages:
  ADT:          20
  ORU:          20
  DFT:          20
  ORM labs:     20
  ORU labs:     20

Performance:
  elapsed:      0.676s
  entity rate:  192/s
```

Manual inspection confirmed that the files were generated successfully and looked structurally correct.

The smoke output also confirmed that:

- patient and encounter identifiers propagated across message families
- Gender Harmony content was present
- labs and vitals were generated
- the batch path did not visibly invoke the removed external SDOH API workflow

---

## 2. 1,000 × 2 × 5 × 2 Benchmark

Command:

```bash
python -m hl7_demo.batch_cli --patients 1000 --encounters-per-patient 2 --observations-per-encounter 5 --transactions-per-encounter 2 --seed 42 --bulk --out-dir ./output/benchmark_1000x2x5x2
```

Result from the initial benchmark:

```text
Generated:
  patients:     1,000
  encounters:   2,000
  observations: 10,000
  transactions: 4,000

Messages:
  ADT:          2,000
  ORU:          2,000
  DFT:          2,000
  ORM labs:     2,000
  ORU labs:     2,000

Performance:
  elapsed:      77.499s
  entity rate:  219/s
```

A later 1,000-patient run with the distribution summary enabled produced:

```text
PID Sex Distribution:
  F: 505 (50.5%)
  M: 495 (49.5%)

Top 5 Diagnoses:
  R51 - Headache: 992
  M25.511 - Pain in right shoulder: 530
  N20.0 - Calculus of kidney (kidney stone): 519
  R10.9 - Unspecified abdominal pai: 516
  R10.2 - Pelvic and perineal pain: 512

Gender Harmony Distribution:
  Gender Identity:
    Female: 989 (49.5%)
    Male: 945 (47.2%)
    Non-binary gender: 37 (1.8%)
    Intersex: 29 (1.5%)

  Pronouns:
    she/her/her/hers/herself: 996 (49.8%)
    he/him/his/his/himself: 946 (47.3%)
    they/them/their/theirs/themselves: 58 (2.9%)

  SPCU:
    Apply female-typical settings: 995 (49.8%)
    Apply male-typical settings: 950 (47.5%)
    Specific (organ/system-specific): 55 (2.8%)

Performance:
  elapsed:      188.651s
  entity rate:  90/s
```

That later timing should not be treated as a clean regression comparison because it was captured during an intermediate code/logging state. The run is retained here as provenance for the distribution output.

One data-quality item observed during this run: `Unspecified abdominal pai` appears truncated in the source description. This is noted for later cleanup and is not a batch-engine blocker.

---

## 3. Million-Entity Benchmark

To preserve the same entity proportions as the 1,000 × 2 × 5 × 2 benchmark, the million-scale run used:

```text
Patients:        58,824
Encounters:     117,648
Observations:   588,240
Transactions:   235,296
Total:         1,000,008 entities
```

Command:

```bash
python -m hl7_demo.batch_cli --patients 58824 --encounters-per-patient 2 --observations-per-encounter 5 --transactions-per-encounter 2 --seed 42 --bulk --out-dir ./output/benchmark_1m
```

Result:

```text
Generated:
  patients:     58,824
  encounters:   117,648
  observations: 588,240
  transactions: 235,296

Messages:
  ADT:          117,648
  ORU:          117,648
  DFT:          117,648
  ORM labs:     117,648
  ORU labs:     117,648

PID Sex Distribution:
  F: 29,188 (49.6%)
  M: 29,636 (50.4%)

Top 5 Diagnoses:
  R51 - Headache: 58,779
  Z46.59 - Encounter for fitting and adjustment of other specified device: 29,735
  N20.0 - Calculus of kidney (kidney stone): 29,595
  R07.9 - Chest pain, unspecified: 29,569
  R31.9 - Hematuria, unspecified: 29,524

Gender Harmony Distribution:
  Gender Identity:
    Male: 57,363 (48.8%)
    Female: 56,377 (47.9%)
    Intersex: 1,991 (1.7%)
    Non-binary gender: 1,917 (1.6%)

  Pronouns:
    he/him/his/his/himself: 57,866 (49.2%)
    she/her/her/hers/herself: 56,913 (48.4%)
    they/them/their/theirs/themselves: 2,869 (2.4%)

  SPCU:
    Apply male-typical settings: 57,844 (49.2%)
    Apply female-typical settings: 56,881 (48.3%)
    Specific (organ/system-specific): 2,923 (2.5%)

Performance:
  elapsed:      6867.619s
  entity rate:  146/s
```

The run completed successfully.

Total HL7 messages generated:

```text
117,648 × 5 = 588,240 messages
```

Total wall-clock time was approximately 1 hour 54 minutes.

This run was completed before the persistent bulk-file-handle optimization was added, making it the baseline for measuring that optimization.

---

## Scikit-learn Version Warning

The million-entity run emitted warnings because locally persisted estimators were created under scikit-learn 1.7.1 and loaded under 1.7.2:

```text
InconsistentVersionWarning: Trying to unpickle estimator LinearRegression
from version 1.7.1 when using version 1.7.2
```

and similarly for `MultiOutputRegressor`.

The warnings did not stop the generation run, but the environment/model version mismatch should be cleaned up later for reproducibility.

---

# Current Validation State

Confirmed:

- configurable Patient / Encounter / Observation / Transaction cardinalities
- deterministic seeding support
- bulk HL7 generation
- ADT / ORU / DFT / ORM / ORU_LABS output
- network-independent batch SDOH behavior
- vitals generation
- Gender Harmony generation
- PID sex summary
- diagnosis frequency summary
- Gender Harmony summary
- million-entity generation on a local workstation
- routine batch logging suppression
- progress-bar implementation
- reusable CLI test suite documented in `BATCH_TEST_SCENARIOS.md`

Implemented but awaiting a fresh run:

- persistent bulk file handles
- periodic bulk flush behavior
- performance impact of the bulk-write optimization
- progress-bar behavior during a new benchmark after the latest bulk writer change

---

# Recommended Next Test

After pulling the latest branch, run the same 1,000 × 2 × 5 × 2 shape into a fresh output directory:

```bash
python -m hl7_demo.batch_cli --patients 1000 --encounters-per-patient 2 --observations-per-encounter 5 --transactions-per-encounter 2 --seed 42 --bulk --out-dir ./output/bulk_write_test
```

Validate:

1. Progress bar advances normally.
2. Five bulk files are created and contain valid HL7.
3. Final counts and distributions are correct.
4. Runtime is compared with the earlier 77.499-second benchmark.
5. Output files visibly grow during the run after periodic flushes.

If this passes, the branch has a clean before/after baseline for the bulk-write optimization and is ready for another million-entity benchmark if desired.

---

# Decision Log

## 2026-08-17 — Create a separate batch-generation path

**Decision:** Add experiment-style batch generation beside the existing MediLacra pipeline rather than refactoring the legacy path in place.

**Reason:** Preserve existing behavior while creating a fast, disposable test harness with explicit cardinality controls.

## 2026-08-17 — Remove external SDOH API dependency from batch execution

**Decision:** Batch mode does not call AirNow, Census ACS, PLACES, or BLS. Local fallback inputs are used for vitals and labs.

**Reason:** High-volume synthetic data generation should be deterministic, network-independent, and not bottlenecked by enrichment APIs.

## 2026-08-17 — Preserve Gender Harmony complexity

**Decision:** Keep Gender Identity, Pronouns, and SPCU enabled by default and preserve deliberately non-1:1 combinations.

**Reason:** These distinctions are useful semantic test material and should not be normalized away just to simplify generation.

## 2026-08-17 — Treat one million linked entities as a meaningful scale benchmark

**Decision:** Use the 1:2:10:4 Patient / Encounter / Observation / Transaction ratio and target approximately one million total entities.

**Reason:** This mirrors the scale-testing style used in the earlier structured-sparsity experiment while exercising a much richer healthcare representation.

## 2026-08-17 — Suppress routine logging and add human-visible progress

**Decision:** Batch mode is quiet by default, with `--verbose` for debugging and a patient-level Rich progress bar for interactive runs.

**Reason:** Per-record INFO logging distorted performance and made large runs unreadable; complete silence made long runs hard to trust operationally.

## 2026-08-17 — Keep bulk output files open during generation

**Decision:** Replace per-message open/append/close cycles with persistent handles and periodic flushes in bulk mode.

**Reason:** The first million-entity run produced 588,240 HL7 messages, making repeated file-open operations an obvious mechanical source of avoidable overhead.

## 2026-08-19 — Rename the working project/folder to `medilacra_data_dumper`

**Decision:** Use `medilacra_data_dumper` as the local repository folder and **MediLacra Data Dumper** as the working name for this branch effort. Leave the upstream `natosit-dev/medilacra` repository, branch name, Python modules, CLI entry point, and functional behavior unchanged.

**Reason:** “Batch generation” described an implementation detail but not the root primitive. “Data Dumper” says what the thing actually does: generate synthetic healthcare reality at configurable scale and dump linked representations for downstream systems, tests, and experiments. Names are part of the interface; the clearer name makes the purpose legible without explanation.

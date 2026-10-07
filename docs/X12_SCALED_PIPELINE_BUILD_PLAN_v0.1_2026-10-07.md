# Scaled X12 Eligibility Output — Build Plan

**Version:** 0.1  
**Date:** 2026-10-07  
**Branch:** `experiment/employer-coverage`  
**Status:** Implemented / validated  
**Pre-build head:** `2932907727f9a15dc85f6f31d3e68f036bcb06a0`

---

# 1. Purpose

Promote X12 270/271 eligibility generation from a single-exchange UI/demo path into a first-class optional output of MediLacra's normal `run_pipeline()` generation process.

The scaled path must preserve the architectural boundary already established:

```text
Clinical Reality                     Payer Reality
----------------                     -------------
Patient                              MemberRecord
CoverageProfile                      EnrollmentRecord
Encounter                            BenefitPlan
      |                                   |
      |                                   |
      +-------- X12 270 inquiry --------->|
                                          |
                                 payer evaluation
                                          |
      |<------- X12 271 response ---------+
```

The general pipeline coordinates the work, but X12 semantics remain outside `pipeline.py`.

The first workload remains deliberately simple:

- subscriber is patient;
- one coverage record;
- ACTIVE eligibility response;
- one 270/271 pair per encounter;
- generic service type 30;
- no identity-error injection;
- no dependent/family modeling;
- no raw X12 persistence yet.

---

# 2. Prompt History / Design Lineage

The build is the result of the following prompt sequence.

> "I'm thinking we should keep the synthetic clinical and payer realities separate. This is a big deal/change and I want to get the primitives right"

This established clinical and payer institutional state as independent materializations of hidden synthetic truth.

> "Put together a build plan. Don't overbuild but let's make clear boundaries."

This constrained the payer foundation to a small explicit institutional boundary.

> "Go build the MVP after you put this in a build design doc in the branch"

This produced the hidden truth, payer state, identity matching, and semantic eligibility engine.

> "Looks good enough, go build it"

This authorized the first two X12 270/271 scenarios.

> "No, next scenario is adding a page where I can test it in the UI and download the X12 messages. Show me a MVP design plan for the new page"

This shifted the next validation step from negative eligibility scenarios to a manual Streamlit test harness.

> "File names should have datetime stamp. Rest looks good, go build it"

This established datetime-stamped X12 download artifacts.

The resulting 270 and 271 were then loaded into an InterSystems IRIS X12 production, where IRIS recognized them as `HIPAA_5010:270` and `HIPAA_5010:271`.

> "Patient matching isn't a priority. Generating the messages at scale is. How do we move from this single example to adding it as an output to the general Medilacra generative process?"

This changed priority from identity-resolution experiments to workload generation.

> "Yeah, should be part of run_pipeline, change the delimiter on the transform to ^, for control numbers use timestamp plus incrementing numbers at the end, agree with keeping it out of pipeline.py.
>
> We should be writing the payer/coverage primitives to duckdb. Don't need a separate X12 field this round, but we'll do that next.
>
> Show me a full build plan"

This set the implementation constraints for the scaled build.

> "K, write that as a build plan to docs in the repo. Include my prompt history. Then go build it"

This document is the durable pre-build checkpoint.

---

# 3. Target Pipeline

The normal generation path becomes:

```text
Patient
  |
CoverageProfile
  |
Encounter
  |
  +-------------------------------+
  |                               |
  v                               v
Clinical projections        Payer materialization
ADT / ORU / DFT / ORM       MemberRecord
                            EnrollmentRecord
                            BenefitPlan
                                  |
                                  v
                               X12 270
                                  |
                                  v
                              PayerSystem
                                  |
                                  v
                               X12 271
```

For this build:

```text
1 encounter = 1 X12 270 + 1 X12 271
```

The requested eligibility date comes from the encounter admission date, not wall-clock generation time.

---

# 4. New General X12 Generation Boundary

Add:

```text
x12/generation.py
```

This module owns scaled X12 orchestration.

The existing:

```text
x12/scenarios.py
```

remains a UI/demo harness and must not become a dependency of the normal pipeline.

Primary responsibilities of `x12/generation.py`:

- run-scoped control-number sequencing;
- requester/payer exchange configuration;
- construction of one 270;
- parsing 270 to `EligibilityInquiry`;
- payer evaluation;
- construction of one 271;
- envelope wrapping;
- X12 file writing helpers;
- return of representation-neutral artifact metadata to `run_pipeline()`.

Target artifact:

```text
X12EligibilityArtifacts
    encounter_id
    payer_id
    member_id
    service_date
    trace_id
    request_transaction_control
    response_transaction_control
    request_interchange_control
    response_interchange_control
    x270
    x271
```

`pipeline.py` should not contain X12 segment names or X12 decision logic.

---

# 5. Clinical Name Transform

Current general MediLacra generation stores:

```text
LAST, FIRST
```

The demo fixture used:

```text
LAST^FIRST
```

The X12 transform should normalize the generated clinical representation to:

```text
LAST^FIRST
```

at the projection boundary before extracting components.

The transform should accept both current forms during transition:

```text
LAST, FIRST
LAST^FIRST
```

but normalize internally to caret-delimited form.

Example:

```text
SMITH, JANE
      |
      v
SMITH^JANE
      |
      +--> last_name = SMITH
      '--> first_name = JANE
```

The canonical `Patient.patient_name` representation is not changed.

---

# 6. Run-Scoped Control Numbers

Timestamp-only controls are insufficient at scale because multiple messages are generated in the same second.

Add:

```text
X12RunContext
    run_at
    exchange_sequence
    control_sequence
```

Every 270/271 pair increments one exchange sequence.

Every X12 message increments one control sequence.

Human-readable trace/reference values use the full run timestamp plus incrementing exchange number:

```text
TRACE-270-20261007114512-00001
ELIG-REQ-20261007114512-00001
```

Constrained X12 control-number fields use a timestamp fragment plus incrementing control sequence while remaining within the 9-digit envelope/control constraint.

Target shape:

```text
HHMM + 5-digit control sequence
```

Example:

```text
run time = 11:45

270:
ST/ISA control = 114500001

271:
ST/ISA control = 114500002

next 270:
ST/ISA control = 114500003

next 271:
ST/ISA control = 114500004
```

The invariant is:

- timestamp prefix;
- monotonically increasing numeric suffix;
- no collisions in a run;
- 270/271 ordering is obvious;
- capacity comfortably exceeds the current 10,000-patient UI limit.

---

# 7. General Payer Materialization

The normal pipeline must not construct `PersonTruth`, `CoverageTruth`, or `GroundTruthLink` directly.

Extend the payer materialization boundary with a helper such as:

```text
materialize_payer_from_clinical(
    patient,
    coverage_profile,
)
```

Internally it may use the existing hidden-truth materialization primitives.

It returns payer-local:

```text
MemberRecord
EnrollmentRecord
BenefitPlan
```

Normal generation creates aligned but independent payer state.

It does not inject the UI divergence scenario or other matching defects.

---

# 8. Run-Scoped Payer Registry

When X12 is enabled, initialize one in-memory registry per run:

```text
payer_systems = {}
```

As each generated patient is assigned coverage:

```text
coverage.payer_id
      |
      v
find/create PayerSystem
      |
      +--> add MemberRecord
      +--> add EnrollmentRecord
      '--> add BenefitPlan
```

This means a scaled run builds a synthetic payer population rather than creating one unrelated toy payer per UI click.

The registry exists only for the run in this phase.

DuckDB persistence captures payer primitives separately.

---

# 9. DuckDB Payer/Coverage Persistence

Existing clinical-side coverage remains:

```text
coverage_profiles
```

Add payer-side tables:

## `payer_members`

```text
member_record_id PRIMARY KEY
payer_id
member_id
first_name
last_name
date_of_birth
administrative_sex
created_ts
```

Indexes:

```text
payer_id
(payer_id, member_id)
```

## `payer_enrollments`

```text
enrollment_id PRIMARY KEY
member_record_id
payer_id
plan_id
group_number
effective_start
effective_end
status
created_ts
```

Indexes:

```text
member_record_id
payer_id
plan_id
```

## `payer_plans`

```text
payer_id
plan_id
plan_name
plan_type
created_ts
PRIMARY KEY (payer_id, plan_id)
```

The same synthetic plan archetype may exist under multiple payer namespaces.

Add:

```text
upsert_payer_member()
upsert_payer_enrollment()
upsert_payer_plan()
```

to `storage_duckdb_entities.py`.

Do not persist `GroundTruthLink` in this phase.

Do not persist raw X12 payloads in the existing `messages.raw_hl7` column.

A representation-neutral artifact table is explicitly deferred to the next storage design.

---

# 10. `run_pipeline()` API

Add:

```python
include_x12: bool = False
```

Default remains `False` for backwards compatibility.

Counts expand to:

```python
{
    "ADT": 0,
    "ORU": 0,
    "DFT": 0,
    "ORM": 0,
    "ORU_LABS": 0,
    "X12_270": 0,
    "X12_271": 0,
}
```

No X12-specific standards configuration is exposed in `run_pipeline()` yet.

---

# 11. Pipeline Initialization

When `include_x12=True`, initialize before the patient loop:

```text
X12RunContext
payer_systems
```

The same `run_ts` used for normal output filenames anchors X12 run metadata.

The pipeline remains the orchestrator only.

---

# 12. Per-Encounter X12 Generation

After:

```text
Patient
CoverageProfile
Encounter
```

exist, the pipeline calls payer materialization and the X12 generation boundary.

Eligibility service date:

```text
Encounter.admit_datetime
      |
      v
YYYY-MM-DD
      |
      v
DTP*291
```

The X12 branch must not depend on Transaction or Observation to produce the eligibility pair.

---

# 13. Persistence Ordering

For `persist="duckdb"`, persist instantiated clinical and payer state before writing output files:

```text
Patient
CoverageProfile
Encounter
Transaction
Observation

MemberRecord
EnrollmentRecord
BenefitPlan
```

This preserves the generated institutional state for debugging even if a later file write fails.

---

# 14. Filesystem Output

## Bulk mode

Write datetime-stamped files:

```text
X12_270_YYYYMMDD_HHMMSS.x12
X12_271_YYYYMMDD_HHMMSS.x12
```

Each record is a complete X12 interchange:

```text
ISA ... IEA

ISA ... IEA

ISA ... IEA
```

Do not build a shared ISA/GS envelope containing many ST/SE transaction sets in this phase.

That is a separate batching experiment.

## Per-encounter mode

Write:

```text
X12_270_<encounter>_YYYYMMDD_HHMMSS.x12
X12_271_<encounter>_YYYYMMDD_HHMMSS.x12
```

All X12 output files retain datetime stamps.

---

# 15. X12 Writer Boundary

File-writing helpers may live in `x12/generation.py`.

`pipeline.py` supplies:

- output directory;
- run timestamp;
- per-encounter versus bulk mode;
- generated X12 artifact pair.

The X12 module owns:

- X12 filenames;
- X12 extensions;
- pair writing/appending.

This prevents X12-specific file handling from spreading across the clinical pipeline.

---

# 16. Main Streamlit Integration

Add to the main MediLacra generation surface:

```text
Include X12 Eligibility (270/271)
```

Default off.

Pass through to:

```text
run_pipeline(include_x12=...)
```

Completion summary includes:

```text
X12_270
X12_271
```

Recent-file display must include both:

```text
*.hl7
*.x12
```

The dedicated X12 Eligibility page remains the single-exchange inspection harness.

The main page becomes the workload-generation surface.

---

# 17. Generate & Persist Page

The existing `pages/2_Generate_and_Persist.py` currently calls the older `pipeline_duckdb.run_and_persist` implementation.

For this build, move that page onto the primary:

```text
hl7_demo.pipeline.run_pipeline
```

with:

```text
persist="duckdb"
```

This avoids implementing the scaled X12 path twice.

Add:

```text
Include X12 Eligibility (270/271)
```

and preview the new payer tables.

The legacy `pipeline_duckdb.py` remains for compatibility/tests but does not become a second X12 implementation.

---

# 18. CLI Integration

Add:

```text
--include-x12
```

to the `hl7_demo.pipeline` CLI.

No other X12 configuration flags are needed yet.

---

# 19. Raw X12 Persistence — Explicitly Deferred

Do not place X12 into:

```text
messages.raw_hl7
```

Do not add an `x12_raw` column as a one-off workaround.

The next storage phase should define a representation-neutral artifact/message table suitable for:

```text
HL7 v2
FHIR
X12
other generated artifacts
```

This build stores payer/coverage primitives, not raw X12 payloads.

---

# 20. Tests

Add focused tests for:

## Name transform

- generated `LAST, FIRST` normalizes to `LAST^FIRST`;
- existing demo `LAST^FIRST` still works;
- X12 name components are correct.

## Run controls

Generate at least 1,000 exchange pairs from one `X12RunContext`.

Assert:

- 2,000 unique message control numbers;
- suffixes increase monotonically;
- all controls contain the same run-time timestamp prefix;
- no collision.

## Payer materialization

Assert:

- generated clinical patient materializes independent payer state;
- payer objects have no clinical foreign keys;
- names/member IDs/coverage dates align in the normal generation path.

## DuckDB persistence

Assert:

- `payer_members`, `payer_enrollments`, and `payer_plans` exist;
- round-trip values are correct;
- repeated plan upsert is idempotent;
- coverage profile remains clinical-side;
- payer member/enrollment linkage is correct.

## Pipeline integration

With `include_x12=True`:

- one generated encounter => one 270 + one 271;
- service date equals encounter admit date;
- counts include X12 outputs;
- bulk filenames are datetime stamped;
- per-encounter filenames are datetime stamped;
- X12 payloads are not added to `messages.raw_hl7`;
- payer primitives persist when DuckDB is enabled.

With `include_x12=False`:

- existing generation behavior remains unchanged.

---

# 21. CI and Scale Validation

Keep CI fast with a modest pipeline generation count.

Add a standalone local scale harness:

```text
scripts/demo_x12_scale.py
```

CLI:

```bash
python scripts/demo_x12_scale.py --n 1000
```

Target output:

```text
Patients:              1000
Payer members:         1000
Payer enrollments:     1000
X12 270 generated:     1000
X12 271 generated:     1000
Control collisions:       0
Elapsed seconds:         ...
```

The scale harness should call the normal `run_pipeline()`; it must not implement a separate generation engine.

---

# 22. External Acceptance Test

After automated validation:

```text
run_pipeline(
    n_patients=1000,
    include_x12=True,
    persist="duckdb",
)
```

should produce:

```text
X12_270_<timestamp>.x12
X12_271_<timestamp>.x12
```

containing 1,000 complete interchanges each.

Load those files into the existing IRIS X12 production.

Target acceptance:

```text
1,000 recognized HIPAA_5010:270 transactions
1,000 recognized HIPAA_5010:271 transactions
0 structural parse failures
```

If IRIS requires a different file-ingestion grain, change only the X12 writer behavior after observing that requirement.

Do not prematurely redesign the transaction-generation layer.

---

# 23. Explicit Non-Goals

Not part of this build:

- patient-matching experiments;
- clinical/payer identity divergence in normal generation;
- NOT_FOUND responses;
- INACTIVE 271 projection;
- AAA;
- dependent/family coverage;
- financial benefit detail;
- deductibles/copays/coinsurance;
- accumulators;
- raw X12 DuckDB persistence;
- generalized artifact table;
- multi-ST shared interchange batching;
- clearinghouse behavior;
- 278;
- 837;
- 835.

---

# 24. Implementation Order

1. Commit this build plan.
2. Normalize the clinical-name transform to caret-delimited internal form.
3. Add `X12RunContext` with timestamp + incrementing controls.
4. Add general payer materialization from generated clinical state.
5. Add `x12/generation.py`.
6. Add payer DuckDB tables and upsert functions.
7. Wire optional X12 output into `run_pipeline()`.
8. Add bulk/per-encounter X12 file writing.
9. Add X12 counts.
10. Add main Streamlit toggle and X12 recent-file display.
11. Move Generate & Persist page onto primary `run_pipeline()`; add X12 toggle/payer table previews.
12. Add CLI `--include-x12`.
13. Add focused unit/integration/persistence/control tests.
14. Add `scripts/demo_x12_scale.py`.
15. Run focused CI.
16. Run full repository regression.
17. Run scaled generation.
18. Record the build outcome in this document.

---

# 25. Definition of Done

The build is complete when the primary pipeline can execute:

```python
run_pipeline(
    n_patients=1000,
    ...,
    include_x12=True,
    persist="duckdb",
)
```

and materialize:

```text
1000 Patients
1000 CoverageProfiles
1000 payer MemberRecords
1000 payer EnrollmentRecords

1000 X12 270 interchanges
1000 X12 271 interchanges
```

with:

- encounter-date eligibility inquiries;
- timestamp + incrementing control numbers;
- no control collisions;
- datetime-stamped X12 output filenames;
- payer primitives persisted in DuckDB;
- existing clinical coverage persisted in DuckDB;
- no raw X12 written into `raw_hl7`;
- no X12 segment logic embedded in `pipeline.py`;
- existing non-X12 generation still working;
- focused tests green;
- full regression green.

The external acceptance test is that IRIS consumes the generated 270/271 workload at scale.


---

# 26. Implementation Outcome

Implemented on `experiment/employer-coverage`.

## General X12 generation boundary

Created:

```text
x12/generation.py
```

Added:

```text
X12RunContext
X12ControlSet
X12EligibilityArtifacts
generate_eligibility_exchange()
write_x12_artifacts()
```

The normal pipeline calls this boundary without learning X12 segment semantics.

## Name transform

The X12 clinical-name transform now accepts both:

```text
LAST, FIRST
LAST^FIRST
```

and normalizes internally to:

```text
LAST^FIRST
```

before X12 component extraction.

The canonical MediLacra `Patient.patient_name` representation was not changed.

## Control numbering

Scaled X12 generation now uses one run-scoped allocator.

Human-readable exchange IDs use:

```text
TRACE-270-YYYYMMDDHHMMSS-NNNNN
ELIG-REQ-YYYYMMDDHHMMSS-NNNNN
```

X12 constrained control fields use:

```text
HHMM + five-digit monotonic message sequence
```

Example:

```text
270 -> 114500001
271 -> 114500002
next 270 -> 114500003
next 271 -> 114500004
```

The control allocator was tested across 1,000 exchange pairs / 2,000 messages with no collisions.

## General payer materialization

Added:

```text
materialize_payer_from_clinical()
```

to `payer/materialize.py`.

`run_pipeline()` does not construct hidden truth/oracle primitives directly.

The helper converts generated clinical-side state into independent payer-local:

```text
MemberRecord
EnrollmentRecord
BenefitPlan
```

Normal generation does not inject identity divergence.

## `run_pipeline()` integration

Added:

```python
include_x12: bool = False
```

When enabled, the primary pipeline now:

```text
generates Patient / CoverageProfile / Encounter
        |
        v
materializes payer-local state
        |
        v
adds state to run-scoped PayerSystem registry
        |
        v
generates 270 using encounter admission date
        |
        v
payer evaluates parsed inquiry
        |
        v
generates 271
        |
        v
writes X12 files
```

Counts expose:

```text
X12_270
X12_271
```

only when X12 output is enabled, preserving the previous return shape for existing callers with `include_x12=False`.

## File outputs

Bulk mode:

```text
X12_270_YYYYMMDD_HHMMSS.x12
X12_271_YYYYMMDD_HHMMSS.x12
```

Each bulk file contains sequential complete `ISA..IEA` interchanges.

Per-encounter mode:

```text
X12_270_<encounter>_YYYYMMDD_HHMMSS.x12
X12_271_<encounter>_YYYYMMDD_HHMMSS.x12
```

No shared multi-transaction interchange batching was introduced.

## DuckDB payer state

Added tables:

```text
payer_members
payer_enrollments
payer_plans
```

Added storage functions:

```text
upsert_payer_member()
upsert_payer_enrollment()
upsert_payer_plan()
```

Existing:

```text
coverage_profiles
```

continues to represent clinical-side coverage knowledge.

Payer plan persistence uses the composite identity:

```text
(payer_id, plan_id)
```

and repeated plan upserts are idempotent.

## Raw X12 persistence boundary

Raw X12 payloads are **not** written to:

```text
messages.raw_hl7
```

The integration test explicitly confirms the existing message log remains HL7-only.

A representation-neutral artifact table remains deferred to the next storage phase.

## UI / CLI surfaces

The main Streamlit generator now exposes:

```text
Include X12 Eligibility (270/271)
```

and lists both `.hl7` and `.x12` output files.

`pages/2_Generate_and_Persist.py` now uses the primary:

```text
hl7_demo.pipeline.run_pipeline
```

instead of implementing another X12 path through the legacy DuckDB pipeline.

It exposes the X12 toggle and payer table previews.

CLI support:

```text
--include-x12
```

## Scale harness

Created:

```text
scripts/demo_x12_scale.py
```

Usage:

```bash
python scripts/demo_x12_scale.py --n 1000
```

It calls the normal `run_pipeline()`, creates a fresh timestamped output directory and DuckDB, and validates:

- patient count;
- payer member count;
- payer enrollment count;
- generated 270 count;
- generated 271 count;
- control-number collisions.

A temporary CI attempt to run the full unmocked generation path was intentionally removed from permanent branch checks because the existing ADT generation path performs network-dependent SDOH enrichment. Scaled X12 semantics and controls are covered in deterministic tests; the 1,000-record full-pipeline run remains the local/IRIS acceptance test.

## Tests added

```text
tests/test_x12_scaled_generation.py
tests/test_payer_storage.py
tests/test_x12_pipeline_integration.py
tests/test_x12_pipeline_ui_wiring.py
```

Coverage includes:

- comma-to-caret name normalization;
- compatibility with existing caret fixtures;
- 1,000 exchange pairs / 2,000 unique monotonic controls;
- generated clinical -> independent payer materialization;
- encounter admission date -> 270 requested service date;
- bulk and per-encounter datetime-stamped X12 filenames;
- payer DuckDB schema and round-trip;
- idempotent payer-plan persistence;
- primary `run_pipeline()` X12 generation;
- payer/coverage linkage;
- no X12 payloads in `raw_hl7`;
- X12-disabled backwards compatibility;
- main Streamlit wiring;
- Generate & Persist primary-pipeline wiring.

## Automated validation

Final code-bearing CI run:

```text
Focused branch suite:
89 passed

Full repository regression:
102 passed
```

Successful workflow:

```text
https://github.com/natosit-dev/medilacra/actions/runs/37620159856
```

No test failures were reported.

---

# 27. Current Architecture

```text
run_pipeline()
     |
     +------------------------- clinical outputs
     |                             |
     |                             +-- ADT
     |                             +-- ORU
     |                             +-- DFT
     |                             +-- ORM
     |
     +--> payer materialization
             |
             +--> DuckDB payer state
             |
             +--> x12/generation.py
                       |
                       +--> X12 270
                       |
                       +--> PayerSystem
                       |
                       '--> X12 271
```

`pipeline.py` coordinates the branch but contains no X12 segment construction.

---

# 28. Remaining Acceptance Test

The implementation is ready for the intended scale test:

```bash
python scripts/demo_x12_scale.py --n 1000
```

Then feed the generated bulk files into IRIS:

```text
X12_270_<timestamp>.x12
X12_271_<timestamp>.x12
```

Target:

```text
1,000 recognized HIPAA_5010:270 transactions
1,000 recognized HIPAA_5010:271 transactions
0 structural parse failures
```

That is the remaining external acceptance step, not an architecture/code prerequisite.

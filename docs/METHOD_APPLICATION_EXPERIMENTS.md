# MediLacra Method Application Experiments

## Project Plan and First-Round Implementation Record

## Purpose

This experiment set isolates a reusable engineering method and demonstrates it against fully synthetic healthcare data.

The method is:

1. inspect available artifacts as evidence;
2. infer the actual technical or operational model;
3. materialize that model explicitly;
4. validate the materialized model against available evidence;
5. correct assumptions when evidence contradicts them;
6. operationalize the result;
7. document the result so another person can understand, reproduce, and extend it.

The goal is not to reproduce any prior production system. The goal is to show that the method survives when all source-specific implementation details are removed and the problem is recreated from first principles using MediLacra synthetic data.

MediLacra already supplies the necessary substrate: synthetic patients, encounters, observations, transactions, HL7 v2 messages, DuckDB persistence, scenario profiles, and Streamlit interfaces. These experiments reuse those seams instead of creating a second synthetic healthcare platform.

---

## Core Design Principle

The experiments reconstruct problem classes, not source systems.

The transformation boundary is:

```text
prior experience with a problem class
        ↓
general engineering lesson
        ↓
new synthetic problem in MediLacra
        ↓
new implementation
        ↓
new evidence
```

It is explicitly not:

```text
old implementation
        ↓
rename tables / fields
        ↓
new implementation
```

This distinction is important. A useful abstraction should remain valid when the original schemas, code, names, systems, organizations, and operating context are gone.

---

## Scope

The first round contains four experiments:

- **Method A — Heterogeneous HL7 Conformance**
- **Method B — Workflow Reconstruction**
- **Method C — Workflow Validation and Correction**
- **Method D — Workflow Operationalization**

A fifth experiment involving encounter classification under uncertainty is intentionally deferred. It is not part of this first round.

---

## Branch Topology

The branches are intentionally not all independent.

Method A tests a separate technical problem and branches directly from `main`.

Methods B, C, and D form a dependency chain because C validates the reconstructed model created by B, and D operationalizes the outputs of B and C.

```text
main
 |
 +-- experiment/method-a-hl7-conformance
 |
 +-- experiment/method-b-workflow-reconstruction
           |
           +-- experiment/method-c-workflow-validation
                      |
                      +-- experiment/method-d-workflow-operations
```

This avoids duplicating synthetic workflow fixtures across branches and prevents independent copies of the same synthetic model from drifting apart.

Current branch history was checked after implementation. C is directly ahead of B, and D is directly ahead of C.

---

# Design Constraints

## 1. Synthetic data only

All experiment inputs must be synthetic or public.

Do not introduce:

- real patient data;
- production extracts;
- proprietary schemas;
- internal system names;
- organization-specific workflow names;
- client configuration;
- credentials;
- private URLs;
- ticket identifiers;
- copied production code;
- copied production mappings.

The repository should remain safe to inspect and share as a synthetic engineering laboratory.

## 2. Primitive before sophisticated

The first implementation should be smaller than any mature production version of the same idea.

Examples:

- three source representations instead of many feeds;
- a few canonical fields instead of a full enterprise semantic model;
- three workflows instead of a large workflow catalog;
- roughly ten validation checks instead of a broad control framework;
- one thin Streamlit interface instead of a large application;
- local Python, files, and DuckDB instead of distributed infrastructure.

Complexity should be earned by a demonstrated need.

## 3. Preserve evidence before interpretation

Whenever possible, the original synthetic representation should survive downstream transformation.

Canonical data should not erase the raw evidence that produced it.

## 4. Interpretation and validation are separate

A reconstructed model is a hypothesis about the available evidence.

Validation should be allowed to prove that:

- the model is correct;
- the model is wrong;
- the documentation is wrong;
- the source data is incomplete;
- the validation method cannot answer the question.

A difference is not automatically a defect.

## 5. User interfaces should not become hidden semantic layers

Operational interfaces should read the materialized model and validation outputs rather than inventing separate business logic.

The interface is a view of the model, not a second model.

## 6. Reuse before framework-building

The experiments share a conceptual structure, but no new general-purpose experiment framework is created in round one.

Repeated infrastructure should only be extracted after repetition is observed in working experiments.

---

# Method A — Heterogeneous HL7 Conformance

**Branch:** `experiment/method-a-hl7-conformance`

## Question

Can several heterogeneous representations of the same MediLacra ADT data be normalized into one inspectable canonical representation while preserving the original evidence and lineage?

## Reused MediLacra components

Method A reuses existing MediLacra functionality for:

- synthetic Patient generation;
- synthetic Encounter generation;
- HL7 MSH generation;
- HL7 EVN generation;
- HL7 PID generation;
- HL7 PV1 generation.

It does not create a second patient generator or a second HL7 implementation.

## Synthetic source variation

The experiment creates the same underlying synthetic ADT events once, then stores them through three deliberately different source surfaces.

The sources use different file/storage formats and different metadata field names.

Conceptually:

```text
synthetic MediLacra reality
        ↓
minimal ADT messages
        ↓
+-------------------------+
| CSV source              |
| JSONL source            |
| DuckDB source           |
+-------------------------+
        ↓
source registry
        ↓
raw normalized evidence
        ↓
canonical ADT events
```

The heterogeneity is intentionally modest. The experiment is testing explicit source conformance, not simulating a large vendor ecosystem.

## Registry

A small source registry declares where each source stores:

- source record identity;
- message payload;
- receive timestamp.

This makes source-specific variation inspectable instead of embedding it throughout transformation code.

## Raw representation

The normalized raw layer preserves at least:

```text
source_name
source_record_id
raw_payload
source_timestamp
```

## Canonical representation

The first-round canonical representation is deliberately small and includes a subset of ADT semantics sufficient for reconciliation, including:

```text
source_name
source_record_id
patient_id
visit_number / encounter identity
event_type
patient_class
admit_datetime
discharge_datetime
```

The exact implementation is in:

```text
experiments/method_a_hl7_conformance/
```

## Validation intent

The MVP checks that:

- all three source representations are ingested;
- all raw source records survive normalization;
- canonical fields parse successfully;
- canonical patient identity reconciles to the MediLacra entities that generated the messages;
- canonical visit identity reconciles to the generating encounters;
- duplicate canonical event keys are not introduced;
- source lineage survives into canonical output.

## First-round files

```text
experiments/method_a_hl7_conformance/
    README.md
    run_experiment.py
    source_registry.json
```

The experiment writes generated source artifacts and result artifacts at run time rather than committing generated databases or large transient outputs.

## Explicitly deferred

Round one does not attempt to implement:

- distributed processing;
- enterprise orchestration;
- incremental watermarks;
- large mapping registries;
- distributed transaction guarantees;
- broad monitoring platforms;
- large semantic models.

Those would obscure the core conformance problem at this stage.

---

# Method B — Workflow Reconstruction

**Branch:** `experiment/method-b-workflow-reconstruction`

## Question

Can a coherent operational workflow model be recovered from fragmented synthetic artifacts that do not individually contain the whole workflow?

## Synthetic workflow ontology

The initial workflow vocabulary contains three synthetic workflow families:

```text
CARE_FOLLOWUP
MEDICATION_REVIEW
SOCIAL_SUPPORT
```

The underlying synthetic lifecycle contains four observed states:

```text
queued
active
complete
canceled
```

The input documentation is intentionally incomplete and initially describes only three states. This creates a controlled contradiction for Method C to discover.

## Fragmented artifacts

The synthetic source system is represented through several independent artifacts:

```text
tasks.json
actions.json
forms.json
appointments.csv
staff.csv
```

No single artifact contains the complete final workflow representation.

The source relationships are intentionally distributed.

One important example is closure evidence:

```text
form submission
      ↓ action_id
workflow action
      ↓ workflow_id
workflow task
```

The final workflow row therefore requires a two-hop relationship that is not directly represented in a single source artifact.

## Deliberate ambiguity and friction

The first-round fixtures contain a small number of meaningful complications:

- the initial source notes omit the `canceled` lifecycle state;
- a specialist assignment can override a generic owner for one workflow family;
- closure forms link through workflow actions rather than directly to tasks;
- appointment staff can match, differ from, or be absent relative to reconstructed workflow assignment;
- some workflows have no appointment.

The fixtures are deterministic so changes in interpretation are not confused with changes in random source generation.

## Materialized model

The reconstructed output declares a single primary grain:

> one row per workflow instance

The model contains fields for:

- workflow identity;
- patient identity;
- workflow type;
- workflow state;
- reconstructed staff assignment;
- assignment source;
- creation and due timestamps;
- derived due status;
- appointment identity;
- appointment staff;
- appointment reconciliation status;
- closure action;
- closure form;
- closure outcome;
- closure presence.

## Time semantics

Due-status derivation uses an explicit `as_of` timestamp rather than implicitly using the wall-clock time at execution.

This keeps the experiment reproducible and prevents the same fixture set from changing semantic meaning merely because it is rerun on a later date.

## Documentation artifacts

Method B includes both the initially available notes and the reconstructed model:

```text
experiments/method_b_workflow_reconstruction/
    README.md
    SOURCE_NOTES.md
    RECONSTRUCTED_MODEL.md
    generate_sources.py
    reconstruct.py
```

The distinction is intentional:

- `SOURCE_NOTES.md` represents the incomplete starting understanding;
- `RECONSTRUCTED_MODEL.md` represents the interpretation produced from the evidence.

Method C is responsible for testing that interpretation.

---

# Method C — Workflow Validation and Correction

**Branch:** `experiment/method-c-workflow-validation`

**Base:** `experiment/method-b-workflow-reconstruction`

## Question

When the reconstructed workflow model is tested against the underlying synthetic evidence, which assumptions are confirmed, which are wrong, and which questions cannot actually be answered?

## Validation model

Validation result and validation interpretation are deliberately separate concepts.

### Status

```text
PASS
FAIL
WARN
NOT_TESTABLE
INFO
```

### Interpretation

```text
EXPECTED_BEHAVIOR
PIPELINE_DEFECT
SOURCE_QUALITY
DOCUMENTATION_CORRECTION
VALIDATOR_LIMITATION
UNKNOWN
```

A `FAIL` therefore does not automatically imply a software defect.

A `NOT_TESTABLE` result is also allowed to remain unresolved when the available evidence does not support a stronger conclusion.

## First-round validation domains

The initial suite checks approximately the following areas:

```text
VAL-0   grain uniqueness
VAL-1   workflow state vocabulary
VAL-2   workflow type mapping
VAL-3   assigned staff resolution
VAL-4   appointment reconciliation
VAL-5   two-hop form linkage
VAL-6   closure consistency
VAL-7   due-status derivation
VAL-8   cross-source population reconciliation
VAL-9   critical field coverage
VAL-10  staff-at-time evidence boundary
```

The suite is intentionally small enough that each check has an understandable purpose.

## Deliberate documentation correction

The initial source notes describe only:

```text
queued
active
complete
```

The synthetic evidence includes a valid fourth state:

```text
canceled
```

The expected interpretation is therefore:

```text
status: FAIL
classification: DOCUMENTATION_CORRECTION
```

The data pipeline is not changed merely to force the evidence to agree with the original documentation.

Instead, the documentation is corrected.

## Deliberate evidence boundary

The fixtures do not contain effective-dated staff employment or role history.

Therefore, a question such as:

> Was the assigned staff member organizationally active at the exact instant the workflow was created?

cannot be proven from the available evidence.

The appropriate result is:

```text
status: NOT_TESTABLE
classification: VALIDATOR_LIMITATION
```

The experiment does not fabricate another dataset merely to eliminate uncertainty.

## Correction artifact

Method C adds:

```text
CORRECTED_SOURCE_NOTES.md
```

The original source notes remain available as provenance. The corrected notes represent the evidence-backed understanding after validation.

## First-round files

```text
experiments/method_c_workflow_validation/
    README.md
    CORRECTED_SOURCE_NOTES.md
    run_validation.py
```

Generated validation outputs are written at run time.

---

# Method D — Workflow Operationalization

**Branch:** `experiment/method-d-workflow-operations`

**Base:** `experiment/method-c-workflow-validation`

## Question

Can the reconstructed and validated workflow model become an interface that another person can inspect and use without turning the interface itself into a new source of hidden semantics?

## Implementation strategy

Method D is a thin Streamlit client over the materialized outputs of B and C.

It does not independently reconstruct workflow semantics.

Conceptually:

```text
fragmented synthetic artifacts
        ↓
Method B reconstruction
        ↓
workflow_detail
        ↓
Method C validation + correction
        ↓
validation results / corrected notes
        ↓
Method D operational interface
```

## Interface

The first-round application contains five simple surfaces.

### Operations

Shows operational workflow counts and a filterable workflow queue.

Useful initial metrics include:

- total workflows;
- open workflows;
- overdue workflows;
- appointment-assignment mismatches.

### Metrics

Table-first summaries expose:

- workflow type by state;
- workflow type by due status;
- appointment reconciliation status;
- completion/closure counts.

Charts are not required to establish the method.

### Validation

Displays the latest validation checks with:

- check identifier;
- status;
- interpretation;
- evidence.

This makes validation state part of the operational interface rather than a hidden engineering artifact.

### History

Displays validation and maintenance history when available.

### How It Works

Renders the current reconstructed model and corrected documentation so the operating interface also explains the system it is presenting.

## Explicitly deferred

Round one does not include:

- authentication;
- user management;
- production deployment;
- writeback;
- workflow mutation;
- scheduling services;
- clinical decision support;
- complex visualization;
- duplicate business logic in the UI.

The application is intentionally a reader over the model.

## First-round files

```text
experiments/method_d_workflow_operations/
    README.md
    app.py
```

---

# Common Experiment Contract

The experiments are related conceptually without being forced into a common software framework.

Each experiment should make the following legible:

1. What problem is being tested?
2. What synthetic reality exists?
3. What representations of that reality are available?
4. What must be inferred?
5. What is materialized?
6. How is the inference tested?
7. What did the test establish?
8. What did it not establish?
9. What would a later iteration test?
10. How can another person run it?

Shared code should only be extracted after repeated working implementations demonstrate a real shared responsibility.

---

# First-Round Definition of Done

## Method A

Three deliberately different synthetic ADT source surfaces become one canonical event representation while raw source evidence and lineage remain available.

## Method B

Several fragmented workflow artifacts become one documented one-row-per-workflow model, including at least one relationship that must be reconstructed across multiple source artifacts.

## Method C

Validation confirms some inferred rules, corrects at least one documented assumption, and explicitly identifies at least one question that cannot be answered from the available evidence.

## Method D

A local Streamlit interface exposes workflows, metrics, validation state, history, and model documentation without introducing a separate hidden semantic model.

---

# First-Round Implementation Status

## Method A

Implemented on:

```text
experiment/method-a-hl7-conformance
```

Current implementation includes:

- synthetic ADT creation using existing MediLacra entities and HL7 builders;
- CSV, JSONL, and DuckDB source surfaces;
- source registry;
- raw evidence normalization;
- canonical ADT extraction;
- identity reconciliation;
- validation output;
- experiment README.

During review, the direct-run import path was aligned with the pattern already used by other MediLacra experiments so the runner can locate repository modules when invoked by file path.

## Method B

Implemented on:

```text
experiment/method-b-workflow-reconstruction
```

Current implementation includes:

- deterministic fragmented fixture generation;
- initial incomplete source notes;
- one-row-per-workflow reconstruction;
- assignment precedence;
- appointment reconciliation;
- two-hop closure linkage;
- fixed-time due-status derivation;
- reconstructed-model documentation.

## Method C

Implemented on:

```text
experiment/method-c-workflow-validation
```

Current implementation includes:

- validation status and interpretation separation;
- a compact multi-domain validation suite;
- deliberate lifecycle documentation correction;
- explicit not-testable evidence boundary;
- corrected documentation artifact.

The branch history was normalized after implementation so C is directly based on the current B head rather than carrying a duplicated repair commit.

## Method D

Implemented on:

```text
experiment/method-d-workflow-operations
```

Current implementation includes:

- thin Streamlit operational interface;
- workflow queue;
- table-first metrics;
- validation display;
- history display;
- reconstructed-model / corrected-documentation display.

The branch history was normalized so D is directly based on the current C head.

---

# Verification State

The first round has been implemented and inspected at the repository/diff level.

During that review, two concrete issues were identified and corrected:

1. direct-run import behavior in experiment runners;
2. temporary branch-history divergence after a lower branch was repaired after an upper branch had already been created.

The branch topology now reflects the intended dependency chain.

At the time of this documentation update, repository-level inspection has been completed, but this record does not claim that every experiment has already been executed end-to-end in a clean local environment or by automated CI.

That distinction is intentional:

```text
implemented + inspected != empirically executed
```

The first clean execution remains part of the experimental evidence.

Failures during that execution should be treated as useful evidence about assumptions, dependencies, packaging, or model behavior rather than hidden to preserve the appearance of completion.

---

# Clean-Room / Sanitization Boundary

This experiment set is intended to remain independent of any specific prior organization, community, or production environment.

Documentation and code should therefore avoid introducing:

- personal names or contact details;
- employer names;
- client or partner names;
- internal team names;
- private community references;
- internal hostnames or URLs;
- source-system-specific schema names;
- proprietary table or column names;
- internal ticket identifiers;
- copied mappings;
- copied production logic;
- private operational metrics;
- legal or personnel context;
- real patient or user data.

When prior experience motivates an experiment, only the generalized engineering problem should survive into MediLacra.

A useful rule is:

> Preserve the lesson, recreate the problem, generate new evidence.

---

# Deferred Work

Encounter classification under uncertainty is intentionally excluded from this first-round branch set.

A later experiment may test whether incomplete synthetic encounter evidence can be used to infer known underlying encounter class while exposing uncertainty and routing ambiguous predictions to human review.

That work should begin from its own minimal hypothesis and should not be added until the A-D experiments have been run and their first evidence reviewed.

---

# Next Review Questions

After first execution, review each experiment using the same questions:

1. Did the experiment actually demonstrate the intended method?
2. Which assumptions were wrong?
3. Which code exists only because of accidental implementation complexity?
4. Which parts are genuinely reusable across experiments?
5. Which outputs should become durable evidence artifacts?
6. What should remain primitive for another round?
7. Is any abstraction still too close to a prior implementation rather than the general problem class?

Only then should the experiments be expanded.

---

## Summary

The first round deliberately reduces four larger engineering patterns to small synthetic demonstrations:

```text
A: heterogeneous representation -> explicit conformance
B: fragmented evidence -> reconstructed operational model
C: reconstructed model -> validation, contradiction, correction
D: validated model -> operational interface + living explanation
```

The experiments are not intended to prove that a particular architecture is universally correct.

They are intended to make a method observable:

> inspect evidence, infer structure, materialize meaning, test the inference, preserve contradiction, correct what is wrong, and leave enough context for the next person to continue.

# MediLacra Interview Transform Trainer — Cheater

Branch: `cheater`

Status: working interview-prep prototype

## Purpose

Cheater is a deliberately small Streamlit surface for practicing common data-engineering interview transformations in SQL and plain Python.

The core training idea is:

```text
QUESTION
  ↓
REMOVE SEMANTIC NOISE
  ↓
IDENTIFY THE TRANSFORMATION
  ↓
GENERATED STARTING CODE
  ↓
EDIT THE CODE
  ↓
EXECUTE THE EDITED CODE
  ↓
OBSERVE THE RESULT
```

The generated code is not the answer boundary. It is a starting point. The code currently visible in the editor is what executes.

That matters because the user can change the transformation and immediately observe the consequence. For example:

```text
ORDER BY admit_ts DESC
        ↓ edit
ORDER BY admit_ts ASC
```

changes "latest encounter per patient" into "earliest encounter per patient" without changing the exercise definition.

## Current Architecture

```text
100-patient deterministic cohort
        ↓
exercise selection
        ↓
TransformationSpec
        ↓
semantic explanation
        ↓
┌────────────────────┬────────────────────┐
│ editable SQL       │ editable Python    │
│ starter            │ starter            │
└────────────────────┴────────────────────┘
        ↓                    ↓
 in-memory DuckDB       local Python exec
        ↓                    ↓
        └──────── result dataframe ───────┘
```

The page is a control surface. Transformation and execution logic lives in `cheater_engine.py`.

## Cohort

The default cohort is deterministic:

```text
patients       100
encounters     200
orders         200
observations   200
transactions   200
```

Each patient has exactly two encounters.

Each encounter has exactly:

- one order,
- one observation,
- one transaction.

The base cohort remains clean. Missing-record and duplicate-record exercises create disposable exercise tables rather than mutating the base data.

### Training schema

Cheater uses a small, purpose-built interview schema. It is MediLacra-flavored, but it is **not intended to be a mirror of every column in MediLacra's persistence schema**.

That is deliberate: Cheater needs stable relational shapes for interview drills, not a second production-style data model.

Current tables:

```text
patients
    patient_id
    patient_name
    date_of_birth
    sex
    state

encounters
    encounter_id
    patient_id
    visit_number
    patient_class
    admit_ts
    discharge_ts
    attending_provider_id

orders
    order_id
    patient_id
    encounter_id
    order_ts
    order_code

observations
    observation_id
    encounter_id
    order_id
    observation_code
    observation_value
    completed_time

transactions
    transaction_id
    encounter_id
    transaction_date
    transaction_amount
    billing_provider_id
```

## Exercise Families

### 1. Filter

Default:

> Filter encounters to outpatient rows.

Primary correspondence:

```text
SQL WHERE
↔
Python if / list comprehension
```

### 2. Group + Aggregate

Default:

> Count encounters per patient.

Primary correspondence:

```text
SQL GROUP BY + COUNT
↔
Python dictionary keyed by group
```

### 3. Join

Default:

> Join patient demographics to encounters.

Primary correspondence:

```text
SQL JOIN
↔
Python lookup dictionary
```

### 4. Latest / Top per Group

Default:

> Return the latest encounter for each patient.

Primary correspondence:

```text
SQL ROW_NUMBER() OVER (
    PARTITION BY ...
    ORDER BY ...
)
↔
Python group + sort + retain N
```

The renderer honors both:

- `order_direction` (`ASC` / `DESC`)
- `limit` (top N)

The SQL starter avoids DuckDB-only projection syntax so the displayed pattern is closer to ordinary interview SQL.

### 5. Missing / Duplicates

Two exercise variants:

- patients with no encounters,
- duplicate encounter IDs.

These operate on disposable exercise views.

## Editable Execution

### SQL

Generated SQL is loaded into the code editor.

Pressing **Run** submits the current editor text and executes it against an isolated in-memory DuckDB connection.

Cheater accepts one `SELECT` or `WITH` statement at a time and rejects obvious write/DDL operations.

This is intentionally a small local execution guard, not a general SQL security system.

### Python

Generated plain Python is loaded into the code editor.

Available table names are lists of dictionaries:

```text
patients
encounters
orders
observations
transactions
```

Exercise-specific tables such as `encounters_exercise` are also exposed when needed.

The edited code must assign final output to:

```python
result
```

Imports are disabled and the tables are disposable copies.

This is a trusted local interview sandbox, **not a security boundary for hostile Python code**.

## Files

```text
cheater_engine.py
pages/8_Cheater.py
tests/test_cheater_engine.py
docs/INTERVIEW_TRANSFORM_TRAINER.md
requirements.txt
```

Dependency added for the editor:

```text
streamlit-code-editor
```

## Tests

The Cheater tests cover:

- deterministic cohort cardinality,
- two encounters per patient,
- one order / observation / transaction per encounter,
- SQL and Python starter equivalence,
- default latest-per-patient behavior,
- ASC / DESC and top-N behavior,
- missing-record exercise isolation,
- duplicate-record exercise isolation,
- edited SQL changing output,
- edited Python changing output,
- Python execution not mutating the base cohort,
- rejection of SQL writes,
- rejection of multiple SQL statements,
- Python `result` contract.

Run locally in the established MediLacra environment:

```bash
conda activate dev310
pytest tests/test_cheater_engine.py -v
```

Launch MediLacra normally:

```bash
streamlit run medi_lacra_app.py
```

Then open the **Cheater** page.

## Current Non-Goals

Cheater is still intentionally small.

Do not add unless interview practice demonstrates a concrete need:

```text
free-text NLP
LLMs
voice input
fuzzy question parsing
SQL dialect selector
arbitrary schema upload
automatic schema inference
remote database connections
persistent user state
scoring
gamification
timers
question-generation engine
LeetCode-style algorithm catalog
FHIR / HL7 workflow integration
Reality Model integration
```

Pandas and DuckDB are implementation machinery for the local cohort and result materialization. They are not the skills being taught by the displayed plain-Python answer.

## Design Lineage

The original v0.1 plan treated code editing and query execution as non-goals. That was a useful initial boundary, but actual use exposed a stronger requirement:

> The user needs to demonstrate that the displayed SQL and Python are not preconfigured answers.

That changed the architecture.

The current rule is:

```text
exercise chooses the starting transformation
generated code provides a starting materialization
edited code is authoritative
execution proves the consequence
```

This is an intentional evolution of the first plan, not accidental scope creep.

## Finish Line

Cheater is doing its job when the user can:

1. recognize the transformation family,
2. explain the data shape,
3. inspect a generated SQL/Python starting point,
4. edit that code,
5. run the edited code,
6. explain why the output changed.

The purpose of this branch is interview leverage, not product expansion.

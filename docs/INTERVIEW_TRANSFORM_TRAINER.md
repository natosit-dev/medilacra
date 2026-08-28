# MediLacra Interview Transform Trainer

Branch: `cheater`

## Purpose

Build a deliberately small, deterministic interview-prep surface inside MediLacra for SQL and plain-Python data engineering questions.

The trainer does not attempt to understand arbitrary English. The user manually normalizes an interview question through dropdowns. Those selections become a canonical transformation specification, which is then rendered as:

1. normalized transformation logic,
2. SQL,
3. plain Python,
4. a concise verbal explanation of the data flow and output grain.

The goal is to train recognition of data shape and transformation primitives rather than rote syntax memorization.

## Core Principle

SQL and plain Python are treated as two materializations of the same underlying data transformation.

```text
INTERVIEW QUESTION
        ↓
HUMAN REMOVES SEMANTIC NOISE
        ↓
DROPDOWN SELECTIONS
        ↓
TRANSFORMATION SPEC
        ↓
┌───────────────┬───────────────┬───────────────┐
│ NORMALIZED    │ SQL           │ PLAIN PYTHON  │
│ LOGIC         │ RENDERER      │ RENDERER      │
└───────────────┴───────────────┴───────────────┘
        ↓
VERBAL EXPLANATION
```

The dropdowns are the parser. No NLP layer is required for v0.1.

---

# v0.1 Scope

The first version covers five high-probability data engineering interview primitives.

## 1. Filter

Typical wording:

- Find rows where...
- Return records matching...
- Show encounters after a date...

Canonical transformation:

```text
SOURCE
→ APPLY PREDICATE
→ RETURN MATCHING ROWS
```

Primary SQL primitive:

```text
WHERE
```

Primary Python primitive:

```text
if / list comprehension
```

Default drill:

> Return encounters admitted after a selected date.

---

## 2. Group + Aggregate

Typical wording:

- Count encounters per patient.
- Sum charges by provider.
- Average result value by test code.

Canonical transformation:

```text
SOURCE
→ GROUP BY DIMENSION
→ APPLY AGGREGATE
→ RETURN ONE ROW PER GROUP
```

Primary SQL primitives:

```text
GROUP BY
COUNT / SUM / AVG / MIN / MAX
```

Primary Python primitive:

```text
dictionary keyed by group + accumulator
```

Default drill:

> Count encounters per patient.

---

## 3. Join

Typical wording:

- Combine patients with encounters.
- Return orders with patient information.
- Match observations to encounters.

Canonical transformation:

```text
SOURCE A
+ SOURCE B
→ MATCH ON RELATIONSHIP KEY
→ RETURN COMBINED RECORDS
```

Primary SQL primitives:

```text
INNER JOIN
LEFT JOIN
```

Primary Python primitive:

```text
lookup dictionary keyed by join value
```

Default drill:

> Return patient demographics with their encounters.

---

## 4. Latest / Top per Group

Typical wording:

- Most recent encounter per patient.
- Highest charge per account.
- Top three observations per encounter.

Canonical transformation:

```text
SOURCE
→ PARTITION BY ENTITY / GROUP
→ ORDER WITHIN EACH PARTITION
→ KEEP FIRST OR TOP N
```

Primary SQL primitives:

```text
ROW_NUMBER()
PARTITION BY
ORDER BY
```

Primary Python primitive:

```text
dictionary keyed by group retaining best row
```

Default drill:

> Return the most recent encounter for each patient.

---

## 5. Missing / Duplicate

This is treated as one data-quality / existence family with a sub-operation dropdown.

### Missing match

Typical wording:

- Patients with no encounters.
- Orders without results.
- Records that do not have a matching parent.

Canonical transformation:

```text
SOURCE A
→ TEST FOR RELATED SOURCE B
→ RETAIN A WHERE B DOES NOT EXIST
```

Primary SQL primitives:

```text
LEFT JOIN ... IS NULL
NOT EXISTS
```

Primary Python primitive:

```text
set membership
```

Default drill:

> Return patients with no encounters.

### Duplicate key

Typical wording:

- Find duplicate encounter IDs.
- Identify keys appearing more than once.

Canonical transformation:

```text
SOURCE
→ GROUP BY KEY
→ COUNT
→ KEEP COUNT > 1
```

Primary SQL primitives:

```text
GROUP BY
HAVING COUNT(*) > 1
```

Primary Python primitive:

```text
frequency dictionary / Counter-like behavior without requiring packages
```

Default drill:

> Find duplicate encounter IDs.

---

# Canonical Transformation Model

The only new core abstraction for v0.1 is `TransformationSpec`.

Minimal fields:

```text
operation
source_a
source_b

entity_key
relationship_key

filter_column
filter_operator
filter_value

group_column
aggregate_function
aggregate_column

order_column
order_direction
limit

preserve_unmatched
```

Not every operation uses every field.

Example: latest encounter per patient.

```text
operation = TOP_PER_GROUP
source_a = encounters
group_column = patient_id
order_column = admit_datetime
order_direction = DESC
limit = 1
```

The canonical spec is the invariant. SQL and Python are renderers.

---

# Minimal Repository Changes

The implementation should remain isolated from existing MediLacra generation, HL7, Reality Interface, persistence, and Reality Model work.

Proposed additions:

```text
medilacra/
├── interview_trainer/
│   ├── __init__.py
│   ├── models.py
│   ├── patterns.py
│   ├── render_sql.py
│   ├── render_python.py
│   └── examples.py
│
├── apps/
│   └── interview_trainer.py
│
└── docs/
    └── INTERVIEW_TRANSFORM_TRAINER.md
```

If the repository already has an established Streamlit page convention, bind to it instead of creating a parallel app structure.

No database is required.

No new framework is required.

No new dependency should be introduced unless required by the existing application conventions.

---

# Static Training Schema

Use a tiny MediLacra-flavored schema for dropdown values.

Do not require live schema introspection in v0.1.

```text
patients
    patient_id
    birth_date
    sex
    zip

encounters
    encounter_id
    patient_id
    admit_datetime
    discharge_datetime
    encounter_class

observations
    observation_id
    encounter_id
    code
    value
    completed_datetime

transactions
    transaction_id
    encounter_id
    amount
    transaction_datetime

orders
    order_id
    encounter_id
    patient_id
    order_datetime
```

This can initially be represented as simple metadata:

```python
SCHEMAS = {
    "patients": [...],
    "encounters": [...],
    "observations": [...],
    "transactions": [...],
    "orders": [...],
}
```

The purpose is pedagogical normalization, not schema discovery.

---

# Control Surface

Use one thin Streamlit page.

## Primary control

```text
QUESTION FAMILY
[ Latest / Top per group ▼ ]
```

Only show controls relevant to the selected family.

Example for latest / top per group:

```text
SOURCE
[ encounters ▼ ]

GROUP / ENTITY KEY
[ patient_id ▼ ]

ORDER COLUMN
[ admit_datetime ▼ ]

DIRECTION
[ newest first ▼ ]

ROWS PER GROUP
[ 1 ▼ ]
```

## Output sections

### 1. Normalized transformation

Example:

```text
Partition encounters by patient_id.
Order each partition by admit_datetime descending.
Keep the first row.
```

### 2. SQL

Show a boring, readable, ANSI-ish solution pattern.

### 3. Plain Python

Show the equivalent transformation using basic Python data structures and control flow.

No pandas in v0.1.

### 4. Interview explanation

Example:

> Output grain is one row per patient. Records are partitioned by patient, ordered newest-to-oldest by admission time, and the first record from each partition is retained.

The verbal explanation is part of the training target, not decoration.

---

# Pattern Registry

`patterns.py` should contain five deterministic pattern families.

```text
FILTER
GROUP_AGGREGATE
JOIN
TOP_PER_GROUP
EXISTENCE_QUALITY
```

Each pattern owns:

```text
required fields
optional fields
semantic steps
SQL template
Python strategy
interview explanation
common traps
```

Example:

```text
TOP_PER_GROUP

Required:
- group_column
- order_column
- direction
- limit

Semantic steps:
1. partition by group
2. order within group
3. assign position
4. retain required number

Common traps:
- ties
- null ordering values
- output grain
```

The UI should not contain transformation logic.

---

# SQL Renderer

Keep the SQL renderer template-based.

No SQL parser.

No optimizer.

No AST unless a later requirement clearly justifies one.

Required templates:

```text
FILTER
SELECT ...
FROM ...
WHERE ...

GROUP_AGGREGATE
SELECT group, AGG(value)
FROM ...
GROUP BY group

JOIN
SELECT ...
FROM a
JOIN b ON ...

TOP_PER_GROUP
WITH ranked AS (...)
SELECT ...
WHERE rn <= n

ANTI_JOIN
LEFT JOIN ...
WHERE right.key IS NULL

DUPLICATES
GROUP BY key
HAVING COUNT(*) > 1
```

Prefer boring SQL over clever dialect-specific syntax.

---

# Plain Python Renderer

The Python renderer should expose the same transformation imperatively using only basic Python.

Conceptual correspondences:

```text
SQL WHERE
↔ Python if

SQL GROUP BY
↔ dictionary keyed by group

SQL JOIN
↔ lookup dictionary

SQL DISTINCT
↔ set

SQL window / rank
↔ grouping + comparison / sorting

SQL anti-join
↔ set membership
```

No pandas, Polars, PySpark, NumPy, or third-party helper packages in v0.1.

The point is to make the shared transformation visible before introducing execution-model differences.

---

# Optional Data Preview

If cheap to implement, show 5–10 tiny synthetic rows before and after the transformation.

Example:

```text
INPUT
patient_id | encounter_id | admit_datetime
1          | E1           | ...
1          | E2           | ...
2          | E3           | ...

↓ TOP PER PATIENT

OUTPUT
1 | E2 | ...
2 | E3 | ...
```

This is useful for making grain visible, but it is not required for v0.1 completion.

---

# Work Packets

## WP0 — Branch + Documentation

Create branch:

```text
cheater
```

Create this document:

```text
docs/INTERVIEW_TRANSFORM_TRAINER.md
```

Acceptance:

- purpose documented,
- five primitives documented,
- architecture documented,
- non-goals documented.

## WP1 — TransformationSpec

Implement the canonical model and static MediLacra training schema.

Acceptance:

> A complete dropdown selection can be represented without knowing SQL or Python.

## WP2 — Five Pattern Definitions

Encode the semantic operations, required fields, verbal explanation, and common traps.

Acceptance:

> Each family maps one `TransformationSpec` to an ordered transformation explanation.

## WP3 — SQL Renderer

Implement the required templates.

Acceptance:

> All default drills emit syntactically plausible SQL.

## WP4 — Python Renderer

Implement matching plain-Python patterns.

Acceptance:

> Every default drill expresses the same semantic result as its SQL version.

## WP5 — Streamlit Control Surface

Wire dropdowns to the canonical spec and renderers.

Acceptance:

> Changing a dropdown immediately changes normalized logic, SQL, Python, and the verbal explanation.

## WP6 — Smoke Tests

Minimal tests:

```text
test_filter
test_group_aggregate
test_join
test_top_per_group
test_anti_join
test_duplicates
```

The tests only need to validate the canonical spec and expected rendered fragments.

This is not a SQL-engine correctness project.

---

# Explicit Non-Goals for v0.1

Do not add:

```text
free-text NLP
LLMs
fuzzy extraction
voice input
pandas
PySpark
Polars
SQL dialect selection
query execution engine
database connections
LeetCode-style algorithm catalog
arbitrary schema loading
automatic schema inference
Reality Model integration
FHIR integration
HL7 integration
persistent user state
scoring system
gamification
timers
question-generation engine
```

Interesting extensions are not requirements.

Only add them later if actual interview practice proves they solve a real problem.

---

# v0.1 Finish Line

The branch is complete when a question such as:

> Find each patient's most recent encounter.

can be manually reduced through dropdowns to:

```text
Operation:
TOP PER GROUP

Source:
encounters

Group:
patient_id

Order:
admit_datetime

Direction:
DESC

Limit:
1
```

and MediLacra returns:

```text
CANONICAL LOGIC
partition → order → keep

SQL
ROW_NUMBER() ...

PYTHON
dictionary / comparison ...

VERBAL ANSWER
one row per patient ...
```

Once all five primitive families work, stop building and use the tool for drilling.

The purpose of this branch is interview leverage, not product expansion.

# MediLacra Structured Sparsity Experiment — Million-Patient Baseline Results

**Run record timestamp:** 2026-08-13 22:10 EDT (UTC-04:00)  
**Experiment branch:** `experiment/structured-sparsity-baseline-20260813`  
**Population:** 1,000,000 synthetic patients  
**Input grain:** 1 patient : 1 encounter : 1 observation : 1 transaction  
**Compared layouts:** canonical vs. bespoke/consumer-specific

## Question

Hold the represented synthetic healthcare reality constant, materialize it in two different relational shapes, run the same semantic workloads, and compare correctness, query structure, runtime, stored-state duplication, and change propagation.

The canonical layout stores semantic facts at their natural grain and reconstructs cross-entity relationships at query time. The bespoke layout preassembles consumer-oriented composites, reducing some query-time joins while duplicating state across multiple materialized representations.

## Query Results

All four workloads returned semantically matching results across the two layouts.

| Workload | Result rows | Semantic match | Canonical median (ms) | Bespoke median (ms) | Bespoke runtime reduction | Canonical tables | Bespoke tables | Canonical joins | Bespoke joins |
|---|---:|:---:|---:|---:|---:|---:|---:|---:|---:|
| Patient encounter history | 1,000,000 | True | 530.5777 | 524.7159 | 1.10% | 1 | 1 | 0 | 0 |
| Patient observations | 1,000,000 | True | 691.3770 | 625.8086 | 9.48% | 2 | 1 | 1 | 0 |
| Patient total charges | 1,000,000 | True | 192.0295 | 137.7521 | 28.27% | 2 | 1 | 1 | 0 |
| Provider clinical activity | 999,989 | True | 415.1322 | 364.9819 | 12.08% | 2 | 1 | 1 | 0 |

No workload used unions in either layout.

### Workload meanings

- **Patient encounter history:** Which encounters did each patient have?
- **Patient observations:** Which observations and diagnoses belong to each patient's encounters?
- **Patient total charges:** What is the total generated charge for each patient?
- **Provider clinical activity:** How many observations are associated with each attending provider/service?

## Layout Summary

| Metric | Canonical | Bespoke |
|---|---:|---:|
| Tables | 4 | 6 |
| Total materialized rows | 4,000,000 | 6,000,000 |
| Tables containing patient ZIP | 1 | 4 |
| Tables containing patient name | 1 | 4 |
| Tables containing hospital service | 1 | 5 |

The bespoke representation materialized **2,000,000 additional rows**, or **50% more stored rows**, for the same represented patient reality.

## Change Propagation Test

One semantic fact was changed: a single patient's ZIP code.

| Layout | Tables affected | Rows affected | Update statements |
|---|---:|---:|---:|
| Canonical | 1 | 1 | 1 |
| Bespoke | 4 | 4 | 4 |

The semantic change is identical, but the bespoke layout requires four materialized copies of the patient ZIP to co-vary while the canonical layout requires one.

## What This Run Establishes

At a population of 1,000,000 synthetic patients, both representations preserved the same tested semantic answers. The bespoke layout generally reduced query-time relational work for cross-entity workloads: three of the four workloads touched one bespoke table with no joins, while the canonical versions touched two tables and performed one join.

That read-time simplification was purchased by greater materialized-state duplication. The bespoke layout used six million rows instead of four million and copied patient and encounter facts across more tables. The ZIP mutation test exposes the maintenance consequence directly: one semantic change propagated to four bespoke rows across four tables versus one canonical row in one table.

A concise statement of the measured tradeoff is:

> **The bespoke representation reduces query-time coupling by increasing state coupling.**

A second formulation is:

> **Both layouts preserve the same tested semantic reality; one materializes more relationships into stored state, while the other reconstructs more relationships when queried.**

## Limits of the Result

This run is a 1:1:1:1 grain baseline. It does not yet establish what happens when one patient has multiple encounters and each encounter has multiple observations and transactions. That richer-grain experiment is necessary to test whether duplication and change-propagation fan-out grow multiplicatively when independent one-to-many relationships are flattened into shared bespoke representations.

Runtime differences should also not be interpreted as universal database performance claims. The measurements are specific to these DuckDB schemas, workloads, generated data, hardware, and experiment implementation. The strongest result here is the repeatable structural difference in materialized state and propagation requirements while semantic outputs remain equal.

## Source Files

This record was produced from:

- `query_results(3).csv`
- `layout_summary(3).csv`
- `change_propagation(3).csv`

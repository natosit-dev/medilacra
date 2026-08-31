# Disco Inferno MVP Results — 20260831T082301-0400

**Status:** GOOD ENOUGH — MVP COMPLETE  
**Experiment:** Disco Inferno / Medilacra entropy engine  
**Run ID:** `20260831T082301-0400`  
**Validated:** 2026-08-31  

## Bottom line

The MVP reached its intended boundary:

- one fixed Medilacra reality was generated;
- the untouched representation was preserved as **Beatrice**;
- three independent cursed copies were produced from that same representation;
- the corruption operators were deterministic and measurable;
- the control arm completed with zero delta;
- the source reality was persisted to DuckDB;
- HL7 projections were emitted as timestamped bulk files;
- the Streamlit control surface completed the run and exposed measurements/artifacts;
- external SDOH enrichment was disabled for the local deterministic run boundary.

No universal entropy score is claimed. The MVP establishes the apparatus needed to study representational damage before attempting a general theory of entropy.

## Source reality — Beatrice

| Entity | Count |
|---|---:|
| Patients | 100 |
| Encounters | 200 |
| Observations | 400 |
| Transactions | 400 |

Generation settings:

```text
patients                    100
encounters / patient          2
observations / encounter      2
transactions / encounter      2
reality seed                 42
Inferno seed                666
SDOH enrichment             OFF
lab ORM / lab ORU exports   OFF for this recorded run
```

## Inferno settings and observed damage

### Charon — drop identifier

```text
operator: drop_identifier
target:   observations.encounter_id
```

| Measure | Beatrice | Inferno | Delta |
|---|---:|---:|---:|
| Observation rows | 400 | 400 | 0 |
| Observation columns | 17 | 16 | -1 |
| Explicit encounter references | 400 | 0 | -400 |

**Affected:** 400 / 400 observations (100%).

Interpretation: all observation rows remain present while the explicit observation-to-encounter relationship is removed. This is the clearest MVP demonstration that representational damage can occur without row loss.

### Null — erase facts

```text
operator: null_field
target:   observations.icd_code
fraction: 0.17
```

**Affected:** 68 / 400 observations (17%).

The row set is preserved while selected facts are removed. This isolates factual missingness from identity loss and cardinality inflation.

### Cerberus — duplicate records

```text
operator: duplicate_record
target:   transactions
fraction: 0.06
```

**Affected source rows:** 24 / 400 transactions (6%).

The underlying reality still contains 400 transactions while the cursed representation contains 24 additional copies, producing 424 represented transaction rows.

## Control

The run completed through the experiment harness, which requires the no-op control comparison to report zero damage before a run is accepted as complete.

```text
Control delta = 0
```

This is the critical apparatus check: the comparison machinery itself is not manufacturing observed damage.

## Durable artifacts produced

The completed run produced the timestamped artifact bundle below:

```text
source_reality_20260831T082301-0400.duckdb
DISCO_INFERNO_20260831T082301-0400.zip
DISCO_INFERNO_REPORT_20260831T082301-0400.md
manifest_20260831T082301-0400.json
metrics_20260831T082301-0400.csv
ADT_A01_20260831T082301-0400.hl7
ORU_R01_20260831T082301-0400.hl7
DFT_P03_20260831T082301-0400.hl7
```

Observed artifact sizes from the completed UI run:

| Artifact | Size |
|---|---:|
| Source-reality DuckDB | 1.51 MB |
| Complete ZIP bundle | 866.1 KB |
| ADT_A01 bulk HL7 | 299.7 KB |
| ORU_R01 bulk HL7 | 549.7 KB |
| DFT_P03 bulk HL7 | 315.1 KB |

The binary run payload is intentionally treated as generated output rather than source code. This repository record preserves the canonical experiment configuration, observed measurements, artifact inventory, and interpretation boundary.

## What the MVP established

Disco Inferno can now make three distinct representational failures directly observable against a known source reality:

1. **Relationship loss** — Charon can preserve every observation row while eliminating the explicit encounter relationship.
2. **Fact loss** — Null can preserve structure and cardinality while removing selected facts.
3. **Cardinality ambiguity** — Cerberus can increase represented records without increasing underlying reality entities.

The architectural comparison with Structured Sparsity is now concrete:

```text
STRUCTURED SPARSITY
same reality
    ↓
different model representations
    ↓
what relationships survive structural transformation?

DISCO INFERNO
same reality
same model
    ↓
Beatrice ↔ cursed representation
    ↓
what knowledge survives information degradation?
```

## Good-enough boundary

The following are deliberately deferred until a future experiment requires them:

- universal or weighted entropy scoring;
- reconstruction / recoverability scoring;
- compound corruption (**Lucifer**);
- direct corruption of HL7 or FHIR payloads;
- cognition experiments;
- larger corruption catalogs;
- productization beyond the current Streamlit control surface.

The next research question remains:

> **Given only the cursed side, what parts of the original reality can still be known?**

That is post-MVP work. The current implementation is accepted as a reusable experimental primitive.

# MediLacra Structured Sparsity Experiment — Results So Far

**Date:** 2026-08-13  
**Status:** Baseline results complete through 10,000 patients at 1/1/1 grain; 1/5/5/5 grain run and human reaction-time layer designed but not yet observed.  
**Repository:** `natosit-dev/medilacra`  
**Public experiment branch:** `experiment/structured-sparsity-baseline-20260813`

## 1. What has actually been demonstrated

The experiment currently has one strong invariant:

> **The same generated healthcare reality is materialized into two different database layouts, and semantic equality is checked before performance is interpreted.**

Across runs at **25, 1,000, and 10,000 patients**, every tested semantic workload returned equivalent results in the canonical and bespoke layouts.

That matters more than the timing numbers. It establishes that the experiment is comparing two different relationship/materialization structures while preserving the tested meaning of the underlying synthetic reality.

The evidence so far supports a real tradeoff:

- the **canonical layout** stores fewer duplicated states and requires more relationship traversal for some reads;
- the **bespoke layout** preassembles more relationships for convenient reads, but duplicates more state and therefore creates more materialized values that must co-vary when an underlying fact changes.

The current experiment therefore distinguishes two mechanically different forms of coupling:

**Query coupling** — how much relationship traversal is required to answer a semantic question.

**State coupling** — how many materialized representations must co-vary to preserve one underlying semantic fact.

The result so far is not that one layout has “more coupling” in every sense. It is that one form of coupling can be reduced by increasing another.

---

## 2. Baseline layout comparison

At baseline grain:

```text
1 patient
1 encounter / patient
1 observation / encounter
1 transaction / encounter
```

the layouts are:

### Canonical

```text
Patient
   |
Encounter
  /       \
Observation Transaction
```

Core tables:

- `patients`
- `encounters`
- `observations`
- `transactions`

### Bespoke

Consumer-oriented materializations:

- `adt_activity`
- `oru_activity`
- `dft_activity`
- `patient_activity_report`
- `provider_activity_report`
- `financial_activity_report`

The bespoke representation makes some reads local by storing already-combined state, but that convenience comes from copying facts into multiple places.

---

## 3. Baseline results through 10,000 patients

### Semantic preservation

All four workloads remained semantically equal between layouts at 25, 1,000, and 10,000 patients:

1. patient encounter history;
2. patient observations and diagnoses;
3. total charges by patient;
4. provider clinical activity.

No performance result is interpreted unless the semantic comparison passes.

### Structural comparison at 10,000 patients

| Measure | Canonical | Bespoke |
|---|---:|---:|
| Tables | 4 | 6 |
| Materialized rows | 40,000 | 60,000 |
| ZIP copy tables | 1 | 4 |
| Patient-name copy tables | 1 | 4 |
| Hospital-service copy tables | 1 | 5 |
| ZIP update footprint | 1 row / 1 table | 4 rows / 4 tables |

The bespoke representation therefore used **50% more materialized rows** for the same generated state at baseline grain.

The ZIP mutation is particularly useful because it measures state propagation directly:

```text
canonical:
one semantic ZIP change
    ↓
1 stored row must change

bespoke:
one semantic ZIP change
    ↓
4 stored rows across 4 tables must change
```

That ratio remained structurally stable from the 25-patient run through the 10,000-patient run.

---

## 4. Read-time results at 10,000 patients

| Workload | Canonical median ms | Bespoke median ms | Canonical joins | Bespoke joins |
|---|---:|---:|---:|---:|
| Patient encounter history | 11.0071 | 10.5416 | 0 | 0 |
| Patient observations | 18.7703 | 13.0884 | 1 | 0 |
| Patient total charges | 12.9586 | 8.4806 | 1 | 0 |
| Provider clinical activity | 19.1938 | 14.2559 | 1 | 0 |

The exact millisecond ratios are not treated as portable performance claims. They are local DuckDB measurements and can vary with caching, hardware, and optimizer behavior.

The pattern is still informative:

- when both layouts can answer a question directly, performance is broadly similar;
- when the canonical layout must traverse a relationship with a join and the bespoke layout already materializes that relationship, the bespoke read is cheaper in these runs.

Mechanically:

```text
CANONICAL

less duplicated state
        ↓
fewer stored values forced to co-vary
        ↓
more relationship traversal for some reads
```

versus:

```text
BESPOKE

relationships preassembled
        ↓
less traversal for those reads
        ↓
more duplicated state
        ↓
more stored values forced to co-vary when reality changes
```

The useful finding is therefore not “normalization is faster” or “denormalization is faster.”

It is:

> **Read-time relationship traversal can be exchanged for write/materialization-time state coupling.**

---

## 5. Why the next grain run matters

The baseline is structurally easy because each encounter has one observation and one transaction.

The next designed run changes the underlying relationship cardinality:

```text
1 patient
5 encounters
5 observations / encounter
5 transactions / encounter
```

Now each encounter has two independent one-to-many relationships:

```text
                 Encounter
                /         \
      5 Observations     5 Transactions
```

The canonical model can preserve those child grains independently.

The flat bespoke `patient_activity_report` carries both observation-level and transaction-level facts. To preserve both without nesting or splitting, it materializes encounter-local observation × transaction combinations:

```text
5 observations × 5 transactions
= 25 combined rows / encounter
```

Across 5 encounters:

```text
25 × 5 = 125 patient_activity_report rows / patient
```

### Predicted rows per patient

| Layout | Total materialized rows |
|---|---:|
| Canonical | 56 |
| Bespoke | 230 |

Predicted ratio:

```text
230 / 56 ≈ 4.11×
```

This is a much stronger test than merely increasing patient count because it changes the **relationship grain of reality itself**.

### Predicted ZIP mutation footprint

For one patient:

```text
canonical:
1 row

bespoke:
adt_activity                5
oru_activity               25
dft_activity               25
patient_activity_report   125
                         ----
total                     180
```

The canonical ZIP remains one patient-level fact. The bespoke ZIP is copied into child-grain and fan-out materializations.

If the run matches these predictions while semantic equality remains intact, the stronger mechanical statement would be:

> **The cost of materializing coupled state is not determined only by record count. It can grow from the interaction of independent relationship grains.**

That is still a prediction until the grain run is executed.

---

## 6. Human reaction-time layer

A third measurement layer has been designed and implemented but has not yet produced results.

The cognitive task was deliberately reduced to basic visual relationship recovery, for example:

```text
BIRD → BLUE
HOUSE → 7
MOON → CAT
TREE → APPLE

What goes with BIRD?

1. CAT
2. 7
3. BLUE
4. APPLE
```

MediLacra data replaces the arbitrary tokens while preserving the same cognitive operation.

The current implementation produces **10 randomized trials: 5 canonical and 5 bespoke**.

The human measurement records:

- correct / incorrect;
- reaction time in milliseconds;
- timeout;
- selected option;
- relationship type;
- number of visible relationship steps;
- presentation order and seed.

The intended comparison is:

```text
database read traversal
database state propagation
human relationship traversal
```

The human layer is currently **N=1 and exploratory**. It can measure how one subject responds to the representations; it cannot establish a general claim about human cognition.

---

## 7. Mechanical connection to oscillator sparsity

The experiment grew from a coupled-oscillator sparsity result, but the comparison is kept at the level of mechanics rather than metaphor.

### Oscillator

An oscillator is a physical system whose internal state repeatedly moves through a cycle.

### State

State is the information needed at a given moment to determine what the system will do next.

### Phase

Phase is the oscillator's current position in its repeating cycle.

### Phase evolution

Phase evolution is how that position changes over time. The rate of phase change is the phase velocity.

### Dependency

A dependency exists when determining the next state of one part of a system requires information about another part.

### Coupling

Coupling is the mechanism and strength by which one oscillator's state changes another oscillator's evolution.

### Oscillator network

An oscillator network is a collection of oscillators plus the interaction paths that permit some oscillators to affect the dynamics of others.

The database is also ultimately a physical process, but a semantic database relationship does **not** map one-for-one onto an oscillator coupling.

The useful comparison is narrower:

```text
oscillator model:
another oscillator's state enters the rule
that determines phase evolution

database experiment:
another represented state must be read,
joined, copied, or updated to recover or
preserve the semantic result
```

For MediLacra:

> **Hold the generated state constant, change which stored states must be read together or changed together, and measure the resulting semantic, computational, materialization, and human-readout effects.**

---

## 8. Current evidence boundary

### Established by the runs so far

- semantic equality across the four tested workloads through 10,000 patients;
- 50% greater materialized-row count in the baseline bespoke layout;
- lower query traversal in the preassembled bespoke workloads;
- higher state-propagation footprint in the bespoke layout;
- structural stability of those baseline ratios as patient count scales.

### Designed or predicted, but not yet observed

- 1/5/5/5 grain fan-out;
- 4.11× bespoke/canonical row ratio at that grain;
- 180-row bespoke ZIP propagation for one patient at that grain;
- reaction-time differences between canonical and bespoke displays.

### Not established

- that relational databases are mathematically equivalent to oscillator networks;
- that DuckDB timing generalizes to other database engines;
- that the canonical layout is universally better;
- that the bespoke layout is universally worse;
- that one person's reaction-time data generalizes to humans generally.

---

## 9. Current scorecard

| Question | Status |
|---|---|
| Can two different layouts preserve the same tested meaning? | **Demonstrated** |
| Does preassembly reduce query traversal for some reads? | **Demonstrated** |
| Does duplicated materialization increase state propagation? | **Demonstrated** |
| Do these baseline structural ratios survive patient-count scaling? | **Demonstrated through 10,000 patients** |
| Does coupling cost grow with independent relationship grain? | **Predicted; next run** |
| Does representation alter basic human relationship-recovery time? | **Implemented; not yet measured** |

---

# Appendix A — Relevant Prompt History

The following prompts directly drove the structured-sparsity experiment and its current interpretation.

## Prompt 1

> Can I demonstrate this principle with Medilacra? Maybe iterators during generation. Route it to 2 ingestion dbs. 1 with a large number of bespoke tables. One with standard Medilacra output. Run the same queries on each and measure the performance. Change the grain, run it again.
>
> Don't get excited. I want to keep this at a level I can understand

## Prompt 2

> Ok, let's figure out the minimal changes needed to Medilacra to design this year. Check the GitHub repo, give me some options for a structured Sparsity branch

## Prompt 3

> Let's do option 1. Does that preserve enough meaning to be useful as a conceptual test of sparcity?

## Prompt 4

> Yeah, let's do this one
>
> 1 patient
> 5 encounters
> 5 observations per encounter
> 5 transactions per encounter
>
> Also, document the experiment design history test results up to now and create a MD. Include the full prompt history at the end.

## Prompt 5

> Could we loop in my own cognition into the data? Multiple choice, 1-4, of basic cognition of how relationships are displayed using heterogenous but semantically unique data. Testing basic human reaction time.

## Prompt 6

> No, that's too specific. Basic cognition

## Prompt 7

> Ok you're losing me. The cognitive test should be something any human could Intuit in less than 5 seconds

## Prompt 8

> BIRD → BLUE
> HOUSE → 7
> MOON → CAT
> TREE → APPLE
>
> What goes with BIRD?
>
> 1. CAT
> 2. 7
> 3. BLUE
> 4. APPLE
>
> Boom. That's it. Now swap in Medilacra data

## Prompt 9

> Now design the experiment. At the end of the "Generated ..." print let's include 5 prompts like the ones we just identified for each data model. record the correctness, reaction time, anything else relevant. Log the results in a separate output

## Prompt 10

> Write the code

## Prompt 11

> Ok how fucking wild is this? I heard about this a couple hours ago

## Prompt 12

> What databases don't have physical oscillator dependencies somewhere down the line? 🙃

## Prompt 13

> oscillator networks and databases are both physical information-processing systems, and we can ask the same topological question of each: which interactions are necessary to preserve the behavior we care about?
>
> This feels like slop. It's emotional at the end, it throws in some generic definitions. Topological is a fancy word. Try again with more mechanics

## Prompt 14

> Fuck, we've gotta go deeper... Define oscillator network, state, dependency, coupling, phase evolution in a way I can understand

## Prompt 15

> Let's see the results so far

## Prompt 16

> Print that to MD, add my prompts, add it to the latest public experiment repo

---

## 10. Current interpretation in one sentence

> **So far, the experiment shows that the same semantic state can be preserved while moving cost between relationship traversal and materialized state propagation; the next grain run tests whether that propagation cost grows through the interaction of independent one-to-many relationships, and the cognition layer tests whether representation also changes the human cost of recovering the same relationship.**

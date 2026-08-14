# Structured Sparsity Experiment — Synthesis

**As of:** 2026-08-14 12:20 -04:00  
**Branch:** `experiment/structured-sparsity`  
**Scope:** Results collected so far, experiment change log, prompt history, hypotheses, and possible interpretations.

> This is a conceptual data-systems experiment inspired by structured sparsity work. It is **not** a claim that database schemas are literally oscillator networks.

## The whole thing in normal-person language

The experiment started with a simple question:

> **If the underlying reality stays the same, what happens when we change how its relationships are arranged?**

That is the bridge back to the sparsity paper.

The paper is about **coupling topology** — fancy language for *which things are allowed to affect which other things, and how many of those connections exist*.

The useful lesson is not “less is always better.” Too much interaction can make a system worse, while intelligently limiting or organizing interaction can preserve more useful independent behavior. Too little interaction can also fail because the pieces stop communicating.

Our MediLacra version became:

> Generate the healthcare world once. Store the **exact same world** in two different shapes. Ask both versions the same questions. First make sure they give the same answer. Then measure what each shape costs.

That is basically an **iso-state experiment** — *same state, different relationship structure*.

The two shapes are:

```text
CANONICAL

Patient
   |
Encounter
 /       \
Obs       Transaction
```

versus something more like:

```text
BESPOKE

ADT activity
ORU activity
DFT activity
patient report
provider report
financial report
```

Canonical keeps facts closer to their natural home and reconstructs some combinations later.

Bespoke pre-combines useful relationships so the answer is often sitting right there waiting for you.

The central tradeoff has become:

> **Bespoke reduces query-time coupling by increasing state coupling.**

Plain English: **it does some of the relationship work ahead of time, but then you have more copies that all need to stay synchronized.**

---

# 1. What we have actually measured

## Baseline: 1 patient → 1 encounter → 1 observation → 1 transaction

We first scaled the *number of patients* while keeping that internal shape fixed.

| Patients | Canonical rows | Bespoke rows | ZIP change: canonical | ZIP change: bespoke | Semantics |
|---:|---:|---:|---:|---:|---|
| 25 | 100 | 150 | 1 row | 4 rows | matched |
| 1,000 | 4,000 | 6,000 | 1 | 4 | matched |
| 10,000 | 40,000 | 60,000 | 1 | 4 | matched |
| 1,000,000 | 4,000,000 | 6,000,000 | 1 | 4 | matched |

The million-patient run reproduced the same structural result at a **40,000× larger patient population than the first run**: 4 million canonical rows versus 6 million bespoke rows, while all four tested semantic answers still matched.

That means the first finding was not just a tiny-data accident.

At that simple grain, bespoke consistently pays about a **50% materialization premium**:

```text
canonical = 4 facts per patient
bespoke   = 6 materialized rows per patient
```

But it buys easier reads for questions it has already assembled.

At one million patients:

| Workload | Canonical | Bespoke | Structural difference |
|---|---:|---:|---|
| Encounter history | 530.6 ms | 524.7 ms | neither needs a join |
| Observations | 691.4 | 625.8 | canonical joins; bespoke doesn't |
| Charges | 192.0 | 137.8 | canonical joins; bespoke doesn't |
| Provider activity | 415.1 | 365.0 | canonical joins; bespoke doesn't |

The exact milliseconds are not the important scientific result. DuckDB, caches, hardware, and implementation details matter.

The important part is that the **relationship work is visibly different**.

**Fancy term:** *query coupling*  
**Normal term:** *how many relationships do I have to chase down to get my answer?*

---

# 2. Then grain changed everything

The more interesting experiment was:

```text
1 patient
5 encounters
5 observations / encounter
5 transactions / encounter
```

Before running it, we predicted:

```text
canonical = 56 rows
bespoke   = 230 rows
```

because the bespoke `patient_activity_report` has to flatten two independent one-to-many relationships:

```text
              Encounter
             /         \
     5 observations   5 transactions
```

If both dimensions are forced into flat rows:

```text
5 × 5 = 25 combinations / encounter
25 × 5 encounters = 125 patient_activity_report rows
```

That prediction landed exactly.

Canonical:

```text
patients       1
encounters     5
observations  25
transactions  25
             ---
TOTAL         56
```

Bespoke:

```text
ADT                         5
ORU                        25
DFT                        25
patient_activity_report   125
provider_activity_report   25
financial_activity_report  25
                           ---
TOTAL                     230
```

So the bespoke/canonical materialization ratio went from:

```text
baseline:     1.50×
rich grain:   4.11×
```

**without adding more tables.**

That matters because the table topology barely changed. What changed was the **dimensionality of the reality inside it**.

**Fancy term:** *multiplicative fan-out across independent relationship grains.*  
**Normal term:** *once two separate “many” relationships get mashed into the same flat representation, they multiply each other.*

That is more interesting than simply saying “normalized databases have fewer rows.”

---

# 3. The ZIP experiment got ridiculous

At baseline:

```text
one ZIP changes

canonical → 1 row changes
bespoke   → 4 rows change
```

At 1/5/5/5:

```text
canonical → 1 row
bespoke   → 180 rows
```

Why 180?

```text
ADT                        5
ORU                       25
DFT                       25
patient_activity_report  125
                         ---
                         180
```

One fact about one person has become physically represented in **180 places**.

The number of affected bespoke tables is still only four.

That gives us an important distinction:

**Topology breadth** = *how many kinds of places are connected?*  
**Propagation fan-out** = *how many actual materialized pieces of state have to move when reality changes?*

Those are not the same measurement.

A strong result so far is:

> **Coupling severity cannot be measured by counting tables or edges alone. Grain determines how much state each relationship carries with it.**

Or, less fancy:

> Four dependencies can be fine when they carry four copies. The same four dependencies get ugly when they drag 180 copies behind them.

---

# 4. Latest machine run

The fixed 12:11 run used the 1/5/5/5 shape, passed all semantic checks, and reproduced the structural prediction.

The four machine queries were:

| Question | Canonical | Bespoke |
|---|---:|---:|
| Encounter history | 0.811 ms | 0.650 ms |
| Observations | 1.755 | 1.008 |
| Charges | 2.334 | 1.508 |
| Provider activity | 2.593 | 2.000 |

Again, this does **not** mean “bespoke databases are X% faster.”

The useful pattern is simpler:

```text
same answer

canonical:
sometimes reconstruct relationship at read time

bespoke:
relationship already sitting on one row
```

So the bespoke layout is spending storage and maintenance complexity to make certain retrievals local.

The cleanest phrasing remains:

> **The bespoke system reduces coupling at read time by creating coupling at maintenance time.**

---

# 5. Human cognition: what we have so far

This started because the goal was explicitly **not** to build a psych exam or puzzle.

The key conceptual simplification was:

> “BIRD → BLUE ... What goes with BIRD? Boom. That's it. Now swap in MediLacra data.”

The current semantic task is:

```text
Given an observation,
which attending provider goes with it?
```

Bespoke:

```text
observation → provider
```

Canonical:

```text
observation → encounter → provider
```

A natural human procedure emerged:

```text
look at the last few characters
→ locate the row
→ follow whatever relationship is shown
→ choose the corresponding provider
```

That is not cheating. It is the brain creating a **task-efficient representation**.

**Fancy term:** *lossy compression preserving discriminative information.*  
**Normal term:** *you don't need the whole UUID; a few characters are enough to find the thing.*

## Cognition results so far

| Run | Order | Canonical | Bespoke | Important caveat |
|---|---|---|---|---|
| 08:19 | canonical first | 4/5, median 12.08s | 5/5, 6.24s | no baseline RT yet |
| 08:29 | bespoke first | 3/5, 9.27s | 4/5, 6.42s | order reversed |
| 11:15 | canonical first | 4/5, 8.01s | 2/5, 7.23s | old display; ambiguous stimulus possible |
| 11:56 | canonical first | 5/5, 9.36s | 4/5, 8.29s | one bespoke trial definitely ambiguous |

The 11:56 bespoke “error” contained the same visible observation twice with two different providers, so it was **not a valid cognitive error**. That trial should be discarded. After removing it, bespoke was 4/4 valid responses.

The stimulus generator was then fixed so duplicate visible observation/encounter identifiers cannot appear in a trial, and the display version was bumped to 1.1.

The 12:11 run is the first run after that fix. Its config says all ten trials completed, but the cognition CSV was not included in the review that produced this document, so its canonical/bespoke timing and accuracy are intentionally left unfilled here rather than guessed.

---

# 6. The simple reaction-time sensor

Before asking the relational question, the experiment now asks something requiring essentially no reasoning:

```text
READY

[random delay]

NOW!
```

Press a key.

The last three baselines have been:

```text
312.7 ms
316.0 ms
299.8 ms
```

The newest run's five measured reactions ranged from **272.0 to 317.5 ms**, median **299.8 ms**, with zero false starts.

Why this matters:

If a relational answer takes 8 seconds one session and 12 seconds another, we can at least ask:

> Did the whole visual/motor system slow down?

versus:

> Did the relationship task itself get harder?

We should **not** automatically subtract 300 ms from everything. That would bake in a theoretical assumption we have not earned.

But we now have a control signal.

**Fancy term:** *sensor normalization / state covariate.*  
**Normal term:** *we have a little speedometer for how awake the eyes and fingers are that session.*

---

# 7. Change log: how the experiment evolved

**v0 — Idea.** Same synthetic reality, two database layouts, same queries.

**v1 — Semantic gate.** Correctness became mandatory before speed could mean anything.

**v2 — Query/state coupling distinction.** “More tables” was recognized as the wrong variable. The experiment started separating relationships traversed during reads from copies that must co-vary during updates.

**v3 — Scale.** 25 → 1,000 → 10,000 → 1,000,000 patients. The baseline structural pattern stayed put.

**v4 — Grain.** Added independent encounters, observations, and transactions. This exposed multiplicative fan-out.

**v5 — Timestamped experimental apparatus.** Each run gets its own DBs, CSVs, config, phase timings, branch/commit provenance.

**v6 — Human readout.** Added five canonical + five bespoke relationship lookups.

**v7 — “Sensor, not puzzle.”** Reduced cognition to simple association retrieval rather than trying to make questions intellectually difficult.

**v8 — Participant orientation.** Added the “this isn't an intelligence test, relax” intro plus 1-2-3-4 finger calibration.

**v9 — Simple reaction baseline.** Added the READY/NOW visual reaction sensor.

**v10 — Clean visual field.** Clear terminal between relational questions so the participant isn't spending cognition finding where the next trial starts.

**v11 — Ambiguity protection.** Discovered duplicate visible observation IDs, classified the affected trial as invalid, then changed stimulus generation so every visible identifier within a question is unique. Commit `3043f84`.

This has mostly improved through **simplification**, not by making the test more elaborate.

---

# 8. Prompt history — conceptual turns that changed the experiment

The prompts that materially changed the design included:

> “Can I demonstrate this principle with Medilacra?... Route it to 2 ingestion dbs... Run the same queries on each and measure the performance. Change the grain, run it again.”

Then:

> “Does that preserve enough meaning to be useful as a conceptual test of sparcity?”

Then the key grain change:

> “1 patient / 5 encounters / 5 observations per encounter / 5 transactions per encounter.”

Then:

> “Could we loop in my own cognition into the data?”

Then the correction when the cognition design got too fancy:

> “No, that's too specific. Basic cognition.”

Then:

> “The cognitive test should be something any human could Intuit in less than 5 seconds.”

Then the compression that solved it:

> “BIRD → BLUE ... What goes with BIRD?... Boom. That's it. Now swap in Medilacra data.”

Then the experimental philosophy got cleaner:

> “Yeah, I don't want these to be puzzles, just raw cognitive sensors.”

Then participant-state control:

> “A pre test of straight reaction time without reasoning would be good.”

Then presentation noise removal:

> “For the 1-4 testing we should clear the screen.”

Then the malformed question exposed an actual sensor bug:

> “This question confused me.”

That prompted the unique-visible-ID fix.

---

# 9. Current hypotheses

## H1 — Meaning can survive topology changes

**Fancy:** *semantic invariance under representational transformation.*  
**Normal:** rearranging the data does not necessarily change what it means.

**Status:** strongly demonstrated for the four tested workloads so far. From 25 to one million baseline patients, and now at richer grain, the two layouts still answer the tested questions equivalently.

## H2 — Read coupling and state coupling trade off

**Fancy:** *pre-materialization shifts relational work from query-time traversal into synchronization obligations.*  
**Normal:** do the joining early and reads get easier, but now there are copies to maintain.

**Status:** demonstrated in this apparatus.

## H3 — Grain amplifies coupling cost

**Fancy:** *state-coupling cost can grow multiplicatively with independent relationship cardinalities.*  
**Normal:** two separate “many” relationships can explode when flattened together.

**Status:** demonstrated for the designed 5×5 case.

## H4 — Human traversal may reflect representational traversal

**Fancy:** *human relational readout may be sensitive to topology in the same direction as machine query traversal.*  
**Normal:** if the answer is two hops away instead of one, a human may take a bit more work to find it too.

**Status:** interesting signal, not established. One person, few trials, learning effects, and multiple sensor versions. Do not turn this into “normalization makes humans 38% smarter.”

## H5 — There is probably an optimum, not a winner

This is the hypothesis most directly faithful to the original sparsity idea.

**Fancy:** *the useful regime may be non-monotonic with respect to coupling density.*  
**Normal:** some redundancy and preassembly are genuinely useful. Too much gives a synchronization/maintenance mess. Too little gives a pile of disconnected pieces nobody can efficiently use.

**Status:** not yet directly tested across a continuum, but the canonical/bespoke tradeoff makes it a plausible theoretical frame.

---

# 10. How this ties back to the sparsity paper without bullshitting

| Sparsity-paper idea | MediLacra analogue | Translation |
|---|---|---|
| **State** | patients, encounters, observations, transactions | the things that exist |
| **Coupling** | dependency/traversal/propagation relationship | who has to know about whom |
| **Coupling topology** | storage + dependency graph | how those relationships are arranged |
| **Dense coupling** | lots of facts repeatedly materialized together | everything knows too much about everything |
| **Structured sparsity** | preserve important relationships, constrain unnecessary ones | connect things deliberately |
| **Synchronization** | many materialized states forced to move together | change one fact, update everything |
| **Effective dimensionality** | how independently distinct facts can vary | can observation and transaction remain separate things? |
| **Modularity** | rich local models with narrow interfaces | keep useful clusters, control cross-cluster dependencies |

A SQL foreign key is **not literally an oscillator coupling**, and a database is not mathematically equivalent to the oscillator system.

The common object is the **topology of dependency**.

The most provocative analogy is probably synchronization.

In the oscillator world, strong coupling can make many oscillators move together, reducing **effective dimensionality** — lots of physical units, but fewer independently behaving modes.

In this data world, the flat bespoke representation can make distinct dimensions of reality repeatedly travel together:

```text
Patient ZIP
× Encounter
× Observation
× Transaction
```

The facts have not disappeared.

But their ability to remain independently represented has been reduced.

A careful phrase for that is:

> **Dense materialization can reduce effective representational dimensionality by forcing independently varying semantic states to co-vary.**

Translation:

> **If you glue enough separate facts together, eventually everything has to move together even though reality doesn't.**

The 180-row ZIP result is a clean example of that phenomenon inside this experimental apparatus.

---

# 11. Strongest interpretation so far

Not:

> Canonical is good. Bespoke is bad.

Not:

> Sparse databases are faster.

Not:

> We proved oscillator theory applies to healthcare databases.

The stronger interpretation is:

> **Representation determines which parts of reality are allowed to vary independently and which parts become coupled by convenience.**

The experiment now has three different readouts:

```text
machine readout
How much relationship traversal is needed?

state readout
How much materialized state must move together?

human readout
How much relational traversal does a person perform?
```

The new result is that the **state side is no longer merely suggestive**. The grain experiment did exactly what the topology predicted:

```text
1.5× redundancy
      ↓
introduce two independent child grains
      ↓
4.11× redundancy

and

1 vs 4 ZIP propagation
      ↓
same basic layout, richer grain
      ↓
1 vs 180
```

That is a real result within this experiment.

And the intuitive version may be simpler than the fancy vocabulary:

> **“I like redundancy until I don't.”**

Redundancy and coupling are not inherently bad. They buy coordination and convenience.

The question is:

> **When does useful connection turn into unnecessary synchronization?**

That is the current center of the experiment.

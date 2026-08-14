# Words That Are Doing More Work Than They Look Like

**Structured Sparsity Experiment — Important Words, Ideas, and History**  
**Date:** 2026-08-14  
**Branch:** `experiment/structured-sparsity`

## Why this document exists

Some words in this project are being used normally, but **densely**.

A word like *human*, *fancy*, *reality*, or *cognition* may look casual while actually carrying several distinctions that accumulated through the experiment.

This is not an attempt to invent private jargon for its own sake. Quite the opposite. The goal is to make explicit what has already become implicit.

The experiment itself follows the same rule:

> Hold reality constant. Change representation. Ask what survives.

The vocabulary should get the same treatment.

---

## Fancy

**Ordinary meaning:** elaborate, sophisticated, impressive.

**Here:** a word that compresses a more exact technical idea.

When I call something a **fancy word**, I usually do **not** mean the word is bullshit or unnecessary. I mean:

> There is a technical term here that says this more precisely, but I need to understand the mechanics underneath it before I let the word carry the meaning for me.

So:

- **topology** is fancy for: the pattern of what can be connected to what.
- **semantic invariance** is fancy for: the meaning survived even though I changed the representation.
- **multiplicative fan-out** is fancy for: two separate “many” relationships got flattened together and multiplied.

A fancy word is therefore a kind of **semantic compression**.

It is useful only after the decompressed meaning is understood.

This distinction showed up explicitly when I objected to an explanation by saying:

> “Topological is a fancy word. Try again with more mechanics.”

and then asked to define oscillator network, state, dependency, coupling, and phase evolution from the ground up.

---

## Simple

**Not:** dumbed down.

**Here:** stripped of unnecessary intermediate machinery.

A simple explanation preserves the mechanism while discarding details that are not needed to understand that mechanism.

A simple cognition task is similar.

The goal is not to make the participant demonstrate cleverness. It is to remove everything except the cognitive operation being measured.

Hence:

```text
BIRD → BLUE
What goes with BIRD?
```

The simplicity is a feature of the experimental instrument.

---

## Basic

Similar to *simple*, but slightly different.

**Basic** means close to the primitive operation underneath a more complicated behavior.

“Basic cognition” in this experiment does not mean rudimentary intelligence.

It means something closer to:

> perceive a relationship → recover it → respond.

The experiment deliberately moved away from puzzles toward this primitive relational lookup.

---

## Raw

**Here:** measured with as little interpretive machinery around it as we can reasonably manage.

“Raw cognitive sensor” does not mean there is literally no mediation. Obviously there is a screen, a terminal, text, a keyboard, instructions, and a task.

It means we try not to add domain knowledge, puzzles, memory games, arithmetic, clever distractors, unnecessary wording, or interface confusion.

The cleaner the task, the more confidently we can say that the remaining signal came from the relationship between **human + representation + requested relation**.

---

## Human

This one is unusually dense.

Sometimes *human* means a biological person.

Sometimes in this project it means:

> an embodied information-processing system capable of perceiving a representation and recovering relationships from it.

That is why the human can be treated as another **readout** attached to the same experiment:

```text
generated reality
      ↓
representation
      ↓
human
      ↓
response
```

This does **not** mean “humans in general.”

Right now the human experiment is one person.

So **human readout** means “measurement obtained through a human interaction with the representation.” It does not mean a universal property of Homo sapiens has been discovered.

---

## Cognition

**Not:** intelligence.

**Not:** IQ.

**Not:** knowledge.

**Not even necessarily:** conscious reasoning.

Here, cognition means:

> the processing required for a human to recover a requested relationship from a representation.

That can include seeing, distinguishing, visually searching, recognizing, compressing, matching, traversing, selecting, and responding.

This matters because I discovered that I was reading only the last few characters of a UUID.

That was not an escape from cognition.

That **was cognition**.

I had discovered that the full identifier contained more information than the local task required, so I reduced it to a discriminating feature and operated on that smaller representation.

Fancy version:

> **task-dependent lossy compression preserving discriminative information.**

Normal version:

> I only needed the last three characters, so that's what my brain used.

---

## Sensor

A **sensor** here is anything that turns some property of the system into an observable measurement.

The database workloads are sensors.

The ZIP mutation test is a sensor.

The reaction-time test is a sensor.

The human is part of a sensor.

So “raw cognitive sensor” means:

> a deliberately boring task whose output changes if the representation imposes different human processing costs.

The word emphasizes that the purpose is **measurement**, not evaluation of the person.

---

## Material reality

This is probably one of the most important ones.

**Material reality** means:

> the actual state of things and relationships that exists prior to the particular representation being used to describe it.

In MediLacra, this is especially clean because we literally generate the synthetic reality **before** storing it.

We have:

```text
Patient
Encounters
Observations
Transactions
relationships among them
```

Then we choose how to represent those facts.

Canonical and bespoke are therefore not two realities.

They are two **representations of one generated material reality**.

There is an important wrinkle, though:

> Representations are themselves material things.

A database layout occupies storage, causes computation, constrains queries, generates maintenance obligations, and affects human behavior.

So the distinction is not:

```text
reality = physical
representation = imaginary
```

It is:

```text
represented reality
        versus
the material system used to represent it
```

Both are real.

They are real in different ways.

---

## Reality

In this experiment, *reality* usually means **ground truth**, not “ultimate metaphysical reality.”

More precisely:

> the generated set of facts and relationships that both representations are obligated to preserve.

This is why semantic equivalence comes before performance.

If canonical says one thing and bespoke says another, we are no longer comparing two ways of representing the same reality.

One of them has changed it.

---

## Meaning

This may be the single densest ordinary word in the whole project.

Meaning is not primarily “what this word means in English.”

Here it is relational.

> **Meaning is what must remain true when information changes form.**

If:

```text
Observation O17
belongs to Encounter E3
whose attending provider is Dr. Smith
```

then another representation can rename columns, rearrange tables, duplicate facts, nest them, flatten them, or serialize them into HL7.

But if it now says that O17 belongs to Dr. Jones, something meaningful failed to survive.

So meaning is very close to:

> **preserved relationships.**

That connects directly to the mathematical idea of an **invariant**.

---

## Semantic

**Semantic** means “having to do with preserved meaning,” particularly preserved relationships.

Thus:

**semantic equivalence** means:

> these representations may look different, but for the question being tested they say the same thing.

**semantic defect** means:

> the representation has altered a relationship that matters.

**semantic interoperability** means something stronger than transporting identical symbols:

> the relevant relationship survives the transformation.

This is why “transport does not guarantee meaning” keeps showing up elsewhere in the MediLacra work.

---

## Representation

A representation is:

> a deliberately selected structure that makes some features of reality explicit while leaving others implicit, compressed, duplicated, or absent.

There is no neutral representation.

Canonical makes independence explicit.

Bespoke makes certain combined relationships explicit.

Those choices have consequences.

Representation is therefore not just cosmetics.

It changes what is local, what must be traversed, what must be repeated, what must remain synchronized, what humans notice, and what software can cheaply ask.

---

## Model

A **model** is a representation with rules.

It does not merely contain symbols representing things.

It establishes what kinds of things exist within the model and what relationships among them are permitted.

A model therefore always throws something away.

The useful question is:

> Did it throw away something required to preserve the behavior or meaning we care about?

---

## Ontology

Fancy word.

Here it means:

> the set of things the system treats as existing, plus the kinds of relationships it permits among those things.

Patient.

Encounter.

Observation.

Transaction.

Those are ontology.

So is:

```text
Observation belongs to Encounter.
Encounter belongs to Patient.
```

An ontology is not merely vocabulary.

Once software operates against it, ontology becomes **operative**.

The system behaves as though those distinctions are real.

---

## Materialize

This one matters because database people can use it casually.

Here:

> **to materialize a relationship means to make it physically present in stored state rather than reconstructing it when needed.**

Canonical:

```text
Observation → Encounter
Encounter → Provider
```

Bespoke ORU activity:

```text
Observation → Provider
```

The latter relationship existed semantically in both systems.

But bespoke **materialized** it.

That makes retrieval easier.

It also creates another state that must remain true.

---

## Coupling

The original technical meaning comes from oscillator systems.

There, coupling is the mechanism and strength by which one oscillator's current state can influence another oscillator's evolution.

In MediLacra, coupling is an analogue at another layer:

> one represented state cannot be recovered or changed correctly without involving another represented state.

We've split it into at least two forms.

**Query coupling**

> Things that must be traversed together to answer something.

**State coupling**

> Things that must change together to continue representing the same fact.

Potentially now:

**Cognitive coupling**

> relationships a human must traverse together to recover an answer.

The database relationship is **not literally an oscillator coupling**.

The common question is:

> Which states are permitted or required to influence one another?

---

## Dependency

Broader than coupling.

A dependency exists when:

> one operation or state requires information from another state.

Every coupling implies some kind of dependency in the way we're using these words.

Not every dependency needs to be treated as strongly coupled.

---

## Topology

Fancy word.

It does **not** mean “how many tables.”

Here it means:

> the pattern of relationships: what connects to what, through what path, and with what branching structure.

Two systems can contain the same number of things but have very different topologies.

And two systems with the same apparent high-level topology can behave differently when the **grain** changes.

---

## Grain

Grain answers:

> What does one instance of this fact describe?

A patient fact is at patient grain.

An encounter fact is at encounter grain.

An observation fact is at observation grain.

A transaction fact is at transaction grain.

This sounds boring until independent grains get flattened together:

```text
5 observations
×
5 transactions
=
25 combinations
```

Then grain becomes destiny. 😹

---

## Fan-out

When one relationship branches into several represented states.

**Multiplicative fan-out** happens when independent branches are combined:

```text
5 × 5 = 25
```

This is why one patient ZIP could ultimately require 180 bespoke rows to change in the 1/5/5/5 experiment.

---

## State

State is:

> enough information about a system at a particular moment to describe the part of its condition relevant to what happens next.

In an oscillator, state is physical/dynamical.

In MediLacra, state is represented clinical reality.

In the ZIP test:

```text
patient ZIP = 01852
```

is one piece of semantic state.

If that one fact exists physically in 180 materialized rows, we have one semantic fact but many stored states that must co-vary.

---

## Dimension / dimensionality

This is another dangerous fancy word.

Here it does **not** mean number of columns.

A dimension is closer to:

> a way in which the represented reality can vary independently.

Observation and transaction are separate dimensions because an encounter can acquire a new observation without necessarily acquiring a new transaction, and vice versa.

If a representation repeatedly glues those independent dimensions together, it reduces their **representational independence**.

That gives us the cautious bridge to the sparsity paper:

> dense coupling can reduce effective dimensionality by making independently capable states behave together.

And our analogue:

> dense materialization can reduce effective representational dimensionality by forcing independently varying semantic states to co-vary.

Translation:

> Glue enough things together and eventually they have to move together even when reality doesn't.

---

## Redundancy

Not automatically bad.

Redundancy means:

> information representing the same underlying fact exists in more than one place.

Sometimes this is useful.

It can make reads easy, improve resilience, preserve recovery options, make local work understandable, and avoid repeated traversal.

The question is when redundancy stops buying enough value to justify the synchronization burden.

Hence:

> **“I like redundancy until I don't.”**

That is almost a plain-language statement of the non-monotonic hypothesis.

Too little connection can be bad.

Too much connection can be bad.

There may be a useful middle.

---

## Messiness

Related to redundancy, but more developmental.

A little messiness means:

> temporary duplication, overlap, or imperfect consolidation that preserves optionality while the system is still changing.

Mess is not the desired end-state.

But premature cleanup can destroy useful information before we know what matters.

So:

> **messiness can be epistemically useful.**

Fancy version.

Normal version:

> Don't clean up the crime scene before you've figured out what happened.

---

## Sparse / sparsity

Not:

> few things.

Not even:

> few tables.

Here:

> fewer active or obligatory relationships among possible relationships.

Structured sparsity adds:

> don't merely delete relationships randomly; preserve the ones that carry useful coordination.

So the question is never simply:

> Can we remove connections?

It is:

> Which connections are actually necessary to preserve the behavior we care about?

---

## Invariant

Fancy but extremely useful.

An invariant is:

> something that stays the same while something else changes.

Our main invariant:

```text
represented healthcare reality
```

Our intervention:

```text
relationship topology / representation
```

Our measurements:

```text
meaning
query work
state propagation
human readout
```

---

## ISO-state

This is basically shorthand for our experimental move:

> hold state constant while changing structure around it.

It isn't meant to pretend this is a formal dynamical-systems equivalence.

It is an experimental discipline:

```text
same reality
different representation
```

---

## Preserve

Another ordinary word doing technical work.

To **preserve** something means:

> allow transformation while keeping a chosen invariant intact.

We are not trying to preserve every byte.

We are trying to preserve **meaningful relationships**.

This is why compression, transformation, normalization, denormalization, HL7 serialization, and human shorthand can all preserve meaning despite being visibly different.

---

## Physical / physicality

When I call something physical, I mean:

> it exists through actual material processes rather than as a purely abstract relation.

An oscillator has physicality.

A database also ultimately has physicality: voltage, storage, memory, clocking, circuits, heat, electrons, etc.

But that does **not** mean a database foreign key is literally an oscillator coupling.

The useful discipline is to describe each level using mechanics appropriate to that level.

---

## Operational

Something is operational when:

> it changes what the system actually does rather than merely how someone describes it.

A category written in an essay is descriptive.

A category encoded into a workflow, schema, policy, model, or decision rule becomes operational.

This becomes important when we get to Baudrillard.

---

# Representation Becomes Operative: Why Baudrillard Belongs Here

Baudrillard belongs here, but **not** because this experiment proves Baudrillard, and not because the bespoke tables should be called simulacra.

The useful connection is more basic.

The old Keanu Reeves essay was already interested in classification, signs, and the possibility that representations can stop merely reflecting reality and begin structuring what is accepted as reality.

The structured-sparsity experiment comes at the problem from almost the opposite direction.

We deliberately create a ground truth first:

```text
material/generated reality
         ↓
representation A
representation B
```

That gives us a reference point against which representations can be tested.

But then something very Baudrillard-ish happens.

Once the representation becomes operational, it starts producing consequences of its own.

A ZIP code that semantically exists once can, because of the model, become:

```text
180 materialized obligations
```

The representation did not change the patient's ZIP.

But it changed the **material consequences of that ZIP existing**.

Similarly, a model determines what is easy to see:

```text
bespoke:
Observation → Provider
```

versus what must be reconstructed:

```text
canonical:
Observation → Encounter → Provider
```

So the representation is no longer passive.

It structures visibility, work, synchronization, computation, cognition, and eventually action.

That gives us a useful tension:

> **Baudrillard asks what happens when the model precedes the real. This experiment deliberately holds a real constant so we can watch the model begin to exert causal force anyway.**

A representation does not have to become false in order to become powerful.

> **It only has to become operative.**

That is one of the strongest bridges between the old Keanu essay and this experiment.

---

# Recovered Experiment Prompt History

## Note on completeness

The earlier saved experiment documents preserve selected prompt histories rather than a forensic export of every single message. The sequence below merges every experiment-driving prompt recoverable verbatim from the saved records and the current conversation. It should therefore be treated as the fullest reconstructed history available here, not as a guarantee that no older prompt was omitted from an earlier record.

### P1

> Fuck it, let's dive into it! Can you grab this page?  
> https://unconv.ai/blog/less-is-more-scaling-dynamics-with-sparsity/

### P2

> ISO, eh?  
> Let's map it out. What's going on with me at a healthcare organization is the data. Use the data to help me understand the post concepts

### P3

> How do oscillator couplings work? I know what an oscillator is, I had a bunch in my lab at WUML. I visualized the waves with oscilloscopes

### P4

> And the couplings induce the phase, which is the speed of the wave cycle, because each wave has a physicality to it, energy that impacts each other?

### P5

> Ok, you said almost. Can you fix what I said, changing only what is needed to present the meaning?

### P6

> Can I demonstrate this principle with Medilacra? Maybe iterators during generation. Route it to 2 ingestion dbs. 1 with a large number of bespoke tables. One with standard Medilacra output. Run the same queries on each and measure the performance. Change the grain, run it again.
>
> Don't get excited. I want to keep this at a level I can understand

### P7

> Ok, let's figure out the minimal changes needed to Medilacra to design this year. Check the GitHub repo, give me some options for a structured Sparsity branch

### P8

> Let's do option 1. Does that preserve enough meaning to be useful as a conceptual test of sparcity?

### P9

> Yeah, let's do this one
>
> 1 patient  
> 5 encounters  
> 5 observations per encounter  
> 5 transactions per encounter
>
> Also, document the experiment design history test results up to now and create a MD. Include the full prompt history at the end.

### P10

> Could we loop in my own cognition into the data? Multiple choice, 1-4, of basic cognition of how relationships are displayed using heterogenous but semantically unique data. Testing basic human reaction time.

### P11

> No, that's too specific. Basic cognition

### P12

> Ok you're losing me. The cognitive test should be something any human could Intuit in less than 5 seconds

### P13

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

### P14

> Now design the experiment. At the end of the "Generated ..." print let's include 5 prompts like the ones we just identified for each data model. record the correctness, reaction time, anything else relevant. Log the results in a separate output

### P15

> Write the code

### P16

> Ok how fucking wild is this? I heard about this a couple hours ago

### P17

> What databases don't have physical oscillator dependencies somewhere down the line? 🙃

### P18

> oscillator networks and databases are both physical information-processing systems, and we can ask the same topological question of each: which interactions are necessary to preserve the behavior we care about?
>
> This feels like slop. It's emotional at the end, it throws in some generic definitions. Topological is a fancy word. Try again with more mechanics

### P19

> Fuck, we've gotta go deeper... Define oscillator network, state, dependency, coupling, phase evolution in a way I can understand

### P20

> Add that to the doc along with my prompt history. Print it

### P21

> Cool, I like redundancy until I don't. A little messiness is good 😊

### P22

> Give me the simple instructions to test this out locally

### P23

> Can you give me the updated scripts in a zip?

### P24

> Ok, let's review the results

### P25

> Yeah to me the tests were all the same. I read the last 3 characters of the observation, matched it to the observation or ORU_activity row, then looked at the corresponding name in either Encounters or in the ORU_ACTIVITY section

### P26

> You weren’t really reasoning about the model; you were doing **string matching and visual lookup**.
>
> ...what's the difference? I think it's been good so far

### P27

> Yeah, I don't want these to be puzzles, just raw cognitive sensors

### P28

> Here's the latest results

### P29

> Lol I'm still waking up a bit, I smoked a lot of weed yesterday 🤣. But I think we should add an intro to the testing. Instead of dropping right in, print the basic instructions, tell the user to take a breath, tell them this isn't an intelligence quiz and that they can relax, then have them press 1 2 3 4 in order to begin

### P30

> It'll be curious to try again when I've woken up a bit more 😅

### P31

> Yeah, a pre test of straight reaction time without reasoning would be good. Press any key when a message appears or something

### P32

> Let's add it

### P33

> ok, it's been a while since I synced my git to my desktop. I've been manually adding files locally. However, I didn't have a medilacra folder on the C drive so I just created that. give me the commands I need to sync the latest experiment stuff we have to that folder from powershell

### P34

> Here's the output. I'm thinking for the 1-4 testing we should clear the screen, it was hard to determine where the last question ended and the new one began

### P35

> Here's a re-run of the cognition experiment

### P36

> This question confused me

### P37

> k, fix the error and commit, then I'll git pull it

### P38

> Just confirming before I do another round
>
> [git pull output]

### P39

> Here's the output. Let's see all the results we've collected so far, a change log, prompt history, hypotheses, and potential interpretations. But, like, don't sound like a total nerd. Write it in a way I can understand it, even if you have to put commentary next to fancy language. The fancy language is good to include too, so I can see how the concepts tie back to the original sparsity paper

### P40

> Very very good. Publish and date this in the github repo branch

### P41

> We should add an addendum where we define words I use weirdly but in a semantically dense way, like fancy, material reality, human, potentially cognition. There may be others? Also include my entire prompt history for the addendum. I feel like we should also mention Beaudrillard? Let's see it here in chat first

### P42

> Perfect, add this to the repo. But not through an addendum, maybe call it... Important_Experiment_Words_Ideas_And_History_8.14.2026? Unless you've got something more clever

---

# A Pattern in the Prompt History

The vocabulary did not arrive as a glossary. The definitions emerged through correction.

There is a recurring pattern:

```text
technical word appears
        ↓
I try to restate it mechanically
        ↓
we notice where the explanation is still too abstract or wrong
        ↓
I reject the abstraction
        ↓
we find the smallest concrete operation
        ↓
the technical word becomes useful again
```

That is why **fancy** deserves to be the first definition.

The fancy words are not decorating the work.

They are **indexes into mechanics we have already unpacked**.

And that is also why Baudrillard belongs here. The whole experiment keeps returning to the gap between **a sign, what it represents, and what starts happening once systems treat the sign as real**.

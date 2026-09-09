# MediLacra — Caregiver Health Baseline Phase 1 Build Analysis

**Document type:** Build analysis / provenance / lessons learned  
**Project:** MediLacra — Gravity Caregiver Health Baseline  
**Phase:** Phase 1  
**Document version:** v0.1  
**Project date:** 2026-09-08  
**Branch:** `feature/gravity-caregiver-baseline-v0.1`  
**Branch base:** `connectathon/piqi-43`  
**Primary plan:** `docs/gravity/CAREGIVER_HEALTH_BASELINE_PHASE_1_PLAN_v0.1_2026-09-08.md`  
**Build history:** `docs/gravity/CAREGIVER_HEALTH_BASELINE_PHASE_1_BUILD_HISTORY_v0.1_2026-09-08.md`  
**Latest verified implementation result at time of analysis:** **12 passed, 1 warning**  

---

# 0. Verbatim Prompt Log

This section preserves the user prompts that materially shaped the feature and this analysis. They are reproduced verbatim from the build conversation so later readers can distinguish original requirements from retrospective interpretation.

## Prompt 0.1 — Caregiver as medical status

> Being a caregiver is a medical status and should be tracked accordingly. What's 5 meaningful metrics for their health?

## Prompt 0.2 — Collapse the assessment to a boring baseline

> 1- hours slept is fine. We're not doing a sleep study
> 2-pain scale is fine to start, 1-10. Make s note to come back and find a non crappy/confusing pain metric that includes people with chronic pain. 
> 3- PHQ is fine, only the most basic questions
> 4- too vague. Make a note to revisit later. Let's put heart rate here. 
> 5-confusing. Replace it with a basic medication reconciliation
>
> I'm thinking these could all be structured as a questionnaire. UI in Medilacra Streamlit, assigned to a synthetic patient, stored as structs, null flavor for fields not answered or declined or corrupt. Questionnaire is the functionality being introduced for Gravity Project. I could create this as an SDOH extension, materialize the FHIR questionnaire bundle, send it through PIQITT to validate the heart rate, med codes, standard clinical SAM. Send to my IRIS FHIR server 

## Prompt 0.3 — Reuse the standard machinery

> Gravity gives us the questionnaire/extraction infrastructure.
>
> Of course 😹 lol why would we build something that's already built and agreed upon? 
>
> Ok, let's see the project plan here. Questions should be pretty much textbook. We only need to create a baseline, fancy stuff can come later

## Prompt 0.4 — What code actually needs to exist?

> What code needs to be written? Keep it high level, nothing here is complicated

## Prompt 0.5 — Corrections before implementation

> 1- good enough
> 2- add a button for decline
> 3-make sure you didn't make those up. Use data classes that already exist in the standard
> 4-yup 
> 5- yup, nice and boring 
> 6- make this a little more stupid. Plausibility before metrics
> 7-yup, and this can be phase 2. I need to get IRIS running on my new machine. 
>
> I think you're ready, but give me the full updated plan here first. All the trimmings. Include a glossary of important relevant terms

## Prompt 0.6 — Implementation instruction

> Go create the branch and build phase one. Add this as the initial project plan on docs. Date and version it, all the trim. Take your time. Reuse before generating new code

## Prompt 0.7 — Medication grain correction acknowledged

> That violated the actual grain of the interaction—the caregiver knows what medication they take; they are not a terminology server. I removed i
>
> Nice catch 🦾
>
> . I won't pretend otherwise. 
>
> Good. Though an odd hill to die on 😹😹💖
>
> Add the build history to an MD in docs, trim and decision log

## Prompt 0.8 — Why was the build so easy?

> Phew. The long, arduous build process is complete 🤣🤣🤣🤣 why was this so easy? What context and materialized data did you pull from?

## Prompt 0.9 — This analysis

> Lol add this as a build analysis in docs, prompt log at the top. Note that I caught you making up data classes- that would have been ugly to detangle later. New MD

---

# 1. Executive Analysis

Phase 1 was easy because very little of the expensive work was actually software construction.

The feature arrived after most of the semantic and architectural decisions had already been made in conversation, prior MediLacra work, the Gravity workgroup lineage, and the existing repository.

The implementation therefore did not need to answer broad questions such as:

- What is the clinical subject?
- What is the grain of the interaction?
- What counts as a missing value?
- What resource represents the form?
- What resource represents the completed form?
- What should become an Observation?
- What should represent a self-reported medication?
- How should Bundle references be normalized?
- How should synthetic patients be created and persisted?
- How should the feature appear in the application?
- What does PIQITT care about first?

Most of those answers already existed.

The build was mainly an integration exercise:

```text
materialized requirements
        +
existing MediLacra runtime/data
        +
existing FHIR/Gravity machinery
        +
existing Connectathon normalization
        +
small new glue layer
        =
Phase 1
```

The main reason the build stayed small was not coding speed. It was disciplined refusal to create new abstractions where existing ones were already adequate.

---

# 2. The Expensive Work Happened Before the Build

The requirements were unusually mature before implementation began.

By the time code was written, the following had already been fixed by direct user decisions:

```text
caregiver = the person being assessed
questionnaire = the capture mechanism
QuestionnaireResponse grain = one completion at one time
sleep = hours slept
pain = simple numeric baseline
PHQ = PHQ-2 only
heart rate = basic current pulse
medication reconciliation = basic self-report
explicit decline must survive distinctly
corrupt input must not silently become a value
plausibility comes before scoring/metrics
IRIS round trip = Phase 2
```

Several seductive but unnecessary extensions had also been explicitly deferred:

```text
NO caregiver risk score
NO sleep study
NO advanced chronic-pain model yet
NO adaptive questionnaire
NO longitudinal analytics
NO AI interpretation
NO Monarch operationalization
NO IRIS dependency in Phase 1
NO generalized caregiver relationship model as a blocker
```

This substantially reduced implementation uncertainty.

A developer starting from a ticket reading only "add caregiver questionnaire support" would have had to rediscover many of these decisions. In this build, they were already materialized as conversational constraints before the first branch commit.

---

# 3. Context Sources Actually Used

The build drew from four distinct context layers.

## 3.1 Current build conversation

The conversation supplied the narrow product contract.

Most important contributions:

- caregiver health should be represented as healthcare data;
- the first instrument should be deliberately basic;
- the interface should be a Streamlit questionnaire;
- answers should attach to an existing synthetic Patient;
- explicit refusal must be capturable;
- missing, declined, and corrupt values must remain distinguishable;
- the first quality question is plausibility, not a composite score;
- IRIS should not block local Phase 1 completion;
- standard machinery should be reused wherever it already exists.

This was the highest-authority source for product behavior.

## 3.2 Wider MediLacra project context

Prior work supplied the architectural worldview:

```text
reality
   ↓
representation
   ↓
transformation
   ↓
validation
```

The caregiver questionnaire did not require a new philosophy. It became another controlled representation/transformation path inside an existing one.

Relevant established MediLacra concepts included:

- synthetic healthcare entities already exist;
- the project cares about what relationships survive transformation;
- PIQITT is concerned with semantic preservation and conformance;
- SDOH context is already treated as part of the synthetic healthcare reality;
- UI execution through Streamlit is already a normal project pattern;
- Connectathon work already created a FHIR-control path.

This context mattered because it changed the implementation question from:

> How should questionnaire software work?

into:

> Where does the already-standardized questionnaire pattern attach to MediLacra?

That is a much smaller problem.

## 3.3 Materialized repository code

The implementation inspected and reused actual repository artifacts rather than coding from remembered architecture alone.

### Existing synthetic patient machinery

Reused:

- `hl7_demo.models.Patient`
- `hl7_demo.generators.gen_patient()`
- existing demographic generation
- existing patient IDs
- existing patient persistence

This meant the caregiver questionnaire did not need a new person generator or parallel caregiver population.

### Existing reference/scenario machinery

Existing ZIP/city/state reference loading and scenario-profile behavior were available as part of the surrounding synthetic-data system.

They were not rewritten for the caregiver feature.

### Existing DuckDB machinery

Reused:

- database path conventions;
- patient table initialization;
- patient upsert;
- reader/writer patterns;
- local single-file persistence model.

Only questionnaire-specific persistence needed to be added.

### Existing Streamlit application

The caregiver workflow was added as another MediLacra page.

No second application shell, routing system, or frontend stack was introduced.

### Existing Connectathon FHIR normalization

The largest direct implementation reuse was:

- `connectathon.fhir_control.prepare_control_bundle()`

That existing function already handled:

- Bundle cleanup;
- stable `fullUrl` generation;
- local reference rewriting;
- self-contained collection-Bundle normalization.

The caregiver feature therefore did not create another FHIR identity/reference policy.

### Existing quality patterns

The Connectathon/PIQITT work already established the style of local validation:

- inspectable checks;
- explicit structural assertions;
- terminology checks;
- reference consistency;
- semantic comparison;
- no need for a magical aggregate score.

The caregiver quality gate is a small specialization of this existing approach.

## 3.4 Existing standards

A substantial amount of behavior came directly from standards instead of local invention.

FHIR already provides the relevant resource and datatype vocabulary:

```text
Patient
Questionnaire
QuestionnaireResponse
Observation
MedicationStatement
Bundle
Quantity
Coding
CodeableConcept
Reference
DataAbsentReason
```

Gravity/SDC already provides the capture/extraction pattern:

```text
Questionnaire
      ↓
QuestionnaireResponse
      ↓
structured clinical representation
```

LOINC provides standardized clinical concepts for the baseline where appropriate.

UCUM provides computable units.

RxNorm provides medication terminology.

The implementation's job was therefore mostly to preserve and connect existing semantics.

---

# 4. Materialized Data Reused During the Build

The phrase "reuse before generating new code" also applied to data.

## 4.1 Existing synthetic Patients

The Streamlit page reads the existing MediLacra `patients` table.

The interaction is:

```text
existing synthetic Patient
        ↓
select Patient
        ↓
complete caregiver questionnaire
```

If no Patient exists, the UI uses the existing `gen_patient()` + `upsert_patient()` path.

No new caregiver-specific master table or generator was needed.

## 4.2 Existing patient demographics and identifiers

The new QuestionnaireResponse refers to the existing synthetic Patient identity.

The feature does not clone demographics into a new caregiver object.

## 4.3 Existing database file

Questionnaire responses are persisted beside the existing MediLacra data in DuckDB rather than in a second storage engine.

New materialized artifacts are limited to the new feature's actual needs:

```text
FHIR Questionnaire
FHIR QuestionnaireResponse
FHIR Observation(s)
FHIR MedicationStatement(s)
FHIR Bundle
questionnaire persistence/projection in DuckDB
```

## 4.4 Existing Bundle semantics

The caregiver Bundle inherits reference/fullUrl handling from the Connectathon work.

That prior materialized code eliminated an entire category of new edge cases.

---

# 5. What Was Context Only, Not a Runtime Dependency

Several prior project domains informed design without being pulled into the Phase 1 execution path.

The build did **not** depend on:

- HL7 v2 ADT messages;
- ORU generation;
- DFT generation;
- encounters;
- orders;
- transactions;
- care-recipient relationship modeling;
- external SDOH enrichment at questionnaire runtime;
- IRIS;
- FHIR endpoint availability;
- Touchstone;
- Monarch Model implementation;
- advanced Reality Model work.

This distinction matters.

A large project context can make a build easier without every contextual artifact becoming a runtime dependency.

The implementation stayed small partly because relevant context was used to make decisions, not automatically imported into the dependency graph.

---

# 6. The Dataclass Near-Miss

This is the most important design correction in the build and should remain visible in the project history.

Before implementation, the assistant proposed custom intermediate objects approximately like:

```text
CaregiverAssessment
AssessmentResponse
MedicationResponse
```

The user immediately challenged this:

> "make sure you didn't make those up. Use data classes that already exist in the standard"

They had, in fact, been made up.

The proposal was withdrawn before those classes became the canonical model.

## 6.1 Why the custom classes were attractive

They would have looked tidy locally:

```text
Streamlit
   ↓
CaregiverAssessment
   ↓
AssessmentResponse
   ↓
FHIR QuestionnaireResponse
```

They also would have made it easy to add application-specific fields and Python typing.

That tidiness was misleading.

## 6.2 Why they would have been ugly to detangle later

The standard already had the semantic objects we needed.

Adding bespoke assessment classes would have created an unnecessary canonical layer between the human interaction and FHIR.

That would have introduced several forms of debt.

### Duplicate semantics

We would need local definitions for concepts FHIR already defines:

- questionnaire identity;
- answer cardinality;
- item hierarchy;
- answer datatype;
- subject reference;
- response status;
- authored time;
- missingness semantics.

### Extra mappings

Every field would require mapping twice:

```text
UI
 ↓
local assessment class
 ↓
FHIR QuestionnaireResponse
```

Instead of:

```text
UI
 ↓
FHIR QuestionnaireResponse
```

### Extra persistence contract

The local classes would likely become the stored canonical representation.

That would force future code to decide whether the truth is:

- the custom object;
- the FHIR resource;
- the extracted Observation;
- or some reconciliation of all three.

### Extra tests

We would need to prove not only that QuestionnaireResponse → Observation preserves meaning, but also:

```text
UI → custom model
custom model → QuestionnaireResponse
QuestionnaireResponse → clinical resources
```

The first extra transformation would exist solely because we invented it.

### Migration debt

Once other code began importing `CaregiverAssessment`, deleting it later would require:

- changing constructors;
- changing persistence;
- changing tests;
- changing UI state handling;
- potentially migrating stored records;
- reconciling local and FHIR cardinalities;
- deciding which behavior was accidental and which had become relied upon.

The correction happened before that layer hardened.

## 6.3 The resulting rule

For this feature:

> **FHIR Questionnaire and QuestionnaireResponse are the canonical assessment objects unless a demonstrated requirement proves an internal adapter is necessary.**

This does not mean MediLacra can never use local domain classes.

It means a new class must earn its existence by representing semantics not already adequately carried by the standard object in the current use case.

## 6.4 Why this mattered more than the amount of code involved

The custom classes would have been easy to write.

That was the danger.

They could have been implemented in minutes and cost hours or days later once they became part of storage, UI, tests, and downstream transformations.

The user correction removed future complexity before it became visible as technical debt.

---

# 7. The Medication-Grain Catch Was the Same Kind of Problem

A second near-miss occurred during the build.

An early questionnaire design exposed an RxNorm code field to the caregiver.

That was technically possible and semantically wrong for the interaction.

The corrected grain is:

```text
caregiver knows/reports medication facts
             ↓
QuestionnaireResponse preserves human report
             ↓
terminology normalization happens downstream
```

The caregiver is not a terminology server.

This correction reinforced the same broader lesson as the dataclass correction:

> **Do not move system responsibilities upstream merely because doing so makes downstream code easier.**

A cleaner developer interface is not automatically a more truthful representation of reality.

---

# 8. Why the Build Was So Easy

The build can be reduced to five reasons.

## 8.1 The ontology was already constrained

The conversation decided the meaning before code had to infer it.

## 8.2 The standard already defined the central objects

There was no need to invent questionnaire semantics.

## 8.3 MediLacra already had the person, storage, UI, and synthetic-data machinery

The feature attached to existing infrastructure instead of creating a new application.

## 8.4 Connectathon work had already solved FHIR Bundle normalization

Reference handling did not have to be rediscovered.

## 8.5 PIQITT's first question was deliberately kept stupid

The quality layer asks things like:

```text
Did 82 bpm stay 82 /min?
Did pain 4 stay pain 4?
Did a declined question remain declined?
Did corrupt text fail instead of becoming a number?
Did an incomplete PHQ-2 avoid generating a fake total?
```

It does not yet ask for a synthetic caregiver wellness index, longitudinal risk model, or probabilistic interpretation.

The absence of unnecessary sophistication is a feature of Phase 1.

---

# 9. Build Economics

The build demonstrates an important project property:

> **Materialized context reduces future compute and design cost.**

Prior work had already paid for:

- synthetic identity;
- patient generation;
- database wiring;
- app structure;
- FHIR normalization;
- quality philosophy;
- Connectathon conventions;
- Gravity research;
- the conceptual distinction between source reality and transformed representation.

The caregiver feature consumed those prior outputs as reusable material.

The cost profile therefore looked like:

```text
EXPENSIVE
thinking clearly across prior sessions
reading standards/workgroup material
building general MediLacra infrastructure
building Connectathon FHIR controls
settling project philosophy and semantics

CHEAP
add Questionnaire
render form
capture QuestionnaireResponse
extract a few clinical resources
persist
run dumb checks
```

This is exactly what reusable architecture is supposed to do.

The feature did not become easy because healthcare interoperability is easy.

It became easy because the relevant interoperability decisions and infrastructure were already present and reusable.

---

# 10. Counterfactual: What Would Have Made This Hard?

Phase 1 would have expanded dramatically if any of the following had been accepted as requirements:

- invent a proprietary questionnaire schema;
- create a parallel caregiver identity model;
- make IRIS availability a Phase 1 blocker;
- build a terminology service;
- require automated RxNorm search/autocomplete;
- implement full SDC/StructureMap execution before any local transformer;
- build adaptive branching;
- implement caregiver-to-care-recipient relationship graphs immediately;
- score caregiver risk;
- create clinical decision support from abnormal values;
- solve chronic-pain measurement properly in v0.1;
- build longitudinal trend analysis;
- create a generic form designer;
- invent a new quality metric framework;
- treat every piece of broader MediLacra context as a runtime dependency.

Any one of these might be valid later.

None was necessary to answer the Phase 1 question.

---

# 11. What Was Actually New

The genuinely new implementation surface is small.

```text
FHIR caregiver-health Questionnaire
Streamlit caregiver questionnaire page
QuestionnaireResponse capture helpers
DataAbsentReason handling for explicit decline/error
small deterministic clinical extraction layer
QuestionnaireResponse DuckDB persistence/projection
caregiver-specific local plausibility/conformance checks
small caregiver test suite
caregiver smoke workflow
```

Everything else is composition.

That distinction is useful when estimating future MediLacra extensions.

A new domain does not automatically imply a new architecture.

If the domain can be expressed through existing entities, standards, storage, and transformation machinery, most of the work may be configuration plus narrow glue.

---

# 12. Testing as Proof of Smallness

The final verified implementation run completed with:

- **12 tests passed**;
- **1 pre-existing warning**;
- backend and Streamlit smoke coverage;
- no Phase 1 test failure.

The test suite focuses on recognizable facts rather than elaborate metrics.

Representative assertions include:

```text
heart rate 82 → Observation 82 /min
pain 4 → pain Observation 4
PHQ 1 + 0 → PHQ total 1
explicit sleep decline → asked-declined
corrupt heart-rate text → error, not Observation
heart rate 190 → plausible representation, not automatically invalid
pain 47 → fails baseline plausibility
incomplete PHQ components → no derived PHQ total
known medication text → verified RxNorm normalization downstream
unknown medication text → remains text, no fabricated code
```

The tests reflect the project's central question:

> Did the meaning survive the transformation?

---

# 13. Provenance of the Build Conclusions

This analysis distinguishes evidence from interpretation.

## Directly evidenced by repository state

- feature branch exists;
- it is based on `connectathon/piqi-43`;
- caregiver Phase 1 code and documentation exist;
- existing `Patient` generation/persistence is reused;
- existing Connectathon Bundle normalization is reused;
- a Streamlit page exists;
- Questionnaire/QuestionnaireResponse/Observation/MedicationStatement/Bundle are emitted;
- questionnaire response persistence exists;
- CI has completed successfully at the verified implementation head;
- the verified run produced 12 passed tests and one warning.

## Directly evidenced by conversation

- caregiver status should be treated as medically relevant;
- the baseline questions were intentionally simplified by the user;
- explicit decline was requested;
- the user challenged the proposed custom dataclasses;
- the user requested standard objects instead;
- plausibility was prioritized before metrics;
- IRIS was explicitly deferred to Phase 2;
- reuse before new code was an explicit implementation instruction.

## Interpretation / architectural analysis

The claims that:

- semantic decisions were the expensive part;
- materialized context reduced build cost;
- custom dataclasses would have created avoidable migration debt;
- the build is primarily glue rather than new architecture;

are retrospective architectural interpretations supported by the above evidence.

They should not be confused with standards requirements.

---

# 14. Lessons for Future MediLacra Work

## L-001 — Search for the existing semantic object before naming a new class

Before adding a domain object, ask:

```text
Does FHIR already represent this?
Does Gravity/another IG already represent this?
Does MediLacra already represent this?
Is this actually a new concept, or just a new use of an existing concept?
```

The custom-dataclass near-miss is the concrete example.

## L-002 — Preserve the grain of the human interaction

Do not ask a human to provide machine-normalized data merely because the terminology field is convenient downstream.

The RxNorm-field removal is the concrete example.

## L-003 — Separate source evidence from derived representation

Keep QuestionnaireResponse even after materializing Observations.

The extracted resource is not a replacement for the capture event.

## L-004 — Reuse does not mean importing everything

Use prior context to choose the right boundary.

Do not turn every relevant project artifact into a dependency.

## L-005 — Make the baseline embarrassing in its simplicity

A boring baseline provides a stable control.

Fancy logic can be compared against it later.

## L-006 — Plausibility before metrics

First ask whether the artifact is coherent and recognizable.

Score it only when a score answers a real question.

## L-007 — Make user corrections durable

The user catching an invented abstraction is not merely conversational feedback.

It belongs in the decision/provenance record because it changed the architecture before code hardened around the mistake.

---

# 15. Compact Dependency Graph

```text
                         PRIOR MATERIALIZED WORK

      MediLacra Patient / generators / demographics
                         │
                    DuckDB storage
                         │
                existing Streamlit app
                         │
          Connectathon FHIR control / PIQITT
                         │
                         ▼
             ┌─────────────────────┐
             │   CAREGIVER v0.1    │
             └─────────────────────┘
                         │
                  FHIR Questionnaire
                         │
                  Streamlit capture
                         │
                QuestionnaireResponse
                         │
                deterministic extraction
                         │
              ┌──────────┴──────────┐
              ▼                     ▼
         Observation         MedicationStatement
              │                     │
              └──────────┬──────────┘
                         ▼
                 Bundle normalization
                         │
                         ▼
               plausibility/conformance
                         │
                         ▼
                   persisted evidence

                         │
                         │ PHASE 2
                         ▼
                    IRIS FHIR server
```

---

# 16. Final Build Analysis

The Phase 1 caregiver feature was easy for the right reason.

It did not require MediLacra to become a new system.

It required MediLacra to recognize that several systems already existed:

- Gravity had a questionnaire pattern;
- FHIR had the resource model;
- LOINC/UCUM/RxNorm had terminology/unit machinery;
- MediLacra already had synthetic people, persistence, and UI;
- the Connectathon branch already had FHIR Bundle normalization;
- PIQITT already had a philosophy for checking whether meaning survived transformation.

The feature therefore became a narrow connection among existing nodes.

The two most valuable build corrections were also both acts of subtraction:

1. the user caught the assistant inventing custom assessment dataclasses before they hardened into a local canonical model;
2. the medication interaction was corrected so the caregiver reports medication facts while terminology normalization remains a system responsibility.

Both corrections prevented technically convenient representations from replacing the actual grain of reality being modeled.

The result is not impressive because it contains a large amount of novel code.

It is useful because it contains very little code that did not need to exist.

```text
Think about it correctly.
Reuse what already survived.
Write the missing glue.
Test the boring facts.
Stop.
```

That is the Phase 1 build.
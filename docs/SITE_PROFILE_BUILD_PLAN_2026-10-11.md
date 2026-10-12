# Site Profile — Unified Site + HL7 Interface Profile Build Plan

**Date:** 2026-10-11  
**Branch:** `site-profile`  
**Status:** approved for MVP build

## Purpose

Extend MediLacra's existing Site/Scenario profile into one unified JSON profile that describes both:

1. **the site's synthetic world** — facilities, departments, visit mix, routing, and probability weights; and
2. **the site's HL7 interface dialect** — how selected clinical concepts are expressed for specific HL7 message semantics.

This is intentionally small. The first slice profiles only:

- **MRN value** — PID-3.1
- **Assigning Authority** — PID-3.4
- **Date of Birth** — PID-7
- **PV1-44 semantic meaning** — scoped to the observed message type/trigger/structure
- **MSH-9.1 / MSH-9.2 / MSH-9.3** — message code, trigger event, and root message structure

## Existing Site Profile behavior to preserve

The current Site & Scenario Setup model already defines:

- facilities and locations,
- departments/service lines,
- visit-class probability weights,
- visit-class -> location-type routing weights,
- concrete location weights,
- preview generation.

Those values already drive synthetic encounter generation through the newer unified pipeline.

The new profile keeps that behavior and adds interface metadata beneath the same profile. It does not create a second profile universe.

## Profile grain

Meaning is not inferred from field path alone.

The profile key is conceptually:

```text
site/interface
+ MSH-9.1 message code
+ MSH-9.2 trigger event
+ MSH-9.3 root message structure
+ HL7 field path
-> semantic meaning
```

This matters especially for PV1-44, whose operational meaning may differ by message semantics.

## MSH-9 behavior

MediLacra already generates MSH-9.3 for known message types:

```text
ADT^A01 -> ADT^A01^ADT_A01
ORU^R01 -> ORU^R01^ORU_R01
DFT^P03 -> DFT^P03^DFT_P03
ORM^O01 -> ORM^O01^ORM_O01
```

The interface profiler will preserve all three MSH-9 components and attempt to resolve MSH-9.3 against MediLacra's existing IRIS-derived HL7 registry.

## Old specification concepts retained

Only the old column ontology is retained:

- Transaction Dictionary Message
- Recommended Format
- Data Element Destination
- Forerun Verification

No old row-level mappings are reused.

For this MVP, those concepts become machine-readable JSON fields.

## JSON direction

New unified profiles are written as JSON.

Existing YAML site/scenario profiles remain readable for compatibility. This branch does not require bulk conversion of old YAML files.

Machine-legible explanatory metadata may be stored in ordinary JSON fields such as:

- `description`
- `notes`
- `rationale`
- `assumptions`
- `constraints`
- `provenance`

## MVP workflow

```text
Select/load site profile
        |
Paste or upload HL7 v2 messages
        |
Split messages
        |
Read MSH-9.1 / 9.2 / 9.3
        |
Group by exact MSH-9 triplet
        |
Observe:
  PID-3.1
  PID-3.4
  PID-7
  PV1-44
        |
Resolve MSH-9.3 against existing HL7 registry when available
        |
Show counts / coverage / transient examples
        |
Human confirms semantic mappings
        |
Save unified JSON site/interface profile
```

Raw source messages are not persisted into the profile by default.

## Build structure

```text
profiles/
  site_profile.py
  hl7_interface_profile.py

pages/
  5_Site_and_Scenario_Setup.py

data/
  scenario_profiles/
    *.yaml        # legacy readable
    *.json        # new preferred format
```

No new application layer is required.

## Phase 1 — Profile storage extraction

Move load/save/list/validation concerns out of the Streamlit page into `profiles/site_profile.py`.

Requirements:

- load existing YAML profiles,
- load new JSON profiles,
- save new profiles as JSON,
- preserve the existing site/generation keys,
- add an `interfaces` object without breaking old profiles.

## Phase 2 — Canonical HL7 path extraction

Add `profiles/hl7_interface_profile.py`.

Reuse existing message splitting where safe, but implement explicit field extraction with correct MSH numbering.

The analyzer must correctly extract:

- MSH-9.1
- MSH-9.2
- MSH-9.3
- PID-3.1
- PID-3.4
- PID-7
- PV1-44

Tests must cover MSH's special field numbering and multiple messages in one input.

## Phase 3 — Message grouping and evidence

Group samples by exact MSH-9 triplet.

For each group, report:

- total messages,
- observed value count per target field,
- coverage percentage,
- a small transient set of example values,
- whether MSH-9.3 resolves to the existing HL7 registry.

Observed evidence and standard metadata remain separate.

## Phase 4 — Interface mapping model

Store a small mapping block beneath each exact message type.

Initial semantic concepts:

- `mrn`
- `assigning_authority`
- `date_of_birth`
- `pv1_44_meaning`

MRN and Assigning Authority are presented as one conceptual identifier mapping in the UI, while retaining their separate paths.

PV1-44 meaning is explicitly human-confirmed per message semantics.

## Phase 5 — Site Admin UI

Extend the existing Site & Scenario Setup page with one new tab:

```text
Facilities & Locations
Departments
Visit Mix & Routing
Interface Profile
Validate & Preview
```

The Interface Profile tab provides:

- paste/upload HL7,
- Analyze,
- detected MSH-9 triplets,
- root-schema resolution,
- field coverage,
- transient examples,
- editable mapping confirmation,
- save through the unified JSON site profile.

The Streamlit page remains a thin client over the profile/analyzer modules.

## Phase 6 — Generate & Persist compatibility

Restore/use unified profile loading in Generate & Persist so the selected profile carries the existing site distribution behavior.

This MVP does **not** yet build a general arbitrary HL7 serializer. The interface mappings are captured and persisted first.

A later slice may use those mappings to alter generated message destinations after this profile model is proven.

## Security / data handling

Input messages may contain PHI.

For this MVP:

- analyze source messages in memory,
- do not save raw HL7 into the profile,
- do not persist sample values by default,
- persist only paths, counts, mappings, message semantics, schema-resolution metadata, and verification statistics.

## Acceptance criteria

The branch is successful when MediLacra can:

1. load an existing site profile,
2. accept a batch of pasted/uploaded ADT messages,
3. distinguish exact MSH-9 triplets,
4. resolve known MSH-9.3 structures against the existing registry when available,
5. report PID-3.1, PID-3.4, PID-7 and PV1-44 coverage,
6. allow the human to confirm those mappings / PV1-44 meaning,
7. save one unified JSON site/interface profile,
8. reload it without loss,
9. preserve the existing site probability/routing behavior.

That is the whole first slice. No generic mapping engine, database, semantic inference, drag-and-drop designer, or interface-engine rewrite.


## Implementation status — 2026-10-11

The first site/interface profile slice is built.

Implemented:

- new branch `site-profile`, based on `experiment/shn-mvp0`;
- unified JSON profile storage in `profiles/site_profile.py`;
- legacy YAML profiles remain readable;
- new/edited profiles save as JSON;
- existing facilities, departments, visit-mix, routing, and location-weight behavior is preserved;
- HL7 interface analyzer in `profiles/hl7_interface_profile.py`;
- exact MSH-9.1 / MSH-9.2 / MSH-9.3 grouping;
- correct special MSH field numbering;
- PID-3.1 MRN observation;
- PID-3.4 Assigning Authority observation;
- PID-7 DOB observation;
- PV1-44 observation scoped to exact message semantics;
- root MSH-9.3 resolution against the existing IRIS-derived HL7 v2.5 registry;
- transient examples are available only on explicit UI reveal and are not persisted;
- persistable mappings use the retained old column ontology:
  - Transaction Dictionary Message,
  - Recommended Format,
  - Data Element Destination,
  - Forerun Verification;
- Site Admin now has an **Interface Profile** tab;
- Generate & Persist and the main generator both load unified JSON profiles as well as legacy YAML;
- Generate & Persist again passes the selected site's existing probability/routing model into the unified pipeline.

During testing, the existing IRIS schema loader was found to expect title-case XML attributes while the real export uses lower-case attributes such as `name` and `structure`. The loader now reads attributes case-insensitively, which allows `ADT_A01` and other root structures to resolve correctly.

### Explicit boundary

This slice captures and persists the observed interface profile. It does **not** yet implement a general arbitrary field-destination serializer.

The selected unified profile already drives the site's existing encounter/location probability model during generation. The new interface mappings are stored alongside it so the next serialization slice can consume them without redesigning the profile.

### Automated regression

GitHub Actions on the completed code/test head:

```text
76 passed in 1.67s
Connectathon smoke tests: success
```

Coverage includes:

- MSH-9 special numbering,
- exact message-semantic grouping,
- shared ADT_A01 root resolution across A01/A08,
- PID-3.1 / PID-3.4 / PID-7 / PV1-44 extraction,
- PV1-44 verification scoped by message semantics,
- removal of PHI-like example values from persisted interface records,
- JSON save/reload,
- legacy YAML loading,
- preservation of existing site probability behavior.

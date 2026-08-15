# MediLacra at a Glance

MediLacra is a synthetic healthcare data and integration simulator. It generates a synthetic patient reality first, then uses that reality for storage, testing, and healthcare interoperability artifacts.

## Core generated entities

The current model already has first-class representations for:

- Patient
- Encounter
- Observation
- Transaction

It also generates and reuses healthcare identities such as patient/MRN, encounter/visit/account, placer/filler order identifiers, observation identifiers, and transaction identifiers.

## What it can generate

MediLacra already contains generators or reference-data support for:

- demographics and patient identity
- encounters, timestamps, locations, classes, and services
- providers
- orders and order identifiers
- observations and clinical results
- transactions and financial data
- vitals and labs
- SDOH/contextual data
- Gender Harmony data
- scenario-driven facilities, departments, visit distributions, and routing

## Healthcare interoperability

MediLacra includes HL7 v2 generation and schema tooling. Its IRIS HL7 schema parser can extract:

- messages
- segments
- ordered fields
- datatypes and components
- coded tables
- requiredness
- repetition

The current pipeline can translate generated healthcare state into HL7 artifacts rather than making the HL7 message itself the source of truth.

## Persistence and identity

DuckDB persistence supports patient, encounter, observation, transaction, and order data with identity indexes and relationships among those records.

Earlier MPI/linkage work also treats MRN, visit, account, accession, placer, and filler identifiers as linkage keys, providing a base for more explicit identity modeling.

## Current architectural direction

The main architectural gap is not generating healthcare facts. MediLacra already does that in many places.

The next step is making those existing facts, generators, identities, relationships, constraints, and events share one explicit semantic reality.

Conceptually, the current pipeline is roughly:

```text
entity generator
    ↓
dataclass
    ↓
HL7 / storage
```

The developing Reality Model moves toward:

```text
semantic requirement
    ↓
existing generator / fact / relationship
    ↓
shared reality state
    ↓
existing dataclasses + downstream outputs
```

The governing boundary is simple:

> **Generate reality once. Downstream representations may format or materialize it, but they should not invent it.**

## Why MediLacra works as the structured-sparsity test rig

Because synthetic reality is generated before the experiment materializes it, the exact same patient, encounter, observation, and transaction state can be written into multiple database layouts.

That lets the experiment hold the represented reality constant while changing relationship structure and measuring:

- semantic preservation
- query traversal
- materialized row count
- change propagation
- local runtime
- human relationship-recovery time

The structured-sparsity experiment therefore changes the **representation**, not the synthetic reality being represented.

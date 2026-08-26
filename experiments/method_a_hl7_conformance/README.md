# Method A — Heterogeneous HL7 Conformance

## Question

Can several heterogeneous storage representations of the same synthetic MediLacra ADT reality be normalized into one inspectable canonical event representation without destroying the raw evidence or its source lineage?

This is intentionally a primitive experiment. It is not a production ingestion framework and it does not reproduce any external system.

## Synthetic reality

The runner reuses MediLacra's existing `Patient` and `Encounter` generators and existing HL7 segment builders. Each generated encounter is projected into a minimal ADT containing MSH, EVN, PID, and PV1.

The exact same message set is then written to three deliberately boring source surfaces:

- `source_alpha.csv` — `record_id`, `payload`, `received_at`
- `source_beta.jsonl` — `message_id`, `message_text`, `created_at`
- `source_gamma.duckdb` — `raw_id`, `hl7`, `receive_ts`

The point is not exotic source behavior. The point is that representation-specific naming and storage exist before semantic conformance.

## Registry

`source_registry.json` tells the runner how to find three source responsibilities:

- source record identity
- raw payload
- source timestamp

The loader uses that registry to produce a common raw shape:

```text
source_name
source_record_id
source_timestamp
raw_payload
```

The original payload remains intact.

## Canonical projection

Each raw HL7 message is parsed into a deliberately small event shape:

```text
source_name
source_record_id
source_timestamp
patient_id
event_type
patient_class
visit_number
admit_datetime
discharge_datetime
```

The experiment therefore separates:

```text
synthetic encounter reality
        ↓
HL7 representation
        ↓
three source storage representations
        ↓
common raw evidence
        ↓
canonical event representation
```

## Validation

The MVP checks only what is required to establish the pattern:

1. all three sources contribute the expected number of records;
2. raw lineage is present on every canonical row;
3. critical canonical fields are populated;
4. patient/visit pairs reconcile to the MediLacra entities that generated the messages;
5. source record identities remain unique within their source.

The result is written to `validation.json`.

## Run

From the repository root:

```bash
python experiments/method_a_hl7_conformance/run_experiment.py
```

Small run:

```bash
python experiments/method_a_hl7_conformance/run_experiment.py --records 3
```

Generated artifacts are written under `experiments/method_a_hl7_conformance/output/` by default.

## What this establishes

A source-specific representation can be treated as evidence rather than as the canonical model. Storage variation is isolated in a small registry/adapter boundary, the raw payload survives, and a shared semantic representation can be reconciled back to the synthetic reality that produced it.

## What this does not establish

This MVP does not test incremental processing, streaming, enterprise orchestration, performance at scale, schema evolution, retry behavior, or full HL7 conformance. Those are later interventions if the primitive pattern proves useful.

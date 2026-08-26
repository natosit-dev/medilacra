# Method B — Workflow Reconstruction from Fragmented Evidence

## Question

Can a coherent operational workflow model be recovered from fragmented synthetic artifacts that do not individually contain the whole workflow?

This experiment is deliberately small. It recreates the reasoning problem, not a mature enterprise workflow platform.

## Starting evidence

`generate_sources.py` writes five independent synthetic source artifacts:

- `tasks.json`
- `actions.json`
- `forms.json`
- `appointments.csv`
- `staff.csv`

`SOURCE_NOTES.md` represents the incomplete documentation available before reconstruction.

The notes correctly name the three workflow types but omit important behavior:

- the source data contains a valid `canceled` state;
- `SOCIAL_SUPPORT` has a more specific specialist assignment field;
- closure forms connect to workflows through an action object;
- appointment staff can disagree with task assignment.

## Reconstruction

`reconstruct.py` materializes one row per workflow instance into `workflow_detail.csv`.

The reconstructed table makes previously fragmented relationships explicit:

```text
Staff --------- Workflow Task -------- Appointment
                     |
                     v
                   Action
                     |
                     v
                    Form
```

The central contract is:

```text
one row = one workflow_id
```

The reconstruction includes:

- workflow type and state;
- effective staff assignment and the field that supplied it;
- deterministic due status;
- appointment presence and assignment reconciliation;
- two-hop closure linkage;
- closure form type and outcome.

`RECONSTRUCTED_MODEL.md` is the durable semantic description produced by the reconstruction step.

## Run

From the repository root:

```bash
python experiments/method_b_workflow_reconstruction/reconstruct.py
```

The default run regenerates the source artifacts before reconstructing the model. Use `--skip-generate` to reconstruct an existing fixture set.

The default `as_of` time is fixed for reproducibility:

```text
2026-08-05T12:00:00
```

Override it with:

```bash
python experiments/method_b_workflow_reconstruction/reconstruct.py --as-of 2026-08-06T12:00:00
```

## What this establishes

The operational object can be more coherent than any individual source artifact. Grain, lifecycle, assignment precedence, cross-system reconciliation, and closure semantics can be made explicit in a durable model rather than remaining distributed across tables and tribal knowledge.

## What this does not establish

The reconstruction is an inferred model. It has not yet been validated as correct merely because it can be built. The next branch attacks these assumptions with an explicit validation and correction loop.

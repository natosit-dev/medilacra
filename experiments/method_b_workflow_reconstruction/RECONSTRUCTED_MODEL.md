# Reconstructed Workflow Model

This document records the model materialized from the fragmented synthetic source artifacts. It is the current inferred model, not the original source notes.

## Grain

One row represents one `workflow_id`.

## Workflow types

- `CARE_FOLLOWUP`
- `MEDICATION_REVIEW`
- `SOCIAL_SUPPORT`

## Lifecycle

Observed source data contains four states:

```text
queued -> active -> complete
             \-> canceled
```

`canceled` is therefore part of the observed system even though it was omitted from the initial source notes.

## Assignment resolution

The generic task owner is not always the effective assigned staff member.

- `CARE_FOLLOWUP` -> `owner_id`
- `MEDICATION_REVIEW` -> `owner_id`
- `SOCIAL_SUPPORT` -> `specialist_staff_id` when populated, otherwise `owner_id`

The materialized table records both the resolved staff identity and `assignment_source` so the rule remains inspectable.

## Closure relationship

Forms do not join directly to workflows.

The observed relationship is:

```text
form submission
      |
      | action_id
      v
workflow action
      |
      | workflow_id
      v
workflow task
```

The reconstructed detail therefore follows a two-hop join:

```text
forms.action_id -> actions.action_id -> actions.workflow_id
```

## Appointment reconciliation

Appointments are linked to the same synthetic patient. The materialized model compares `scheduled_staff_id` with the reconstructed effective assigned staff member.

Possible values:

- `MATCH`
- `MISMATCH`
- `NO_APPOINTMENT`

This is reconciliation evidence, not proof that a mismatch is operationally wrong.

## Due status

For open work:

- due date before the experiment `as_of` date -> `OVERDUE`
- due date on the `as_of` date -> `DUE_TODAY`
- future due date -> `SCHEDULED`
- absent due date -> `NO_DUE_DATE`

Completed or canceled work is `CLOSED`.

The `as_of` timestamp is explicit so repeat runs do not silently change historical results.

## Materialized output

`workflow_detail.csv` contains the recovered operational model, including:

- workflow identity and type
- lifecycle state
- resolved assignment and assignment source
- due status
- appointment relationship and staff reconciliation
- closure action
- closure form and outcome

## Remaining uncertainty

The current source artifacts do not contain effective-dated staff employment history. The model can resolve the staff record present in the synthetic directory, but it cannot prove whether that person was organizationally active at the exact instant each task was created. That question belongs in validation as `NOT_TESTABLE` until another source exists.

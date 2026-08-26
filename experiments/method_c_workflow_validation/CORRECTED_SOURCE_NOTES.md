# Corrected Source Notes — Synthetic Workflow System

These notes supersede the lifecycle and assignment statements in `method_b_workflow_reconstruction/SOURCE_NOTES.md` after validation against the synthetic source artifacts.

## Workflow types

- `CARE_FOLLOWUP`
- `MEDICATION_REVIEW`
- `SOCIAL_SUPPORT`

## Lifecycle

Observed evidence supports four states:

```text
queued -> active -> complete
             \-> canceled
```

The original notes omitted `canceled`. Validation treats that contradiction as a documentation correction, not as a pipeline defect.

## Assignment

The effective assigned staff field depends on workflow type:

- `CARE_FOLLOWUP` -> `owner_id`
- `MEDICATION_REVIEW` -> `owner_id`
- `SOCIAL_SUPPORT` -> `specialist_staff_id` when populated; otherwise `owner_id`

## Appointment reconciliation

Appointments are patient-linked external evidence. The scheduled staff member is compared with the reconstructed effective assignee.

Possible reconciliation values:

- `MATCH`
- `MISMATCH`
- `NO_APPOINTMENT`

A mismatch is evidence for review. It is not automatically classified as an operational defect.

## Closure forms

Closure forms connect to workflows through workflow actions:

```text
forms.action_id -> actions.action_id -> actions.workflow_id
```

Completed and canceled workflows in the current fixture have a resolvable closure form through that path.

## Evidence boundary

The current staff source has identity and role but no effective-dated employment history. Whether an assignee was organizationally active at the exact workflow creation timestamp cannot be established from the current evidence and must remain `NOT_TESTABLE`.

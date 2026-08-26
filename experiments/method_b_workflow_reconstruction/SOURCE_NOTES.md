# Source Notes — Synthetic Workflow System

These notes represent the incomplete documentation available before reconstruction. They are intentionally not guaranteed to be correct.

## Declared workflow types

- `CARE_FOLLOWUP` — general follow-up work after a healthcare event
- `MEDICATION_REVIEW` — medication review by clinical staff
- `SOCIAL_SUPPORT` — social-support referral work

## Declared lifecycle

Tasks move through:

```text
queued -> active -> complete
```

## Assignment

Each task contains an `owner_id` identifying the assigned staff member.

## Appointments

Appointments are stored separately from tasks. They can be associated to the same patient but the notes do not define whether the scheduled staff member must match the task owner.

## Closure forms

Completed work may have a closure form. The notes do not document the join path between a workflow and its form submission.

## Known documentation gaps

- exact closure linkage
- whether workflow types have assignment exceptions
- cancellation behavior
- scheduling mismatch semantics

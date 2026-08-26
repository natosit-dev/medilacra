# Method D — Workflow Operationalization

## Question

Can the reconstructed and validated synthetic workflow model become an interface that another person can actually inspect and operate without reading the reconstruction code first?

This branch is stacked on:

```text
method-b-workflow-reconstruction
        ↓
method-c-workflow-validation
        ↓
method-d-workflow-operations
```

It does not create a new workflow model. It is deliberately a thin interface over the artifacts produced by B and C.

## Interface

`app.py` provides five small Streamlit tabs:

### Operations

- total workflow count
- open workflow count
- overdue count
- appointment mismatch count
- workflow type/state filters
- wide operational queue

### Metrics

Table-first summaries for:

- workflow type × state
- workflow type × due status
- workflow type × appointment reconciliation status

No charts are required for the first round. The point is operational legibility, not visualization polish.

### Validation

Shows the latest Method C checks with status, interpretation classification, and evidence.

The UI explicitly preserves the distinction between a failed check and a pipeline defect.

### History

Shows the append-only validation history produced by repeated Method C runs.

### How It Works

Renders the reconstructed semantic model and the evidence-backed corrected source notes directly inside the operational interface.

## Run

From the repository root:

```bash
streamlit run experiments/method_d_workflow_operations/app.py
```

If Method B/C outputs do not exist, the app builds them automatically. The `Rebuild synthetic evidence` button reruns reconstruction and validation and appends a new validation-history run.

## Design boundary

The UI contains no independent workflow semantics. Assignment precedence, closure joins, due-status derivation, and validation logic remain in the upstream experimental layers.

That separation is intentional:

```text
fragmented evidence
       ↓
reconstruction
       ↓
validation/correction
       ↓
operational interface
```

The interface exposes the model; it does not secretly redefine it.

## What this establishes

A reconstructed data model becomes more useful when its operational view, quality state, history, and plain-language semantics are available together. The next person can inspect what the system believes, why it believes it, what failed validation, and what remains uncertain without reconstructing the reasoning from code.

## What this does not establish

This MVP has no authentication, writeback, scheduler, production deployment, alerting, custom visualization layer, or clinical decision support. Those concerns are outside the current experiment.

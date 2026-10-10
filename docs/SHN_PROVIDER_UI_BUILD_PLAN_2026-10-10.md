# SHN Provider ePA Workbench — build plan

**Date:** 2026-10-10  
**Branch:** `experiment/shn-mvp0`  
**Status:** approved for build

## Goal

Turn the successful MediLacra provider-side SHN experiment into a thin Streamlit workbench without moving healthcare or workflow logic into the UI.

The provider workflow remains:

```text
MediLacra reality
  -> CRD
  -> payer-selected DTR
  -> QuestionnaireResponse materialized from reality
  -> PAS
  -> payer decision / authorization
```

The live payer response controls branching. A scenario that stops after CRD must not be forced through DTR or PAS.

## Architecture

```text
Streamlit provider UI
        |
        | thin calls only
        v
ProviderWorkflow
        |
        +-- CRD module
        +-- DTR module
        +-- PAS module
        +-- SHN transport client
        +-- artifact/provenance handling
        |
        v
JSON scenario configuration
```

Transaction mechanics live in Python modules. Clinical/test differences and expected behaviors live in data configuration.

The UI is not the source of truth. It renders workflow state and artifacts produced by the provider modules.

## Configuration decision: JSON

New SHN scenario configuration uses JSON, not YAML.

Reasons:

- PIQI already uses JSON artifacts.
- FHIR and SHN request/response payloads are JSON.
- JSON avoids YAML scalar ambiguity for identifiers such as `"00301"`.
- JSON maps directly to Python dictionaries and JavaScript objects.
- JSON Schema provides a portable machine-readable contract.
- JSON is straightforward to canonicalize, hash, diff and preserve as provenance.

Human explanation is not discarded. Commentary is represented as data so machines can retain and expose it:

```json
{
  "description": "Synthetic provider-side prior authorization scenario.",
  "notes": [
    "Used for CRD -> DTR -> PAS testing.",
    "Questionnaire answers must come from explicit MediLacra reality facts."
  ],
  "rationale": "Exercises a documented route-00301 authorization path.",
  "assumptions": [],
  "constraints": [],
  "provenance": {
    "date": "2026-10-10",
    "source": "MediLacra SHN MVP-0"
  }
}
```

These fields are part of the JSON configuration contract rather than parser-only comments.

Existing YAML configuration elsewhere in MediLacra is not removed by this work. JSON is the default for this new provider scenario system and the preferred direction for new configuration work.

## Proposed repository shape

```text
connectathon/
  shn_provider/
    __init__.py
    client.py
    workflow.py
    state.py
    artifacts.py
    summaries.py
    crd.py
    dtr.py
    pas.py
    scenario.py
    scenario_registry.py

  shn_scenarios/
    schema.json
    lumbar_fusion.json
    explicit_not_covered.json
    no_rule_default.json

pages/
  10_SHN_Provider_ePA.py
```

The existing tested `connectathon/shn_*.py` experiment modules remain available during extraction. Reuse precedes replacement.

## Build phases

### 1. Freeze working behavior

The existing evidence is the compatibility baseline:

```text
CRD: 100/100 semantic success when admitted
DTR: 34/34 identity + package success
QR:  34/34 successful materialization
PAS: 34/34 A1 + authorization + no CommunicationRequest
```

The refactor must preserve semantic identity for the same seed and scenario.

### 2. Python SHN transport client

Extract transport responsibilities currently proven in the shell runners:

- client-credentials token acquisition and in-memory refresh,
- base endpoint configuration,
- authenticated POST,
- caller-supplied correlation IDs,
- response correlation and SHN leg IDs,
- trace URL construction,
- HTTP 429 Retry-After/backoff,
- structured transport result.

The client must never expose or persist the client secret or bearer token.

### 3. Transaction modules

`crd.py` owns generic provider CRD request/response mechanics.

`dtr.py` owns questionnaire-package request mechanics and fail-closed QuestionnaireResponse materialization.

`pas.py` owns PAS request/response mechanics.

Scenario-specific codes, diagnoses, questionnaire mappings and expected decisions must not be embedded in the Streamlit page.

### 4. JSON scenario registry

Create a JSON Schema plus the three currently proven route-00301 scenarios:

- lumbar-fusion authorization,
- explicit not-covered,
- no-rule/default.

A small Python registry maps stable configuration names such as `"lumbar_fusion"` to existing reality builders. Config contains names, not executable Python references.

Questionnaire mappings are data:

```text
payer linkId
  -> exact text/type contract
  -> MediLacra fact path
  -> semantic name
```

Unknown required questions, changed text/type, missing facts or identity drift remain fail-closed.

### 5. First-class workflow state

Create a provider case object containing:

- scenario and seed,
- reality,
- CRD request/response/summary,
- DTR request/response/summary,
- materialized QuestionnaireResponse and provenance,
- PAS request/response/decision,
- transport metadata,
- errors and completion/stop reason.

ProviderWorkflow exposes explicit stage methods and `run_to_completion()`.

Live payer output, not scenario expectation alone, determines whether DTR/PAS is entered.

### 6. Artifact layer

Persist inspectable artifacts independent of Streamlit:

```text
case/
  manifest.json
  reality.json
  crd/
    request.json
    response.json
    summary.json
    transport.json
  dtr/
    request.json
    response.json
    summary.json
    questionnaire_response.json
    materialization.json
    transport.json
  pas/
    request.json
    response.json
    decision.json
    transport.json
```

Generated/live provider artifacts remain gitignored.

### 7. Thin Streamlit page

Replace the stale `pages/10_SHN_MVP0.py` demo-transform page with a provider ePA workbench.

The page may:

- select scenario and seed,
- create a case,
- build/run the next stage or run to completion,
- display normalized workflow state,
- display question -> reality fact -> answer provenance,
- display correlation/leg IDs and trace links,
- display/download raw artifacts,
- run and summarize a cohort.

The page must not implement CRD, DTR, PAS, token, retry, clinical inference or branching logic.

### 8. Regression

Run offline unit tests against the extracted modules and compare request semantics to existing tested builders.

Then re-run a live seed-300 end-to-end workflow through the Python client before using the new UI for live demos.

The existing shell runners remain available as an independent known-good transport control.

## Non-goals for this slice

Do not build:

- a general credential-management UI,
- a database-backed job system,
- a generic payer administration console,
- a custom visualization framework,
- a general FHIR validator UI,
- a universal DTR form engine,
- new clinical inference.

The workbench is a provider-side client over already-proven MediLacra reality and SHN transactions.

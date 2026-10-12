# SHN Reference Test Suite — Build Plan

**Date:** 2026-10-12  
**Branch:** `experiment/shn-mvp0`  
**Scope:** TP-01 through TP-05 plus TN-01 through TN-10  
**Security scope:** minimal protocol/security hygiene only; this is not a security upgrade.

## Goal

Extend the provider-side MediLacra SHN workbench from a small set of clinical scenarios into an executable Connectathon reference test suite.

The new layer must preserve the existing architectural rule:

```text
Streamlit
  -> orchestration
  -> transaction modules
  -> SHN transport

JSON configuration
  -> test data
  -> operation sequence
  -> expected observations

negative mutation
  -> one deliberate break
  -> expected refusal/alternate behavior
```

The UI remains thin. FHIR/Da Vinci mechanics, branching, mutations, response parsing and pass/fail evaluation remain outside Streamlit.

## Source behavior

The staff Connectathon test process defines the target behaviors.

Positive reference tests:

- **TP-01:** route 00301, HCPCS G0151, CRD -> DTR -> PAS A4 + CommunicationRequest -> DTR relaunch by trace -> PAS inquiry.
- **TP-02:** route 00300, HCPCS L8000, CRD names a questionnaire while `doc-needed=no-doc`; DTR returns PriorAuthRequired; PAS returns A1 Certified in total with authorization.
- **TP-03:** route 00300, HCPCS E1390; PAS returns queued/A4 plus Task status requested with attachment-request-questionnaire.
- **TP-04:** route 00300, HCPCS G0151; PAS returns A3 Not Certified.
- **TP-05:** inquiry against both routes plus a no-match inquiry.

Negative tests:

- TN-01 unknown payer -> 422.
- TN-02 unknown member without Coverage -> 422 per staff process.
- TN-03 PAS inconsistent patient linkage -> expected 502 per staff process.
- TN-04 PAS missing Coverage.beneficiary or external-base references -> 200/A3 and no pend.
- TN-05 Claim.patient identifier-only -> documented error behavior; expectation is encoded from the staff process and may be revised if live endpoint differs.
- TN-06 DTR questionnaire version the payer does not carry -> no package / Questionnaire not found.
- TN-07 hook/service mismatch -> expected 400 per staff process.
- TN-08 order-dispatch -> 404.
- TN-09 reused correlation ID -> 502.
- TN-10 expired token -> token rejected; do not invent an exact status if the source does not establish one.

The provider endpoint guide remains useful implementation evidence for request shapes. Where it differs from the staff draft, the runner records the live observation rather than silently rewriting the expected result.

## Architecture

### Existing provider layer remains

```text
connectathon/shn_provider/
  client.py
  workflow.py
  crd.py
  dtr.py
  pas.py
  ...
```

The current MediLacra scenario workflow remains intact.

### New reference-suite layer

```text
connectathon/shn_provider/
  inquiry.py
  reference_payloads.py
  test_case.py
  test_case_registry.py
  reference_suite.py
  mutations.py

connectathon/shn_test_cases/
  schema.json
  tp01_00301_round_trip.json
  tp02_00300_approval.json
  tp03_00300_pend_task.json
  tp04_00300_not_certified.json
  tp05_inquiry.json
  negatives/
    tn01_unknown_payer.json
    tn02_missing_coverage.json
    tn03_bad_patient_linkage.json
    tn04_bad_coverage_reference.json
    tn05_identifier_only_claim_patient.json
    tn06_bad_questionnaire_version.json
    tn07_hook_service_mismatch.json
    tn08_order_dispatch.json
    tn09_reused_correlation_id.json
    tn10_expired_token.json
```

## Data/config rule

A test case is declarative JSON.

It describes:

- test id and label,
- route / Da Vinci line,
- synthetic member,
- service code and display,
- ordered operations,
- optional base case,
- optional named mutation,
- expected HTTP/semantic observation,
- notes, rationale, constraints and provenance.

Python implements the transaction or mutation. JSON selects it.

No executable Python is embedded in config.

## Ordered operations

The current provider workflow has fixed CRD/DTR/PAS fields. Reference tests need repeated operations, so the suite gets a separate first-class operation result:

```text
OperationResult
  operation_id
  operation_type
  request
  response
  summary
  transport
  expected
  passed
  error
```

A reference test result is an ordered list of OperationResults.

This supports:

```text
CRD
DTR
PAS submit
DTR relaunch
PAS inquiry
```

without inventing fields such as `dtr2`.

## Known-good payload construction

Reuse the existing frozen 00301 baseline artifacts:

- `connectathon/shn_live_baseline_00301/crd-00301.json`
- `connectathon/shn_live_baseline_00301/dtr-00301.json`
- `connectathon/shn_live_baseline_00301/pas-00301.json`

Reference payload builders make only explicit test-case substitutions:

- payer route,
- service coding,
- request/bundle identifiers,
- questionnaire canonical returned by live CRD,
- inquiry profiles,
- pend trace/context.

The 00300 tests use the documented reference-payer rule that the Appendix-A PAS request changes route and service coding while retaining the same structural bundle.

## Positive-test implementation

### TP-01

Operations:

1. CRD G0151 / 00301.
2. DTR using exactly the canonical returned by CRD.
3. PAS submit without completed documentation.
4. Extract CommunicationRequest trace identifier.
5. DTR relaunch with Coverage + context trace and no questionnaire.
6. PAS inquiry derived from the submitted PAS bundle.

Assertions include HTTP 200, CRD questionnaire path, A4/Pending, CommunicationRequest, DTR relaunch package, and non-empty inquiry response.

### TP-02

Operations:

1. CRD L8000 / 00300.
2. DTR whenever a questionnaire is present even though `doc-needed=no-doc`.
3. PAS submit L8000 / 00300.

Assertions include PriorAuthRequired and A1 with authorization.

### TP-03

Same 00300 reference structure with E1390. Assert queued/A4 plus requested Task / attachment-request-questionnaire.

### TP-04

Same 00300 reference structure with G0151. Assert A3 Not Certified.

### TP-05

Inquiry runner:

- matching 00301 inquiry,
- matching 00300 inquiry,
- deliberately no-match inquiry.

Inquiry normalizes Parameters/responseBundle responses instead of making the UI understand FHIR bundle structure.

## Negative-test mutation layer

Negative tests start with a known-good payload and apply exactly one named mutation immediately before transport.

Examples:

```text
unknown_payer
remove_coverage
bad_patient_linkage
remove_coverage_beneficiary
identifier_only_claim_patient
bad_questionnaire_version
hook_service_mismatch
order_dispatch
reuse_correlation_id
expired_token
```

The normal builders remain valid-data builders.

The mutation module is deliberately explicit so an invalid test request cannot be mistaken for a normal provider scenario.

## Result evaluation

Each operation records both:

```text
expected
observed
```

and computes pass/fail only for fields the JSON test case actually asserts.

A 200 is not automatically a pass.

Normalized observations include:

- HTTP status,
- CRD covered / pa-needed / doc-needed / questionnaire,
- DTR package/questionnaire/outcome,
- PAS ClaimResponse outcome,
- PAS review action code + display,
- authorization number,
- CommunicationRequest count/payload,
- Task count/status/code,
- inquiry response count,
- OperationOutcome/error text.

## Evidence artifacts

Persist by run:

```text
connectathon/results/shn_reference_suite/
  <run-id>/
    manifest.json
    result.json
    operations/
      01-crd/
        request.json
        response.json
        summary.json
        transport.json
      ...
```

The result manifest carries the Connectathon evidence grain:

- test id,
- route,
- timestamp,
- correlation ids,
- HTTP/outcome,
- pass/fail,
- notes.

## Thin UI extension

Add a fourth tab to `pages/10_SHN_Provider_ePA.py`:

```text
Reference Suite
```

It provides:

- TP/TN case picker,
- short contract/notes display,
- Run test button,
- ordered operation table,
- expected vs observed,
- PASS/FAIL,
- trace buttons,
- raw artifacts in expanders.

No test logic belongs in the page.

## Minimal protocol/security hygiene

This slice does only the following:

1. Normal generated correlation IDs become UUID4 values, matching the Connectathon process.
2. Existing credential files remain ignored and secrets/tokens remain memory-only.
3. Add regression tests proving transport/artifact serialization never includes bearer tokens or client secrets.

No private-key JWT migration, vault, encryption-at-rest project, key rotation framework or other broad security work is part of this build.

TN-09 and TN-10 receive narrow test-only hooks to bypass normal safe behavior:

- TN-09 explicitly supplies the same correlation ID twice.
- TN-10 sends a deliberately stale bearer token without changing normal token acquisition.

## Build order

1. Commit this plan.
2. Add JSON Schema and TP-01 through TP-05 configs.
3. Add TN-01 through TN-10 configs.
4. Add UUID4 correlation IDs and controlled test overrides to the SHN client.
5. Add test-case loader/registry.
6. Add reference payload builders.
7. Add inquiry builder/normalizer.
8. Expand PAS normalization for Task and CommunicationRequest details.
9. Add operation/result models and reference-suite runner.
10. Implement TP-01.
11. Implement TP-02 through TP-04.
12. Implement TP-05 inquiries.
13. Add named mutation layer.
14. Implement TN-01 through TN-10.
15. Add secret/token non-persistence tests.
16. Add reference-suite tests with fake transport.
17. Extend CI.
18. Extend thin Streamlit UI.
19. Run offline regression suite.
20. Leave live Connectathon execution to the local environment holding ignored SHN credentials; record observed differences rather than silently changing expected behavior.


## Implementation status — 2026-10-12

The first reference-suite slice is built.

Implemented:

- TP-01 through TP-05 as declarative JSON test contracts.
- TN-01 through TN-10 as declarative JSON negative-test contracts.
- Reusable reference payload builders over the frozen 00301 known-good CRD/DTR/PAS artifacts.
- Explicit named mutation layer; normal transaction builders remain valid-data builders.
- Ordered `OperationResult` / `ReferenceRunResult` execution model.
- TP-01 CRD -> DTR -> PAS pend -> DTR relaunch -> inquiry orchestration.
- TP-02 00300 L8000 approval orchestration.
- TP-03 00300 E1390 A4 + Task normalization.
- TP-04 00300 G0151 A3 normalization.
- TP-05 matching inquiries on both routes plus a no-match inquiry.
- PAS normalization for CommunicationRequest payloads, Task status/code and authorization.
- Inquiry normalization for Parameters/responseBundle responses.
- UUID4 correlation IDs for ordinary requests.
- Narrow correlation/path/bearer overrides used only by the negative-test harness.
- TN-10 represented as an explicit manual case rather than persisting a token or sleeping five minutes.
- Artifact writer rejects `client_secret`, `access_token`, `bearer_token` and HTTP `Authorization` keys.
- Reference-suite CLI.
- Reference Suite tab in the thin Streamlit provider workbench.
- Offline fake-transport regression coverage for every automated TP/TN case.

GitHub Actions passed after the UI integration:

```text
commit: 3ea26eb053e0f2d2dc1063ee01e626d124337162
workflow: Connectathon smoke tests
conclusion: success
```

### CLI

Run an individual live case:

```bash
python -m connectathon.shn_provider.reference_run TP-01
python -m connectathon.shn_provider.reference_run TP-02
python -m connectathon.shn_provider.reference_run TN-01
```

TN-10 intentionally returns a manual-observation record rather than handling a bearer token:

```bash
python -m connectathon.shn_provider.reference_run TN-10
```

### UI

```bash
streamlit run medi_lacra_app.py
```

Open **SHN Provider ePA -> Reference Suite**.

### Live boundary

No live TP/TN suite traffic is run from CI. Live execution belongs in the local environment holding the ignored provider-test credentials. A mismatch between the staff draft and the live endpoint is recorded as a failed expectation with the actual response and trace; the harness does not silently change the contract.

# Claims + ePA MVP — CLI Test Results and Build-Plan Audit

**Version:** 0.1  
**Date:** 2026-10-07 (America/New_York; CI timestamps UTC 2026-10-08)  
**Branch:** `experiment/claims-epa`  
**Base branch:** `experiment/employer-coverage`  
**Final tested code head:** `0097fc1287e3d23673c086878fc18c6c066a8e46`  
**CI run:** https://github.com/natosit-dev/medilacra/actions/runs/37722418933  
**CI job:** `113132893665`  
**Result:** **PASS for scoped executable MVP. External conformance and interoperability NOT yet established.**

See also [Build Plan](CLAIMS_EPA_MVP_BUILD_PLAN_v0.1_2026-10-07.md) and [Build History](CLAIMS_EPA_MVP_BUILD_HISTORY_v0.1_2026-10-07.md).

---

## 1. Exact Executed CLI Commands

On GitHub Actions runner (Ubuntu, Python 3.11), checkout of the code-bearing SHA above:

```sh
python -m pytest -q tests/test_claims_epa_mvp.py
python -m pytest -q
python -m claims_epa --seed 43 --count 5 --at 2026-10-07T23:00:00 --out /tmp/claims-epa-ci
test -f /tmp/claims-epa-ci/CLAIMS_EPA_20261007_230000_00001/837P.x12
test -f /tmp/claims-epa-ci/CLAIMS_EPA_20261007_230000_00001/epa_response.fhir.json
```

Results copied from the completed workflow job log (not inferred or estimated):

```text
Focused Claims/ePA tests: 15 passed in 0.30s
Full repository pytest: 130 passed, 2 warnings in 10.09s
CLI case count: 5
Artifact count per case: 10
Job: success
```

The tests were **executed as CLI commands on the GitHub Actions worker**, not on the operator's laptop. Local container `git clone` was attempted but failed DNS resolution for `github.com`; GitHub Actions provided the authoritative executable test environment for this delivery.

### Existing warnings, not introduced pytest failures

`tests/test_core_generator_offline_sdoh.py` emitted two `sklearn.base.InconsistentVersionWarning` warnings when loading saved models:

- LinearRegression serialized by scikit-learn 1.7.1 but read by 1.9.1;
- MultiOutputRegressor serialized by 1.7.1 but read by 1.9.1.

Both warnings were outside the Claims/ePA modules. The full test job nevertheless passed.

### Interim red builds

During the payer-identity separation refactor, two intermediate partial commits (`fce8925` and `a68ccb3`) failed CI while function signatures and callers were being updated. Later corrective commits completed the cross-module change. The final tested code head `0097fc1` passed the focused and complete suites. Do not describe the build history as failure-free.

---

## 2. Evidence Matrix

| Requirement exercised | Test/evidence | Result |
|---|---|---|
| Reuse MediLacra Patient/CoverageProfile/Encounter/Transaction/Observation | `test_semantic_case_uses_existing_clinical_and_payer_primitives` | PASS |
| Payer-side member and coverage evaluation | payer materializer and inactive/expired enrollment tests | PASS |
| 837P / 835 and 278 req/resp | `test_sibling_x12_and_fhir_share_request_response_facts` | PASS (self-structure only) |
| ISA/GS/ST/SE/GE/IEA relationship, control matching, segment counts | `validate_envelope` and generator tests | PASS (self-structure only) |
| FHIR R4 Claim/ClaimResponse resources for claim and preauthorization | `test_sibling_x12_and_fhir_share_request_response_facts` | PASS (self-structure only) |
| FHIR collection Bundle internal references | `validate_bundle` | PASS (reference resolution only) |
| Money reconciliation in integer cents | semantic reconciliation/invalid-money/denied tests | PASS |
| ePA approved / pended / denied state | parameterized `test_authorization_states` | PASS |
| No implicit patient/encounter/observation linkage errors | mismatch negative tests | PASS |
| Clinical vs payer response name divergence | `test_payer_authoring_preserves_identity_divergence` | PASS |
| Fail closed when payer member routing ID differs | `test_tampered_payer_routing_identity_fails_closed` | PASS |
| Distinct existing claim versus future planned ePA dates | prospective-date assertion and expiry-date case | PASS |
| Coverage expires between existing service and future authorization | paid claim / denied PA case | PASS |
| Cross-representation exchange identity and control uniqueness | deterministic and 100-case tests | PASS |
| 100 case census (4 X12 messages each) | `test_100_synthetic_cases_have_unique_controls_and_exchanges` | PASS: 400 distinct X12 ST controls |
| 100 case semantic identity census | same test | PASS: 200 separate Claims/ePA exchange IDs |
| Main `run_pipeline()`, DuckDB persistence boundary | `tests/test_claims_epa_pipeline.py` in full suite | PASS |
| UI checkboxes and main CLI option | pipeline wiring regression | PASS |
| Deterministic file artifact packaging and CLI run | `test_files_and_cli`; Actions five-case smoke | PASS |
| Old repository regression | `python -m pytest -q` | PASS: 130 |

These tests prove the exercised behavior only. The custom X12 and FHIR validators are deliberately **not** substitutes for real implementation-guide validation.

---

## 3. Produced Artifact Contract

For each synthetic case:

```text
CLAIMS_EPA_YYYYMMDD_HHMMSS_NNNNN/
  837P.x12
  835.x12
  278_request.x12
  278_response.x12
  claim_request.fhir.json
  claim_response.fhir.json
  epa_request.fhir.json
  epa_response.fhir.json
  semantic_reality.json
  manifest.json
```

Each request and response uses its own institutional representation where applicable. The FHIR and X12 files are sibling projections of the same semantic request/response, NOT an X12-to-FHIR transformation. The manifest labels the case: `SYNTHETIC TEST ONLY; NOT X12 TR3 / PAS IG CERTIFIED`.

The main pipeline emits these in case-specific folders when `include_claims_epa=True`; raw X12 and FHIR do not enter `messages.raw_hl7`. Existing pipeline flags default to `False`.

---

## 4. Plan-to-Build Audit (the requested crosswalk)

| Build plan section / acceptance | Audit disposition | Evidence / qualification |
|---|---|---|
| 1. New isolated branch | **Complete** | Branch from `experiment/employer-coverage`; main unchanged |
| 2. Prior prompt history / dated pre-build plan | **Complete** | Plan checkpoint `1c3a12e` committed before code |
| 3. Semantic Claims + ePA models | **Complete for MVP** | `claims_epa/models.py`; explicit source and payer records |
| 4. X12 837P / 835 / 278 req+resp | **Implemented; external conformance pending** | `claims_epa/x12_projection.py`, X12 envelope self-checks |
| 5. FHIR Claim / ClaimResponse two uses | **Implemented; external conformance pending** | `claims_epa/fhir_projection.py`; R4 collection Bundles |
| 6. Shared exchange IDs; clinical/payer authorship | **Complete for MVP** | clinical/payer divergence, route mismatch fail-closed, parity tests |
| 7. Reuse existing models and X12 envelope | **Complete for MVP** | `hl7_demo.models`, payer materializer, `x12.envelope`, `x12.parser` |
| 8. CLI, dated outputs, synthetic manifest | **Complete** | `python -m claims_epa`; 5-case smoke, 10 artifacts/case |
| 9. Main pipeline optional generation / UI | **Complete** | `include_claims_epa=False` default and main Streamlit toggles |
| 10. Pytest CLI, full regression | **Complete** | 15 focused, 130 full-suite passes, 2 warnings |
| 11. Build log, decisions, test audit | **Complete** | plan + build history + this audit |
| 12. External IRIS/X12/PAS review | **Deferred, explicitly not claimed** | no live IRIS or PAS profile validation performed |
| 13. Leave unmerged | **Complete** | no merge request and no update to base/main |

## 5. Remaining Gaps and Risks for Review

**A. Standards conformance (highest priority).** The X12 envelope/control syntax and selected segments are exercised, but the complete licensed 837P, 835 and 278 TR3s are *not* validated. Required loops, code qualifiers, situational rules and transaction envelope semantics must be checked using InterSystems IRIS and/or an appropriate certified validator and implementation guides. Likewise, these are FHIR R4 resource-level Bundles, **not yet PAS-profile-validated `Claim/$submit` Bundles**. Validate against a version-pinned Da Vinci PAS package before SHN interoperability.

**B. Remittance mapping.** X12 835 is a payment/remittance transaction; FHIR `ClaimResponse` represents adjudication. The current output is a useful shared-decision test fixture, **not** a lossless 835↔ClaimResponse translation. `PaymentReconciliation` and payment-specific semantics are deferred.

**C. FHIR payer Coverage richness.** The response includes a separately identified payer Patient/Coverage and payer decision, but its minimal Coverage projection does not yet carry all payer-local `EnrollmentRecord` period/plan/group fields inherited from eligibility's fuller FHIR projection. Do not interpret its current `Coverage.status` alone as proof of in-force benefits. Promote/reuse the fuller existing FHIR Coverage builders rather than adding a second source of truth.

**D. Clinical event semantics.** The demo represents a billed clinical service and a separate later requested service using the same CPT from an existing Observation as a catalog/fixture seed; it is not a longitudinal order/claim/authorization state machine. Clinical ServiceRequest evidence, indications, attachment `275`, prior-authorization updates, and relationship of a future approved service to a later claim remain deferred.

**E. Adjudication/policy realism.** Claim 80% allowed is explicitly synthetic; medical necessity is driven by requested scenario status, not a real payer policy. No multi-line claims, institutional/dental claims, COB, line adjustments beyond MVP, denial CARC/RARC sophistication, 277CA, or payer contract logic.

**F. Scale/operability.** Tested at 100 in-process semantic cases for uniqueness and 5 CLI filesets. No measured large-batch throughput, no native GS-batched multiple transaction sets, and no real network/SHN transport yet. Separate artifact tables and raw representation persistence remain deferred.

**G. UI / external manual acceptance.** Static wiring and pipeline generation tested; hands-on UI click-through and ingesting actual files in IRIS FHIR/X12 tools are manual follow-ups.

## 6. Review Commands

```sh
git checkout experiment/claims-epa
python -m pytest -q tests/test_claims_epa_mvp.py tests/test_claims_epa_pipeline.py
python -m pytest -q
python -m claims_epa --seed 43 --count 5 --at 2026-10-07T23:00:00 --out /tmp/claims-epa-review
python -m claims_epa --seed 43 --authorization-status pended --claim-status denied
```

Recommended first inspection: compare `semantic_reality.json` to `837P.x12`, `835.x12`, `278_request.x12`, `278_response.x12` and FHIR Claim/ClaimResponse Bundles; then run IRIS parser and FHIR profile validation. **Review the gaps, not just the green tests.**

**Final disposition:** scoped synthetic MVP implemented and CLI-tested; external standards/interoperability certification not done. Branch remains isolated for human review.

# Downstream Reality Provenance Audit — Claims/ePA, Eligibility, HL7 v2 and FHIR

**Version:** 0.1  
**Date:** 2026-10-08  
**Branch inspected:** `experiment/claims-epa` (after IRIS 835 Loop 1000A correction)  
**Status:** Evidence inventory and consolidated repair design; **NO corrective code changes in this audit**  
**Trigger:** User observed Lowell, MA addresses appearing in X12 files, then requested a pass to find all downstream invention so failures can be corrected together.

## 0. User-origin prompt / scope

> "I noticed there's a synthetic address in Lowell in certain X12 messages. Where'd that come from?"

> "Do a press to find all the places you're inventing reality downstream. We'll want to fix them all at once"

Interpret "press" as a **pass / audit**. Evaluate **downstream representation code and the semantic handoff that feeds it**, not whether upstream generating synthetic data is inherently undesirable. The goal is to prevent silent fact generation, semantic substitution and omission in each wire representation.

**Scope inspected:** `claims_epa/`, `x12/`, `fhir/eligibility_*.py`, `fhir/fhir_convert_backend.py`, `eligibility/`, `payer/`, relevant `hl7_demo/messages.py`, `hl7_demo/segments.py`, `hl7_demo/labs.py`, `hl7_demo/sdoh.py`, `hl7_demo/generators.py`, and pipeline/orchestration. Other experimental pages, historical `dev/` copies, training notebooks and third-party tooling **not line-by-line audited**. This is a targeted comprehensive production-path inspection, **not a proven absence of other instances across every repository file**.

## 1. Classification / rule

- **S = SOURCE FACT:** sourced from an established, institutionally owned record, e.g., `Patient.address`.
- **E = EXPLICIT SYNTHETIC FACT:** created once by a visible scenario/generator, linked to an identity and carried through.
- **D = DERIVATION:** transparent function of facts, with explicit assumptions/policy, e.g., calculated amount or date.
- **P = PROTOCOL METADATA:** schema-mandated constant with no claim about underlying reality (e.g., `ST*835`, code system URLs, functional groups).
- **I = INVENTED DOWNSTREAM:** serializer or exchange assembler supplies an unestablished real-world fact, role, clinical event, patient-reported method, payment choice, benefit, or party identity.
- **O = OMITTED/SUBSTITUTED:** established reality is not represented, or another unrelated value is substituted while appearing to convey it.

**Invariant:** `project(reality, format, profile)` may format, encode, omit permitted optional fields, or use protocol constants. It must **not create or overwrite domain facts**. Required missing facts fail clearly; optional absent facts remain absent/explicitly unknown. A fixture's synthetic status alone does not excuse an `I` in the serializer.

## 2. Confirmed Claims/ePA defects and assumptions

| ID | Severity | Site (approx. lines) | Classification | Observation | Batch repair requirement |
|---|---|---|---|---|---|
| C01 | HIGH | `claims_epa/x12_projection.py:93-105` | I | 837P supplies `MEDILACRA TEST`, `MEDILACRA01`, `TEST CONTACT`, `5550100000`, fixed `1 SYNTHETIC STREET / LOWELL MA 01852`, fixed patient `100 SYNTHETIC WAY / LOWELL MA 01852`, and `REF*EI*999999999`. None are from the generated patient/provider/submitter. | Source patient N3/N4 from Patient; create explicit provider and submitter organizations, addresses, contact/EIN. Do not default actual geography in the serializer. |
| C02 | HIGH | `claims_epa/models.py:157-179,297-302` | E→silent default | `synthetic_payer_contact()` injects fictional Lowell address and phone for **every payer** unless a caller overrides it. Moving the default into `SemanticCase` fixed serializer layering but did not establish payer-authored reality. | Bind payer contact to an explicit scenario/institution record, with provenance; no automatic fallback in generic cases. Preserve the now IRIS-accepted `N1 PR / N3 / N4 / PER / N1 PE` ordering. |
| C03 | HIGH | `claims_epa/x12_projection.py:132-158` | I | 835 chooses payment method `CHK`, payer transaction trace origin `999999999`, assumes billing provider is the remittance **payee**, and maps all paid adjustments to `CAS*CO*45` (denied to `CO*96`) without an actual reasoned payer adjustment. | Materialize `PaymentMethod`, `Payee`, `RemittanceTrace`, `Adjustment(reason, group, amount)` as payer-side facts; derive X12 only from these. |
| C04 | HIGH | `claims_epa/x12_projection.py:102,108` | I / scenario assumption | 837P asserts primary/self subscriber, commercial insurance, place-of-service composite `11:B:1`, and fixed `Y/A/Y/Y` claim flags. Some are valid *for selected scenarios* but not established in the shared ClaimSubmission. | Carry subscriber relationship, insurance filing type, place of service, assignment, release, benefits and encounter setting from scenario records; validate situational X12 requirements. |
| C05 | CRITICAL | `claims_epa/x12_projection.py:185-211` | O + I | 278 has a requested `procedure_code` in `AuthorizationRequest` but never references it in the 278 projection. The message uses fixed `UM*SC*I*3*11:B...*Y`, `HI` diagnosis and `HSD` quantity. It does not represent the requested service with an evidence-backed code mapping. | Map actual requested service/CPT and proposed date into correct 278 service-level constructs per licensed TR3; fail if no supported representation exists. Verify exact segment/loop against IRIS. |
| C06 | HIGH | `claims_epa/x12_projection.py:186-216` | I | 278 assumes review type, certification mode, place/type, global tracking company ID `999999999`; response trace header and requester/payer roles are fixed by code. | Bind review category, utilization setting and trading-partner identity to `AuthorizationRequest` + message `TransportProfile`. Keep true X12 structure/control qualifiers as P. |
| C07 | HIGH | `claims_epa/models.py:211-235,259-288` | D/E without clinical event | `build_case()` invents a prospective service **14 days after** encounter/run date and reuses a completed Observation CPT as a new proposed service. `approved` is also the default authorization outcome. This is a scenario generator, not a serializer, but it is not backed by an independent order/requested-service event. | Create explicit `RequestedService/ServiceRequest` scenario fact with date, code, ordering clinician, indication, state. Derive authorization from that fact. Retain historical claim vs proposed service separation. |
| C08 | HIGH | `claims_epa/models.py:269-286` | E / unversioned policy | Synthetic fee rule `allowed = 80% charge`, patient responsibility `0`, all allowed paid and generic denial reason are invented in a payer decision fixture; the scenario/payer plan does not specify those policy rules. | Supply named and versioned `SyntheticAdjudicationPolicy` and `SyntheticAuthorizationPolicy` owned by payer simulation. This is permissible generation, but must not masquerade as a general payer rule. |
| C09 | HIGH | `claims_epa/fhir_projection.py:62-70,87-107` | I/O | FHIR Claim/ePA `Coverage.status` is always `active`; `Coverage` has no payer enrollment period/plan/group from source. The payer response `Organization` name comes from the clinical CoverageProfile rather than payer-owned party state. Administrative active status alone also cannot establish coverage on a proposed service date. | Reuse existing `fhir/eligibility_r4.py` clinical/payer Coverage projections with period/plan; model payer-owned name/identity separately. Derive status where supported, avoid incorrectly asserting effective coverage. |
| C10 | MEDIUM | `claims_epa/fhir_projection.py:116-164` | I / constrained-scenario assumptions | FHIR claims universally declare `professional`, `priority=normal`, focal insurance `True`, one line, one diagnosis, and both `Claim.status` and `ClaimResponse.status` `active`. Some are lifecycle choices and legitimate in a constrained fixture, **not automatically errors**, but several have no scenario field to vary them. | Make business/use context explicit in semantic record; retain legitimate protocol defaults only with documented applicability constraints. Do not confuse `status=active` (resource lifecycle) with payer decision. |
| C11 | MEDIUM | `claims_epa/fhir_projection.py:43-47` | lossy fallback | Unknown/unmapped sex becomes FHIR `gender=unknown` silently; source distinction may be erased. | Apply documented code mapping and retain source and unmapped reason; `unknown` may be acceptable as a projection but shouldn't imply source said unknown. |
| C12 | MEDIUM | `claims_epa/generation.py:75-147` | E (legitimate, but fixture-local) | Demo explicitly creates a Lowell patient, fictitious employer, numeric SSN, dates, `TESTPAYER`, and an example service/amount. **This is acceptable upstream synthetic fixture data**. The defect is that other parties' geography/identity is invented separately and is not traceable to it. | Move fixture facts into an explicit documented scenario config; ensure all representations project that one fact inventory with independent institutional records. |

## 3. Existing eligibility defects and assumptions

| ID | Severity | Site | Classification | Observation / remedy |
|---|---|---|---|---|
| E01 | HIGH | `x12/eligibility_271.py:18-30,131-146` | I | Every active response emits a fixed set of ten service categories as active. `BenefitPlan` only has plan identity/name/type and no per-service benefit assertions. Stop claiming specific services absent payer benefit facts; or explicitly generate BenefitPlan benefits in scenario. |
| E02 | MEDIUM | `x12/generation.py:110-119,153-159,182-220` and `eligibility/generation.py:9` | I / transport default | Fixed `MEDILACRA CLINIC`, requester ID, originating company ID and sender/receiver IDs. These are synthetic trading-partner configuration defaults, **not standards-mandated constants**. Move to `ExchangeRouting/TransportProfile`. |
| E03 | MEDIUM | `fhir/eligibility_r4.py:92-106,258-355,376-454` | I / scenario assumption | Both clinical/payer `Coverage.relationship` are always self, clinical Coverage active, `CoverageEligibilityRequest.purpose=[validation, benefits]` fixed, focal `True`. These can be correct for current subscriber-is-patient scenarios, but must be source facts / declared scenario constraints before generalizing. `inforce=True` in the active-only response **does** derive from an established ACTIVE outcome, so is **not** independently flagged. |
| E04 | LOW | `fhir/eligibility_generation.py:31-32` | transport default | Default requester `MEDILACRA01 / MEDILACRA CLINIC`; same routing-profile fix as E02. |
| E05 | CONTEXT | `payer/materialize.py:53-65` | E | `EnrollmentStatus.ACTIVE` assigned when creating payer-local data from truth. This is *upstream synthetic model creation* (not serializer invention), but coverage truth lacks an explicit enrollment-state dimension. Make it an explicit scenario assumption if supporting terminations/disagreements. |

## 4. Wider existing HL7 v2 and legacy FHIR conversion seam

These predate the Claims/ePA branch. They are relevant if the repair goal is literally **all active Medilacra projection paths**, not just new X12/FHIR modules.

| ID | Severity | Site | Classification | Observation / remedy |
|---|---|---|---|---|
| H01 | HIGH | `hl7_demo/messages.py:230-280` | I | `build_adt()` predicts vitals *while rendering*, using current age and optional SDOH queries; offline or missing data is silently set to poverty `0`, AQI `50`. Move predictive inputs and resulting vital observations to synthetic reality generation; preserve unknown SDOH rather than claiming a neutral measurement. |
| H02 | HIGH | `hl7_demo/messages.py:329-420` | I | ADT builder chooses gender identity, pronouns, SPCU afresh, timestamps them with `datetime.now()`, and asserts `patient-reported` or endocrinology-assessment methods. Generate person-asserted facts, methods, effective times **once** upstream; serializer must only project those. |
| H03 | HIGH | `hl7_demo/messages.py:749-769`; `hl7_demo/labs.py:57-102` | I | `build_oru_labs()` calls stochastic `predict_labs_for_patient()` while formatting ORU, using SDOH fallbacks `0` / `50`. Move lab generation to run-scoped Observation instances, share values across FHIR and HL7 and record synthetic-model provenance. |
| H04 | MEDIUM | `hl7_demo/segments.py:1140-1152,1350-1378,1439-1449,1890-1947` | I | ORC order control `RE`, order status `CM`, OBX fallback `F`, and producer `MEDILACRAHS^DEPT1` are emitted without modeled source status/producer. Status, order lifecycle and producer should come from Order/Observation; set ID and value type can remain protocol metadata. |
| H05 | MEDIUM | `hl7_demo/segments.py:774-851` and `hl7_demo/generators.py:545-590` | I / source mismatch | GT1 with CoverageProfile forces patient self-guarantor and mapped employment status; transaction generator separately fabricates a guarantor name from `_provider_name()`. Consolidate guarantor person/relationship and employment in scenario; do not derive financially responsible party from age or randomly generated provider name. |
| H06 | MEDIUM | `hl7_demo/segments.py:1605-1668` | I | FT1 replaces missing clinical description with `CHARGE`, asserts transaction type `CG` and currency USD regardless of Transaction's modeled semantic fields. Use explicit transaction type and currency where required; omit unsupported descriptions instead of manufacturing coded meaning. |
| H07 | MEDIUM | `hl7_demo/segments.py:210-267` | transport default | MSH sender `FAKELAB/MEDILACRAHS`, receiver `MLHS/STAGE`, message time from wall clock. Sender/receiver must come from routing profile; wall clock as message-creation metadata is fine, but never substitute for encounter/observation time. |
| H08 | MEDIUM | `hl7_demo/sdoh.py:570-578` | status/data provenance | Missing PLACES measurement becomes text `N/A` with OBX result status `F`. This does not fabricate a numeric value, but makes absence look like a completed observation without explaining unavailable source/measurement state. Preserve unavailable/null provenance semantically. |
| F01 | HIGH | `fhir/fhir_convert_backend.py:172-181,365-375,512-566,573-583` | I | Legacy HL7v2→FHIR conversion unconditionally sets Encounter `finished`, Coverage `active`, Observation `final`, DiagnosticReport `final`, and Claim `professional/active`, regardless of actual source status/events. Map actual source status, declare scenario defaults if justified, or do not emit unsupported assertion. Particularly dangerous: ADT admission can become a `finished` encounter. |
| F02 | MEDIUM | `fhir/fhir_convert_backend.py:108-125,614-622` | I / fallbacks | MessageHeader source/destination can become `Unknown`, timestamp is conversion-time UTC rather than source message time; missing OBR creates final, generic `DiagnosticReport` (with all observations) rather than expressing missing source document. Require source lineage; only create a report when source report semantics are established. |
| F03 | LOW | `fhir/fhir_convert_backend.py:70-76,125-145` | identity loss | Random UUID resources replace potentially stable source identifiers; `urn:mrn` assumes identifier system if assigning authority unavailable. Not fictional clinical details, but can sever repeatable cross-representation identity. Prefer source-defined stable IDs/known assigning authority and record mapping provenance. |

## 5. Critical findings (compressed)

1. **Most serious message loss:** X12 278 does not serialize the actual requested procedure; FHIR ePA does. Cross-representation tests currently assert shared exchange ID and broad decision but do not enforce exact CPT and proposed-date survival in both representations.
2. **Most pervasive domain invention:** parties (addresses, submitters, guarantors, payer contacts, trading partners, payees) are encoded in ad-hoc defaults instead of independent source records.
3. **Most pervasive semantic invention:** statuses, benefit coverage, claim filing/payment details, decision reasons and clinical/provider methods are chosen by rendering code or unversioned test policies.
4. **Most pervasive temporal invention:** ADT facts calculated at render-time; ePA prospective service invented by `+14 days`; legacy FHIR v2 converter asserts `finished/final` irrespective of source status.
5. **Most insidious test hole:** both formats can agree on a fabricated or incomplete representation. Internal semantic parity cannot prove completeness against truth or external TR3/FHIR profiles.

## 6. Consolidated repair plan — one coherent batch

### Stage 1 — fact ownership and minimal entities

Keep the current canonical clinical/payer dataclasses. Add only what existing code demonstrates we lack:

- **Party / Contact / Role:** patient address from Patient; provider practice/address/NPI/tax ID; submitter; payer organization address/contact; payee vs billing provider; guarantor/relationship. Define independent organizational ownership.
- **ServiceRequest / RequestedService:** CPT, diagnosis/indication, quantity, requested service date, requestor, medical-necessity evidence and status; no fake future request from a completed Observation.
- **Remittance / Adjudication:** payment method/date/trace/payee, adjustment group/reason, allowed/paid/patient share. Payer decision rules become named scenario policies.
- **BenefitDetails / CoverageStatus:** payer-benefit assertions by service, enrollment state and relevant time window.
- **Observation/OrderEvent:** values, effective date, status, method, author/performing organization; all random/predictive generation **before** message building.
- **TransportProfile:** sender/receiver/trading-partner organization identity, address/contact where required, X12 GS/ST qualifiers, control allocation and HL7 MSH routing.

These may initially be thin typed records/config dictionaries rather than a universal knowledge graph. Reuse `fhir/eligibility_r4.py` coverage builders and existing `payer/` and `hl7_demo/` models; **do not create duplicate sources of truth**.

### Stage 2 — remove downstream decisions

Refactor serializers to accept completed semantic facts and transport profiles. No `Faker`, `random`, `predict_*`, `datetime.now` for clinical fact timing, or literal organization addresses/phone/EIN inside X12/FHIR/HL7 builders. Keep **P** constants, e.g., `ST` IDs, FHIR code systems, control/segment delimiters, as versioned protocol metadata.

For required fields, reject missing facts with a precise error identifying workflow, loop/segment or FHIR field. For optional fields, omit or use the standard's permitted explicit unknown semantics; never fill with misleading fake geography, clinical states or payment statuses.

### Stage 3 — representation completeness / semantic tests

Create a field-level **provenance ledger** for each output: `representation_field → concept → source_record/owner → transformation → scenario_id`. For a deterministic generated reality, construct a truth matrix, and assert not just *X12 equals FHIR* but **both equal the source when applicable**. Required tests:

- vary patient, provider, submitter and payer addresses independently → 837P/835/FHIR show appropriate institutional values;
- vary payee vs billing provider → 835 payee follows designated entity;
- change payment method and CARC/CAS reasons → 835 encodes the payer-defined decision rather than choosing CHK/CO45;
- vary subscriber relationship, place of service, filing code, benefits and coverage periods → all representations preserve distinctions;
- change ePA CPT, requested quantity and service date → 278 and FHIR represent the actual requested service (cannot pass if 278 ignores procedure);
- change order/observation status and method → HL7 and legacy FHIR preserve it; no final/finished defaults;
- repeat a reality snapshot through HL7, X12 and FHIR → stable shared facts and identities, with format-specific controls only;
- explicit missing-required-fields and unknown-valued optional fields fail/omit as designed;
- static regression search ensures serializers no longer import random/predictive sources or contain fake addresses, payer phone numbers, bogus tax IDs or fabricated clinical/benefit statuses.

### Stage 4 — standards and outside-in testing

Run CLI pytest; run a scale census for control and identity uniqueness; manually import **270, 271, 837P, 835, both 278** into IRIS `HIPAA_5010` schemas; validate FHIR R4 resources against HL7 validator and PAS against the chosen version-pinned Da Vinci guide. Capture each external error as a source-linked regression test. Distinguish **schema acceptance** from **complete TR3 / PAS conformance**.

### Stage 5 — handoff / gating

- Maintain a single implementation branch or follow-up branch from `experiment/claims-epa`.
- Version prompt history, this audit, acceptance checklist and test evidence as previous builds do.
- Do not merge until the matrix of provenance tests, existing regressions and required external validation is accepted.
- Treat local user-specified demo scenario constants as legitimate **E** values; do not strip the ability to create fictional patients and institutions. The problem is location and ownership of generation, not use of fiction.

## 7. Prioritized decisions for implementation

1. **Scope boundary:** do we repair new Claims/ePA + 270/271 first, or include legacy HL7v2 and HL7v2→FHIR converter in the same branch? All are inventoried; latter broadens regression scope substantially.
2. **Source structure:** favor `Party/Contact` and `ServiceRequest` thin dataclasses or dictionaries with explicit scenario provenance rather than a universal ontology.
3. **Required-field behavior:** prefer **fail closed** for unmaterialized required schema facts over adding default city, payment reason, guarantor, service status, or code.
4. **Standard grammar:** do not invent the missing 278 CPT segment from memory; validate correct X12 278 service-level representation against IRIS/TR3 before implementation.

**Outcome of audit:** concrete confirmed sites and missing semantics are identified. No claim of external validator success for newly identified issues. No generator/serializer code altered by this audit.

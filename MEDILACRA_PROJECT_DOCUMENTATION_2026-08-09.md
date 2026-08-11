# MediLacra Project Documentation
**Working documentation date:** August 9, 2026  
**Repository:** `natosit-dev/medilacra`  
**Repository baseline:** `main` at commit `20fc475e7f7e3b7fcc4b49bbf1c307aed05f3ccd` (July 15, 2026)  
**Working documentation version:** `0.5.0-dev` (documentation label; not asserted to be a Git tag)  
**HL7 target:** HL7 v2.5 / v2.5-style message structures  

MediLacra is a synthetic healthcare data generation and interoperability sandbox. It creates linked synthetic healthcare entities, optionally persists those entities, and renders them into healthcare integration artifacts such as HL7 v2 messages. Public SDOH data can be incorporated to make synthetic cohorts more useful for data-quality, analytics, interface, and demonstration work.
## 1. Executive Summary
The current design treats persisted synthetic entities as the canonical source of truth. Patient, encounter, transaction, and observation records are generated first, linked through stable identifiers, and persisted when persistence is enabled. HL7 messages are derived projections of those canonical records rather than the primary data store.
- Core canonical entities: Patient, Encounter, Transaction, Observation.
- Optional DuckDB persistence for local inspection; the same patterns have also been exercised in a private Databricks environment.
- Primary HL7 families: ADT^A01, ORU^R01, DFT^P03, ORM^O01, and lab ORU^R01.
- SDOH enrichments include ZIP-based geography and public indicators such as air quality, poverty, obesity, and unemployment.
- The August 9 working state expands demographics, providers, insurance, guarantor, diagnosis metadata, POS, and HL7 PID/PV1/GT1/IN1 coverage.
- The project is an active prototype/sandbox, not a clinical prediction system or production-grade healthcare platform.

## 2. Scope and Design Principles
- Synthetic-first: use generated or public data only; do not introduce PHI or production extracts.
- Canonical entities before messages: establish linked healthcare data first, then render interfaces.
- Concrete before abstract: keep the model understandable and relatively flat until repetition and complexity justify normalization.
- Standards-aware, not standards-theater: use recognizable HL7 v2 fields and code systems where practical, while documenting local/demo values.
- Reusability: the same synthetic entities should be usable for HL7, FHIR experiments, DuckDB, Databricks, analytics, validation, and future IRIS workflows.
- SDOH-friendly: preserve geography and demographic context that can support population-level synthetic experiments.

## 3. Current Architecture
```text
Streamlit UI / CLI
        |
        v
Generation Pipeline
        |
        +--> Patient
        +--> Encounter
        +--> Transaction
        +--> Observation
        |
        +--> Optional persistence
        |      +--> DuckDB
        |      +--> Databricks-compatible patterns
        |
        +--> HL7 v2 rendering
               +--> ADT^A01
               +--> ORU^R01 narrative
               +--> DFT^P03
               +--> ORM^O01 labs
               +--> ORU^R01 labs
        |
        +--> Files / downstream integration experiments
```

The working pipeline currently creates one patient, one encounter, one transaction, and one report-backed observation per iteration. Lab messages may be added separately. Scenario profiles influence encounter placement and facility context.
## 4. Runtime Flow
1. Load report templates and supporting reference data.
1. Generate a synthetic Patient.
1. Generate a linked Encounter using the patient identifier and optional scenario profile.
1. Generate a linked Transaction using the encounter identifier.
1. Select a report row and generate a linked Observation.
1. Persist canonical entities when persistence is enabled.
1. Render ADT, narrative ORU, and DFT; optionally render lab ORM/ORU.
1. Apply scenario-driven sending facility context when configured.
1. Write per-encounter or bulk HL7 files.
1. Optionally append raw message metadata to the message store.

## 5. Component Inventory
| Component | Role |
| --- | --- |
| `medi_lacra_app.py` | Primary Streamlit UI and run controls. |
| `hl7_demo/pipeline.py` | Orchestrates generation, persistence, message rendering, and file writes. |
| `hl7_demo/models.py` | Dataclass definitions for canonical entities. |
| `hl7_demo/generators.py` | Creates synthetic entity values and limited coherent relationships. |
| `hl7_demo/segments.py` | Builds HL7 v2.5 segments and maps canonical values to fields. |
| `hl7_demo/messages.py` | Assembles segment builders into message structures. |
| `storage_duckdb_entities.py` | DuckDB DDL, additive migrations, and entity upserts. |
| `hl7_demo/sdoh.py` | Public-data SDOH lookup and OBX construction. |
| `hl7_demo/vitals.py` | Lightweight synthetic vitals generation. |
| `hl7_demo/labs.py` | Synthetic lab panel generation and lab message helpers. |
| Scenario YAML | Facility/location/service configuration for generated encounters. |
| IRIS examples | Separate integration experiments; not the core Python execution path. |
| FHIR / note-coder experiments | Adjacent prototypes; not the canonical generation path. |

## 6. Canonical Data Model
The August 9 working model intentionally remains flat. Provider roles, insurance, guarantor, and diagnosis metadata are stored directly on the existing entities for clarity. This can be normalized later when the data model becomes difficult to reason about.
### Patient
| Field | Type | Definition / use |
| --- | --- | --- |
| patient_id | str | Synthetic patient identifier / current MRN fallback. |
| patient_name | str | Display name, generally LAST, FIRST. |
| date_of_birth | str | Synthetic DOB, YYYY-MM-DD. |
| sex | str | Administrative sex used by PID-8 and existing Gender Harmony logic. |
| gender | str | Persisted gender value, independent of administrative sex. |
| race | str | Synthetic race category. |
| ethnicity | str | Synthetic ethnicity category. |
| marital_status | str | Synthetic marital status. |
| language | str | Synthetic primary language. |
| employer | str | Synthetic employer/employment label for SDOH-oriented work. |
| ssn | str | Synthetic SSN. |
| address | str | Synthetic street address. |
| phone | str | Synthetic phone. |
| email | str | Synthetic email; working convention is firstname.lastname@fakermail.com. |
| zip_code | str | 5-digit ZIP used for geography/SDOH. |
| city | str | City aligned to ZIP reference data. |
| state | str | State aligned to ZIP reference data. |

### Encounter
| Field | Type | Definition / use |
| --- | --- | --- |
| encounter_id | str | Canonical encounter identifier, linked to patient. |
| patient_id | str | Parent patient identifier. |
| visit_number | str | Synthetic visit number. |
| account_number | str | Synthetic account number. |
| patient_class | str | Readable class such as INPATIENT / OUTPATIENT / EMERGENCY. |
| assigned_patient_location | str | PV1-3-oriented location value. |
| admit_datetime | str | Encounter start. |
| discharge_datetime | str | Encounter end. |
| hospital_service | str | Clinical service, e.g. RAD. |
| admit_source | str | Readable admission source. |
| discharge_disposition | str | Readable discharge disposition. |
| ordering_provider_id | str | Local ordering provider identifier. |
| ordering_provider_name | str | Ordering provider display name. |
| attending_provider_id | str | Local attending provider identifier. |
| attending_provider_name | str | Attending provider display name. |
| attending_provider_taxonomy | str | Provider taxonomy code paired with specialty. |
| attending_provider_specialty | str | Readable specialty. |
| mid_level_provider_id | str | Local mid-level provider identifier. |
| mid_level_provider_name | str | Mid-level provider display name. |
| referring_provider_id | str | Local referring provider identifier. |
| referring_provider_name | str | Referring provider display name. |
| placer_order_number | str | Synthetic placer order identifier. |
| filler_order_number | str | Synthetic filler order identifier. |
| place_of_service_code | str | Billing place-of-service code. |
| place_of_service_description | str | Readable POS description. |

### Transaction
| Field | Type | Definition / use |
| --- | --- | --- |
| transaction_id | str | Synthetic transaction/charge identifier. |
| encounter_id | str | Parent encounter identifier. |
| transaction_date | str | Charge transaction timestamp. |
| transaction_amount | float | Extended transaction amount. |
| unit_cost | float | Synthetic unit price/cost. |
| transaction_quantity | int | Quantity, currently typically 1. |
| fee_schedule | str | Synthetic fee schedule, e.g. TECH/PRO. |
| insurance_plan_id | str | Synthetic plan identifier. |
| insurance_plan_name | str | Readable insurance plan name. |
| member_id | str | Synthetic insured/member identifier. |
| group_number | str | Synthetic insurance group number. |
| plan_type | str | PPO/HMO/EPO/MEDICARE/MEDICAID-style plan type. |
| subscriber_relationship | str | Relationship of insured/subscriber to patient. |
| authorization_number | str | Synthetic authorization identifier. |
| billing_provider_id | str | Local billing provider identifier. |
| billing_provider_name | str | Billing provider display name. |
| billing_provider_npi | str | Synthetic 10-digit NPI-shaped value. |
| guarantor_name | str | Synthetic guarantor display name. |
| guarantor_relationship | str | Guarantor relationship to patient. |

### Observation
| Field | Type | Definition / use |
| --- | --- | --- |
| encounter_id | str | Parent encounter identifier. |
| observation_id | str | Report/observation identifier. |
| cpt_code | str | CPT code from report catalog. |
| cpt_description | str | Readable CPT description. |
| procedure_description | str | Procedure description. |
| icd_code | str | ICD-10-CM code from report catalog. |
| icd_description | str | Readable diagnosis description. |
| diagnosis_type | str | Current working value FINAL for report-backed observation. |
| diagnosis_rank | int | Current working rank 1. |
| placer_order_number | str | Links observation to encounter order. |
| filler_order_number | str | Links observation to encounter order. |
| observation_text | str | Synthetic/report narrative. |
| observation_sub_id | str | OBX sub-ID seed. |
| result_status | str | Result status, typically F. |
| completed_time | str | Completion timestamp within encounter window. |
| performing_provider_id | str | Local performing provider identifier. |
| performing_provider_name | str | Performing provider display name. |

## 7. Data Relationships and Invariants
```text
Patient.patient_id
  -> Encounter.patient_id

Encounter.encounter_id
  -> Transaction.encounter_id
  -> Observation.encounter_id

Encounter.placer_order_number
  -> Observation.placer_order_number

Encounter.filler_order_number
  -> Observation.filler_order_number
```

- The canonical entity graph is created before HL7 rendering.
- POS should be coherent with patient class where possible.
- Provider taxonomy and specialty should be selected as a pair.
- Insurance plan name and plan type should be selected as a coherent pair.
- Observation completion time should fall inside the encounter window.
- The current report catalog provides the CPT/ICD/procedure/report bundle used by the Observation.

## 8. Synthetic Generation Rules
| Area | Current straightforward rule |
| --- | --- |
| Patient identity | Faker-generated synthetic identity; geographic city/state/ZIP come from reference data. |
| Email | firstname.lastname@fakermail.com derived from generated patient name. |
| Employer | Simple employer string; may include employer company or basic status labels. It is not yet predictive. |
| Encounter timing | Recent encounter with a short duration; scenario profile may influence class/location/service. |
| POS | Derived from patient class where practical: inpatient 21, outpatient 22, emergency 23. |
| Provider specialty | Small taxonomy/specialty pool; radiology context biased to Diagnostic Radiology. |
| Insurance | Small plan pool with plan type paired to plan name. |
| Transaction | One simple charge per encounter in the current core flow. |
| Observation | One sampled report row per encounter; CPT, ICD, description, and narrative travel together. |
| Gender Harmony | Existing 95% alignment bias to administrative sex with a minority of edge-case variation. |
| Labs | Optional synthetic lab panel; values may be shifted using SDOH signals. |

## 9. Persistence Model
DuckDB remains a deliberately lightweight local persistence layer. The working schema contains patients, encounters, observations, transactions, orders, and messages. Existing databases are intended to evolve through additive ALTER TABLE ... ADD COLUMN IF NOT EXISTS migrations rather than requiring destructive rebuilds.
- patients: demographics, identity, contact, geography, employer.
- encounters: visit context, provider roles, order identifiers, POS.
- observations: CPT/ICD/report/result/provider data.
- transactions: charge, insurance, authorization, billing provider, guarantor.
- orders: small order-link table retained for future use.
- messages: bronze-style raw HL7/message file metadata.

The current design intentionally persists the linked entities before message rendering. This is a design choice: canonical synthetic data is the source of truth; HL7 is a derived representation.
## 10. HL7 v2.5 Mapping
The working HL7 enhancement moves segment creation toward explicit field indexing rather than manual delimiter counting. This makes the mapping easier to review and reduces accidental field shifts.
| Segment | Canonical source | Key mapped fields |
| --- | --- | --- |
| MSH | Run/message context | MSH-3/4 sender, MSH-5/6 receiver, MSH-9 message type/trigger/structure, MSH-10 control ID, MSH-12 v2.5. |
| EVN | Encounter | Event code and encounter timestamp. |
| PID | Patient | PID-3 patient ID; PID-5 name; PID-7 DOB; PID-8 sex; PID-10 race; PID-11 address; PID-13 phone/email; PID-15 language; PID-16 marital status; PID-19 SSN; PID-22 ethnicity. |
| PV1 | Encounter | PV1-2 patient class code; PV1-3 location; PV1-7 attending; PV1-8 referring; PV1-10 service; PV1-14 admit source; PV1-19 visit; PV1-36 discharge disposition; PV1-44/45 dates; PV1-52 mid-level/other provider. |
| ORC | Encounter | Placer/filler order IDs, order status, ordering provider. |
| OBR | Encounter + Observation | Order IDs, CPT/service ID, observation time, ordering provider. |
| OBX | Observation / enrichment | Narrative result, status, observation time; also SDOH/vitals/Gender Harmony CWE or numeric results. |
| DG1 | Observation | ICD-10-CM code, diagnosis timestamp/type. |
| FT1 | Transaction + Observation | Transaction identifiers, date, charge type, CPT/description, quantity, amounts, plan, fee schedule, diagnosis, performing provider. |
| GT1 | Transaction | Guarantor name and relationship. |
| IN1 | Transaction | Plan ID/name, group number, authorization, plan type, subscriber relationship, member ID. |

### Supported message families
| Message | Purpose | Working structure |
| --- | --- | --- |
| ADT^A01 | Admission/registration-style synthetic event | MSH, EVN, PID, PV1, enrichment OBXs, DG1, GT1, IN1. |
| ORU^R01 | Narrative report result | MSH, PID, PV1, OBR, repeated TX OBXs. |
| DFT^P03 | Financial transaction | MSH, EVN, PID, PV1, FT1, DG1, GT1, IN1. |
| ORM^O01 | Synthetic lab order | Delegated to lab-specific builder. |
| ORU^R01 labs | Synthetic lab results | Delegated to lab-specific builder. |

## 11. SDOH and Population Context
- ZIP/city/state reference data provides a geographic anchor.
- Air quality can be obtained/cached from AirNow integrations.
- ACS poverty percentage can be incorporated at ZCTA level.
- CDC PLACES obesity can be incorporated as an optional enrichment.
- BLS unemployment can be incorporated as an optional enrichment.
- Employer is now retained on Patient to support future SDOH-oriented cohort design.
- Current SDOH-to-vitals/labs logic is demonstrative and must not be interpreted as clinically validated inference.

## 12. Scenario Profiles
Scenario YAML profiles are used to influence encounter context such as patient class, location, facility, and service. In the current architecture, scenarios do not yet provide a complete clinical storyline across report choice, diagnosis, procedure, insurance, provider specialty, and lab results. The working direction is to add coherence incrementally rather than create a large rule engine prematurely.
## 13. Databricks and IRIS Context
### Databricks
The entity-first design is compatible with Databricks because canonical records can be persisted as tables and rendered into interface artifacts separately. The current documentation does not assert a packaged Databricks deployment specification; it records that the approach is already being exercised in a private Databricks environment.
### InterSystems IRIS
The repository/archive contains IRIS/ObjectScript integration experiments, but IRIS is not the canonical persistence layer for the current Python pipeline. A future integration can consume generated HL7 through MLLP or another transport without changing the entity model.
## 14. Version Control Strategy
Repository of record: `https://github.com/natosit-dev/medilacra`. The inspected default branch is `main`. The latest retrieved `main` commit was `20fc475e7f7e3b7fcc4b49bbf1c307aed05f3ccd` dated July 15, 2026 with message "Rewrite README with project overview and setup guide".
### Proposed versioning convention
- Use Semantic Versioning labels for coherent project states: MAJOR.MINOR.PATCH.
- 0.x versions remain prototype/sandbox releases.
- MINOR: meaningful model, message, persistence, or workflow capability expansion.
- PATCH: fixes, mapping corrections, documentation, dependency updates, small refactors.
- Use -dev or -rc suffixes for unreleased working states.
- Do not treat the documentation version as an existing Git tag unless a tag is explicitly created.

| Suggested label | Meaning |
| --- | --- |
| 0.5.0-dev | Current August 9 working state: expanded canonical model + DuckDB migrations + HL7 PID/PV1/GT1/IN1 enhancements. |
| 0.5.0 | Use when these changes are committed, smoke-tested, and intentionally released. |
| 0.5.1 | Mapping/test/documentation corrections after the 0.5.0 capability set. |
| 1.0.0 | Reserve for a consciously supported, reproducible release contract rather than prototype status. |

### Commit guidance
```text
feat: expand canonical healthcare entities
feat: add HL7 GT1 and IN1 generation
fix: correct HL7 v2.5 field placement
docs: add project architecture and data dictionary
test: add entity and HL7 smoke tests
refactor: normalize provider associations
```

## 15. Repository / Commit Milestones
These are commit-based milestones retrieved from GitHub; they are not presented as formal semantic releases.
| Date | Commit | Message / milestone |
| --- | --- | --- |
| 2026-07-15 | 20fc475 | Rewrite README with project overview and setup guide |
| 2025-11-19 | 7163bd9 | CPT/ICD Labels + Note Coding + AI Admin updates |
| 2025-10-25 | 57bfe22 | Note Coder Integration + BERT |
| 2025-10-13 | 5502537 | YAML Cache + Scenarios |
| 2025-10-10 | 6dd4f98 | Scenario Profiles |
| 2025-10-04 | fdb8c5b | Message Config + SDOH + db + Testing |
| 2025-09-30 | 9131a28 | SDOH Enhancements |
| 2025-09-29 | b4e2fc0 | Additional Logging + Comments |
| 2025-09-28 | 06dcb1f | Added Logging |

## 16. Engineering Decision Log
| ID | Decision | Current choice | Rationale |
| --- | --- | --- | --- |
| D-001 | Canonical entities precede HL7 rendering | Keep Patient/Encounter/Transaction/Observation as the source of truth; generate messages from them. | Prevents interface representations from becoming the master data model and supports DuckDB/Databricks/FHIR reuse. |
| D-002 | Persist linked entities before message write | Persistence occurs after entity linkage is created and before file output. | Intentional data-first design; write failures are delivery concerns rather than reasons to discard valid canonical data. |
| D-003 | Keep the model flat for now | Provider roles, coverage fields, guarantor, diagnosis metadata remain on existing entities. | Concrete and understandable while the model is still small; normalization can follow actual pain rather than speculation. |
| D-004 | Add employer to Patient | Persist a simple employer field only. | Employer is important to planned SDOH work but does not yet drive clinical generation. |
| D-005 | Derive POS from patient class | Use simple mappings such as inpatient 21, outpatient 22, emergency 23. | Creates low-cost coherence between encounter and billing context. |
| D-006 | Pair specialty and taxonomy | Select provider taxonomy and readable specialty together. | Avoids internally contradictory provider data. |
| D-007 | Keep insurance on Transaction for now | Plan/member/group/type/authorization and guarantor remain on Transaction. | Avoids introducing Coverage/Guarantor entities before multiple coverages or lifecycle behavior are needed. |
| D-008 | Synthetic email convention | Use firstname.lastname@fakermail.com and persist it on Patient. | Predictable, obviously synthetic, and directly reusable in PID-13. |
| D-009 | HL7 v2.5 explicit field indexing | Build larger segments with indexed field arrays rather than counting delimiters manually. | Improves auditability and reduces field-shift errors. |
| D-010 | Add GT1 and IN1 projections | Render guarantor and insurance data into ADT/DFT when transaction data is available. | Makes the new financial context visible in standard HL7 v2 without changing the canonical model. |
| D-011 | Repository baseline vs working state | Document main separately from current working-session changes. | Prevents documentation from misrepresenting uncommitted work as already released. |

## 17. Prompt / Development History
This is a concise development history of the prompts that drove the current documentation state. It records user intent and outcomes, not hidden reasoning.
| Date | Prompt / request summary | Resulting change |
| --- | --- | --- |
| 2026-08-09 | Review the uploaded MediLacra ZIP and explain how it actually works. | Mapped the runtime, persistence, HL7, SDOH, lab, IRIS, FHIR, and auxiliary components. |
| 2026-08-09 | Use the public GitHub repo as the source of truth. | Separated current `main` from the dated ZIP/local snapshot. |
| 2026-08-09 | Clarify why entities are persisted before message write. | Recorded canonical-entity-first persistence as intentional architecture, not a defect. |
| 2026-08-09 | Expand persisted healthcare data with simple fields. | Selected insurance, POS, provider taxonomy/specialty, diagnosis/context fields. |
| 2026-08-09 | Keep the implementation minimally invasive. | Limited changes to existing dataclasses, generators, storage, and later HL7 projection. |
| 2026-08-09 | Provide a fuller models.py without over-abstracting. | Expanded Patient, Encounter, Transaction, and Observation while retaining flat entities. |
| 2026-08-09 | Add employer for SDOH work. | Added Patient.employer while deliberately avoiding a full employment model. |
| 2026-08-09 | Provide the corresponding generators.py with comments. | Defined straightforward pools/coherence rules for demographics, provider specialty, POS, insurance, guarantor, and observations. |
| 2026-08-09 | Update DuckDB persistence. | Expanded DDL/upserts and additive migrations for the new fields. |
| 2026-08-09 | Enhance HL7 v2 mappings. | Scoped changes to segments.py/messages.py with a small pipeline parameter change. |
| 2026-08-09 | Generate a full updated segments.py. | Introduced explicit field indexing plus PID/PV1/GT1/IN1 and field-placement cleanups. |
| 2026-08-09 | Generate the final messages.py update. | Added transaction-aware ADT insurance/guarantor segments and DFT EVN/GT1/IN1 composition. |
| 2026-08-09 | Produce complete project documentation. | Created this architecture, data dictionary, version-control, decision-log, prompt-history, and release-notes package. |

## 18. Release Notes
### 0.5.0-dev - August 9, 2026 - Unreleased working state
Status: working-session target state; not represented here as an existing Git tag or confirmed merge to `main`.
#### Added
- Expanded Patient demographics: gender, ethnicity, marital status, language, employer, email.
- Expanded Encounter context: admit source, discharge disposition, referring and mid-level providers, attending taxonomy/specialty, POS.
- Expanded Transaction insurance/guarantor context: plan name, member/group, plan type, subscriber relationship, authorization, billing NPI, guarantor name/relationship.
- Expanded Observation metadata: CPT/ICD descriptions, diagnosis type/rank, performing provider.
- Synthetic firstname.lastname@fakermail.com patient email convention.
- GT1 and IN1 segment builders.
- Richer PID and PV1 field projections.
- Additive DuckDB migrations for the expanded schema.

#### Changed
- HL7 segment construction moves toward explicit field-index arrays for auditability.
- PV1-2 renders compact HL7 patient-class codes I/O/E from readable canonical values.
- ADT can accept Transaction data and append GT1/IN1.
- DFT composition includes EVN and can append GT1/IN1.
- Provider specialty/taxonomy, POS, and insurance plan/type generation are paired for basic internal coherence.

#### Not yet changed / deferred
- No provider normalization into Provider / EncounterProvider tables yet.
- No separate Coverage, Guarantor, Diagnosis, Employer, Facility, Claim, or Invoice domain entities yet.
- Employer does not yet influence health outcomes or SDOH calculations.
- No claim adjudication/payment lifecycle.
- No full longitudinal multi-encounter patient model in the core flow.
- FHIR and IRIS remain separate/adjacent integration work rather than the canonical runtime.

### Repository baseline - July 15, 2026
The latest retrieved `main` commit rewrote the project README and documents the existing prototype: synthetic entities, HL7 v2.5-style messages, SDOH enrichments, lab/vitals generation, DuckDB persistence, Streamlit UI, and YAML scenarios.
## 19. Known Limitations
- The system is synthetic and demonstrative; it is not a clinical prediction or decision-support system.
- Report selection is still largely independent of scenario context, so full clinical coherence is not guaranteed.
- One core encounter currently maps to one core transaction and one report-backed observation in the main loop.
- Synthetic NPI values are NPI-shaped; check-digit validation is not yet part of the basic generator design.
- Some code values remain local/demo values and should be formalized only when a specific interoperability profile requires it.
- HL7 structure and mapping need repeatable validation tests before calling a release standards-conformant.
- The current seed behavior does not necessarily control every source of nondeterminism.
- Public API availability and cached SDOH data can affect enrichment behavior.
- The working August 9 changes need to be committed/tested before they can be treated as the repository release state.

## 20. Recommended Next Steps
1. Commit the expanded models/generators/storage/segments/messages changes on a feature branch.
1. Run a small entity smoke test and verify non-null/coherent new fields in DuckDB.
1. Add focused unit tests for PID, PV1, GT1, IN1, FT1, OBR, DG1 field positions.
1. Generate one ADT, ORU, and DFT and validate segment ordering and expected fields against a v2.5 parser/profile.
1. Update README/data dictionary in the repository from this document.
1. Only then decide whether the next modeling step is multiple coverages, provider normalization, multiple observations/charges, or longitudinal encounters.

## 21. Release Checklist for 0.5.0
- [ ] models.py matches generator constructor fields.
- [ ] generators.py creates all required values without constructor errors.
- [ ] DuckDB schema initializes cleanly on a new database.
- [ ] Existing DuckDB database migrates cleanly with ADD COLUMN IF NOT EXISTS.
- [ ] Patient / Encounter / Observation / Transaction joins remain intact.
- [ ] Generated email follows fakermail.com convention.
- [ ] ADT contains expected PID/PV1/DG1/GT1/IN1 data.
- [ ] ORU contains correct OBR and narrative OBX fields.
- [ ] DFT contains EVN, FT1, DG1, GT1, and IN1 as expected.
- [ ] Lab ORM/ORU still run after shared segment changes.
- [ ] Scenario-profile sending facility behavior remains intact.
- [ ] README and release notes updated.
- [ ] Release/tag created only after smoke tests pass.

## 22. Source Basis
- Public repository: https://github.com/natosit-dev/medilacra
- Latest retrieved `main` commit during documentation: 20fc475e7f7e3b7fcc4b49bbf1c307aed05f3ccd.
- Uploaded August 9 archive: Medilacra_8.9.2026.zip.
- Uploaded/working code reviewed in this session: models.py, generators.py, storage_duckdb_entities.py, segments.py, messages.py, pipeline.py, medi_lacra_app.py.
- Current-session design decisions and requested changes through August 9, 2026.

## 23. Documentation Maintenance
Keep this document synchronized with releases rather than individual experimental edits. Update the data dictionary when canonical model fields change, the HL7 mapping section when segment projections change, the decision log when a durable architecture choice is made, and release notes when a coherent version is cut. Prompt history should remain a concise engineering chronology rather than a transcript.

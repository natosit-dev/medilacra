# Scaled X12 Pipeline — Test Results

**Version:** 0.1  
**Date:** 2026-10-07  
**Branch:** `experiment/employer-coverage`  
**Code-bearing head tested:** `db02fbb1991ad825fe61d1d2ef50cdbdc8cfde28`

---

# 1. Purpose

Record the validation results from the first scaled X12 270/271 integration into the primary MediLacra `run_pipeline()` generation path.

The build under test added:

- optional X12 270/271 generation to `run_pipeline()`;
- generated clinical-name normalization for X12;
- run-scoped timestamp + incrementing control numbers;
- general payer materialization;
- payer member/enrollment/plan DuckDB persistence;
- main Streamlit X12 generation controls;
- Generate & Persist integration;
- a normal-pipeline X12 scale harness.

---

# 2. Automated Pytest Results

Successful GitHub Actions workflow:

```text
https://github.com/natosit-dev/medilacra/actions/runs/37620159856
```

Results:

```text
Focused employer/coverage/payer/X12 suite:
89 passed in 4.80s

Full repository regression suite:
102 passed in 2.95s
```

No pytest failures were reported.

---

# 3. New Test Files Added in This Round

```text
tests/test_x12_scaled_generation.py
tests/test_payer_storage.py
tests/test_x12_pipeline_integration.py
tests/test_x12_pipeline_ui_wiring.py
```

## `tests/test_x12_scaled_generation.py`

Validates:

- `LAST, FIRST` -> `LAST^FIRST` X12 normalization;
- compatibility with existing caret-form fixtures;
- run-scoped X12 control allocation;
- 1,000 eligibility exchange pairs / 2,000 unique controls;
- monotonically increasing control suffixes;
- no control collisions;
- generated clinical -> independent payer materialization;
- encounter admission date -> 270 service date;
- bulk and per-encounter datetime-stamped X12 filenames.

## `tests/test_payer_storage.py`

Validates:

- `payer_members` table creation;
- `payer_enrollments` table creation;
- `payer_plans` table creation;
- payer member round-trip persistence;
- payer enrollment round-trip persistence;
- enrollment status persistence;
- payer plan round-trip persistence;
- idempotent payer-plan upsert.

## `tests/test_x12_pipeline_integration.py`

Validates the actual primary pipeline boundary:

```text
run_pipeline(include_x12=True)
```

including:

- one 270 generated per encounter;
- one 271 generated per encounter;
- encounter service date carried into 270;
- generated clinical identity carried into 270;
- payer identity carried into 271;
- clinical CoverageProfile persistence;
- payer MemberRecord persistence;
- payer EnrollmentRecord persistence;
- payer BenefitPlan persistence;
- clinical coverage / payer-member synthetic linkage;
- raw X12 is not stored in `messages.raw_hl7`;
- `include_x12=False` preserves the previous output/count behavior.

## `tests/test_x12_pipeline_ui_wiring.py`

Validates:

- the main Streamlit generator compiles;
- the main generator exposes `Include X12 Eligibility (270/271)`;
- the main generator passes `include_x12` into `run_pipeline()`;
- `.x12` artifacts are included in recent-file display;
- Generate & Persist uses the primary `hl7_demo.pipeline.run_pipeline`;
- Generate & Persist exposes payer DuckDB tables.

---

# 4. Control Number Validation

The scaled control allocator was exercised across:

```text
1,000 eligibility exchanges
2,000 X12 messages
```

Observed assertions:

```text
2,000 unique controls
0 collisions
monotonic sequence
shared run timestamp prefix
```

Example shape:

```text
270 -> 114500001
271 -> 114500002
270 -> 114500003
271 -> 114500004
...
```

Human-readable trace IDs retain full timestamp + exchange sequence:

```text
TRACE-270-20261007114512-00001
TRACE-270-20261007114512-00002
...
```

---

# 5. External IRIS Validation

After pulling the scaled build locally, generated messages from the normal MediLacra generation path were loaded into an InterSystems IRIS X12 production.

IRIS recognized generated requests as:

```text
HIPAA_5010:270
Health Care Eligibility Benefit Inquiry
```

and generated responses as:

```text
HIPAA_5010:271
Eligibility, Coverage or Benefit Information
```

IRIS also decomposed the complete hierarchy:

```text
Interchange
  ISA / IEA
      |
      v
Group
  GS / GE
      |
      v
Transaction
  ST / SE
```

Examples observed from the general generator included different synthetic patients, payers, member IDs, service dates, plans, groups, and control numbers rather than replaying the original hand-built fixture.

Examples included:

```text
AETNA
RODRIGUEZ / SAMANTHA
MEM-37042806
service date 20261003
```

and:

```text
BCBS
SANCHEZ / CHRISTOPHER
MEM-73255959
Standard PPO
GRP-FEDEX-840180
```

The IRIS validation showed X12 envelope/control relationships being accepted at the interchange, group, and transaction-set levels.

This is external structural/parser validation, not a claim of exhaustive implementation-guide certification.

---

# 6. Result

The first scaled X12 integration satisfies the current build target:

```text
general MediLacra generation
        |
        v
Patient + CoverageProfile + Encounter
        |
        v
independent payer primitives
        |
        v
270 -> payer evaluation -> 271
        |
        v
full X12 interchange files
        |
        v
IRIS HIPAA 5010 parser
```

The next architectural issue identified during local UI testing is separate from X12: the core ADT generator still performs AirNow/Census SDOH lookups even when visible optional SDOH/lab controls are disabled. That behavior is already avoided in Disco Inferno and should be promoted into the primary generator.

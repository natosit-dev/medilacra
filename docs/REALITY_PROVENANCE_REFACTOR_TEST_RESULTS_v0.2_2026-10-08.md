# Reality Provenance Refactor — Latest Test Results

**Version:** 0.2
**Date:** 2026-10-08 America/New_York (CI log 2026-10-09 UTC)
**Tested commit:** `cd89ed3337c5610a14c6d13a35676d5fcb4753ad`
**Workflow:** https://github.com/natosit-dev/medilacra/actions/runs/37867998969
**Result:** SUCCESS

## Executed CLI tests

```text
python -m pytest -q tests/test_reality_persistence.py \
    tests/test_storage_duckdb_entities.py tests/test_claims_epa_pipeline.py
7 passed in 2.41s

python -m pytest -q
147 passed, 2 warnings in 5.32s

python -m claims_epa --seed 43 --count 2 \
    --at 2026-10-07T23:00:00 --out /tmp/reality-provenance-cli
SUCCESS: 2 generated cases; 10 Claims/ePA artifacts per case
```

The complete suite covers source-field persistence, read-only audit and verified backup, independently owned clinical and payer facts, stored-case replay, field-level X12/FHIR invariants, prospective RequestedService, versioned synthetic payer policy, and preservation of legacy FHIR event/result statuses. The optional lab generator remains unchanged in scope.

**Quality boundary:** A green test run confirms internal behavior only. It does not certify X12 5010 transaction-guide compliance, FHIR validation, Da Vinci PAS profiles or the user's existing local DuckDB data. Separate external IRIS and HL7 validator checks remain open. The current refactor branch is intentionally unmerged; the source checkpoint remains unchanged.

New source improvements after the original v0.1 test/audit document are explained in [Post-checkpoint Addendum v0.2](REALITY_PROVENANCE_REFACTOR_ADDENDUM_v0.2_2026-10-08.md).

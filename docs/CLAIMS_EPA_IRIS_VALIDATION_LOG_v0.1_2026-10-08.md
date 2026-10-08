# Claims/ePA — IRIS External X12 Validation Log

**Date:** 2026-10-08
**Version:** 0.1
**Branch:** `experiment/claims-epa`
**Validation source:** Human-operated InterSystems IRIS X12 HIPAA 5010 schema viewer
**Feedback:** 835 artifact from normal Medilacra UI, user screenshot
**Status:** Corrective generator patch committed; **IRIS retest pending**

## Prompt / observation history

> "Got it. Dropped them in IRIS. We got our first schema error"

The screenshot shows:

- `X12 835 Document - Id = 552, DocType = 'HIPAA_5010:835'`
- `'Health Care Claim Payment/Advice', 14 segments`
- `Build Map Status = 'ERROR'`
- `Missing required loop1000A.N3 element at segment 6 (N1)`
- `Missing required loop1000A.N4 element at segment 6 (N1)`
- `Missing required loop1000A.PER element at segment 6 (N1)`

Message sequence at issue:

```x12
N1*PR*UNITEDHEALTHCARE~
N1*PE*ORTEGA,MICHAEL*XX*1345177818~
```

**Interpretation:** IRIS recognized the document as HIPAA 5010:835; its payer-identification loop 1000A expects street-address N3, city/state/postal N4, and contact PER before payer-to-payee loop boundary. This is evidence of *first schema failure*, **not** validation of the rest of the message or of the envelope's all TR3 constraints.

## Patch

Affected code:

- `claims_epa/models.py`: explicit `PayerContact` in the semantic case, with test-only factory, optional caller override and payer-ID match guard.
- `claims_epa/x12_projection.py`: `build_835` emits `N3`, `N4`, `PER` after `N1*PR` and before `N1*PE`.
- `claims_epa/generation.py`: passes contact through semantic model to 835 renderer.
- `tests/test_claims_epa_mvp.py`: IRIS-driven regression asserts exact segment order, values, and mismatched payer rejection.

Representative **synthetic** replacement body:

```x12
N1*PR*UNITEDHEALTHCARE~
N3*100 SYNTHETIC PAYER WAY~
N4*LOWELL*MA*01852~
PER*CX*SYNTHETIC EDI SUPPORT*TE*5550100000~
N1*PE*ORTEGA,MICHAEL*XX*1345177818~
```

The address and phone are explicitly fictional **fixture values**, not claims about UnitedHealthcare. No payer address has been researched or inferred. This is a test-only message generator; production payer directory and contact data remain unimplemented.

## Reproduce and retest

```bash
cd ~/code/medilacra
git switch experiment/claims-epa
git pull --ff-only
python -m pytest -q tests/test_claims_epa_mvp.py
python -m claims_epa --seed 43 --count 1 --out /tmp/claims-epa-iris
# Re-run Generate and Persist with Claims + ePA selected to test the UI path.
```

Find the new `835.x12` under the newest `output/CLAIMS_EPA_*/` folder. Import it to the same IRIS `HIPAA_5010:835` parser and record the new build-map result. **Do not describe this issue as IRIS-verified resolved until the human confirms it.**

## Next interpretation rule

Record IRIS schema errors one by one, with transaction type, loop, segment, severity and a before/after example. Avoid retrofitting a global schema model from one failure. Update the corresponding regression test each time and keep the semantic models responsible for source facts.

## Automated regression result (2026-10-08)

GitHub Actions [run 37787168534](https://github.com/natosit-dev/medilacra/actions/runs/37787168534) validated the corrected code and new 1000A tests:

```text
python -m pytest -q tests/test_claims_epa_mvp.py  -> 17 passed
python -m pytest -q                           -> 132 passed, 2 warnings
CLI smoke: 5 synthetic cases, 10 artifacts per case
GitHub Actions job result: success
```

**Evidence boundary:** GitHub tests verify message construction and local structural assertions; the corrected 835 **has not yet been reimported into IRIS** as of this entry. The manual test remains open.

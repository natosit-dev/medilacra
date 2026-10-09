# MediLacra first run: provider test endpoint, route 00301 (Da Vinci 2.2)

CRD order-sign, then DTR `$questionnaire-package`, then PAS `Claim/$submit`, then `Claim/$inquire`,
against `https://pa-test.shn-preview.org`, test member `MBR-COVERED`, payer
`urn:oid:2.16.840.1.113883.6.300|00301`. Synthetic data only.

Sources (SmartHealthNetwork/shn-platform main): `docs/workstreams/prior-authorization/provider-quick-start.md`
and `provider-test-endpoint.md` (the same text as shn-sdk `docs/PROVIDER_TEST_ENDPOINT.md`).

## Files

| File | What it is |
|---|---|
| `register-medilacra.json` | the `POST /register` body (reference §2). **Edit the three `<...>` fields first.** |
| `crd-00301.json` | CRD order-sign body, reference §5.1, unchanged (payer `00301` on the contained payor Organization, `coverage` and the other five prefetch keys) |
| `dtr-00301.json` | DTR body, reference §5.2, unchanged. The script overwrites its `questionnaire` parameter (`valueCanonical`) with the canonical the CRD answer names |
| `pas-00301.json` | PAS request Bundle, reference Appendix A, unchanged. Its Patient carries the member identifier the payer matches on: `http://example.org/MIN|12345678901`, typed `MB` |
| `run-00301.sh` | the steps. Needs bash, curl, jq |

## Run it

```bash
chmod +x run-00301.sh
$EDITOR register-medilacra.json   # your name, a plain email address, your system and version
./run-00301.sh register           # once only. Writes client.json (mode 600) with the one-time client_secret
./run-00301.sh crd                # gets a token first, then sends CRD
./run-00301.sh dtr
./run-00301.sh submit
./run-00301.sh inquire
# or after register: ./run-00301.sh all
```

Each step gets a new token when the last one is 4 minutes old (tokens last 5 minutes). The
script never prints the secret or the token, and never saves request headers. Keep
`client.json` private and out of git. If you lose it, you need a new registration.

## What to expect

| Step | Expect |
|---|---|
| register | `200`, `client_id` printed. A refusal is plain text: see the refusal guide, "Registering" |
| crd | `200`, `cards: 0`, one system action; `covered: conditional`, `pa-needed: auth-needed`, `doc-needed: clinical`, questionnaire `http://example.org/fhir/Questionnaire/HomeHealthAssessment`, saved in `out/questionnaire-canonical.txt` |
| dtr | `200`; `packagebundle` with a Questionnaire, 3 Libraries, a ValueSet and a QuestionnaireResponse; `outcome` with one warning (demographic prepopulation skipped) |
| submit | `200`; ClaimResponse `outcome: complete`, review action `A4` "Pending", a CommunicationRequest (`102089-0`) with a new `AUTH-TRN…` trace number |
| inquire | `200`; a `Parameters` with `responseBundle`s, often many: every matching claim the payer holds since its last clearing, including other participants'. The script tells you whether yours is in it |

These are the reference payer's normal answers, not MediLacra bugs: the empty `cards`, the
missing `FHIRHelpers` Library, the prepopulation warning, the pend, the payer's own
`Patient/SubscriberExample` in PAS answers, and an `A2`/`A3` whose display disagrees with X12.
Test claims are cleared every night at 07:00 UTC (3:00am ET) from 10/07 to 10/14. After a
clearing, run `submit` again before `inquire`.

## Outputs and traces

- `out/<step>.json`: the answer body. `out/<step>.headers`: the answer headers.
- `out/run-log.tsv`: one line per call: UTC time, step, HTTP status, the `X-Correlation-Id`
  we sent (`medilacra-<step>-<timestamp>`), the one that came back, `X-SHN-Leg-Id`, and the trace URL.
- Trace: `https://admin.shn-preview.org/connectathon/trace/<X-Correlation-Id>` (or the
  `X-SHN-Leg-Id`), opened with the picker at All participants. Register and token answers
  carry no id: find them by time and `client_id`.
- Anything other than 2xx: look up the text in `provider-refusal-guide.md`. Quote the
  `X-Correlation-Id` and the time.
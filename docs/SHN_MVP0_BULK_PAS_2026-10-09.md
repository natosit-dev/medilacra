# SHN MVP-0 — bulk documented PAS

After seed 300 returned A1 Certified in total with the completed DTR QuestionnaireResponse, the remaining DTR-eligible patients can be submitted through the same PAS boundary.

Build from the already materialized 34-case DTR cohort while skipping seed 300:

```bash
DTR_BATCH="connectathon/results/shn_bulk_dtr/shn_bulk_dtr_0300_0399"

python -m connectathon.shn_bulk_pas \
  --dtr-batch "$DTR_BATCH" \
  --skip-seed 300
```

Expected output:

```text
connectathon/results/shn_bulk_pas/shn_bulk_pas_documented
```

Expected count: 33.

Send:

```bash
PAS_BATCH="connectathon/results/shn_bulk_pas/shn_bulk_pas_documented"
./connectathon/shn_bulk_pas_send.sh "$PAS_BATCH"
```

Success target for every case:

```text
HTTP 200
ClaimResponse outcome = complete
review action = A1 "Certified in total"
CommunicationRequests = 0
authorization present
behavior_match = true
```


## Live batch result — remaining 33 patients

The documented PAS batch completed successfully:

```text
HTTP 2xx:       33/33
A1 certified:   33/33
no comm req:    33/33
authorization:  33/33
behavior match: 33/33
```

Combined with the separately tested seed 300, the entire 34-case DTR-eligible cohort completed the documented PAS boundary successfully:

```text
34/34 HTTP 200
34/34 A1 "Certified in total"
34/34 no CommunicationRequest
34/34 authorization present
34/34 expected behavior
```

This establishes repeatability across all 34 independently generated lumbar-fusion patients that CRD routed into DTR.

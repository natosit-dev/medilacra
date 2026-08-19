# Yakkity ACK — First Delivery Quick Start

Yakkity ACK now has a minimal MediLacra-side delivery loop:

```text
HL7 file
   ↓
MLLP framing
   ↓
TCP sender
   ↓
IRIS receiver
   ↓
ACK
   ↓
MSH-10 / MSA-2 correlation
   ↓
microsecond timing
```

## 1. Generate one MediLacra message

From the repository root:

```bash
python -m hl7_demo.batch_cli \
  --patients 1 \
  --encounters-per-patient 1 \
  --observations-per-encounter 1 \
  --transactions-per-encounter 1 \
  --seed 42 \
  --per-encounter \
  --no-progress
```

Choose one generated ADT file from the output directory.

## 2. Point Yakkity ACK at IRIS

Once an IRIS HL7 TCP/MLLP business service is listening:

```bash
python -m yakkity_ack \
  --host 127.0.0.1 \
  --port 2575 \
  --message ./output/<your-adt-file>.hl7 \
  --show-ack
```

Replace the host, port, and message path with the values for your environment.

## 3. Expected output shape

```text
Yakkity ACK
Recipient:   127.0.0.1:2575
Message:     ADT^A01
MSH-10:      <message-control-id>
HL7 version: 2.5

ACK:         AA (ACCEPTED)
MSA-2:       <message-control-id>
Correlation: PASS

Timing (microseconds):
  connect:    ... us
  send:       ... us
  ACK wait:   ... us
  round trip: ... us
```

The first milestone is complete when the outbound `MSH-10` matches the returned `MSA-2`.

## What the first version measures

- TCP connection time
- socket send time
- ACK wait time
- message-to-ACK round-trip time
- ACK code (`AA`, `AE`, `AR`, or another returned value)
- correlation between outbound `MSH-10` and inbound `MSA-2`
- raw `ERR` segments where supplied

Timing uses Python's monotonic `time.perf_counter_ns()` internally and reports integer microseconds.

## What it does not do yet

- persistence / DuckDB run ledger
- retries
- persistent TCP connections
- load generation
- percentile summaries
- mutation/scenario framework
- application-vs-commit ACK distinction

Those belong after the first real IRIS round trip is proven.

## Local test without IRIS

The test suite includes a tiny local mock MLLP receiver that accepts one message and returns a correlated `AA` ACK. Run:

```bash
pytest tests/test_yakkity_ack.py -q
```

This verifies framing, parsing, correlation, and the complete socket delivery loop without requiring an IRIS instance.

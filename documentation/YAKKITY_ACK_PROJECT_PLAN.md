# Yakkity ACK — Project Plan

**Working name:** Yakkity ACK  
**Tagline:** *Don’t Talk NACK*  
**Status:** MVP planning  
**Parent project:** MediLacra  
**Primary integration target:** InterSystems IRIS interoperability production  
**Branch:** `yakkity-ack`  
**Date:** August 18, 2026

## Prompt History

### Prompt 1 — Initial idea
> “Oh shit! I should use my IRIS production to do ACK testing with Medilacra. What's the minimum setup needed?”

This established the project goal: use MediLacra-generated HL7 messages as controlled input to a real IRIS production and inspect acknowledgment behavior.

### Prompt 2 — Project name
> “Yeah we could start a new branch. Call it... Yakkity ACK 😁😁😁
>
> OH SHIT!   ... Don't talk NACK 🤣🤣🤣🤣🤣🤣”

This established the working project name and tagline.

### Prompt 3 — Gap analysis
> “Ok, look at Medilacra and let's do a gap analysis to MVP”

Review of the current MediLacra repository showed that most upstream capabilities already exist: linked synthetic patient generation, encounter generation, observation generation, transaction generation, ADT/ORU/DFT/ORM/lab ORU construction, experiment-style CLI cardinality controls, deterministic seeds, batch/per-encounter output, scale testing, and existing IRIS/ObjectScript interoperability components.

The principal missing capability is transport and acknowledgment observation:

**MediLacra can already talk. IRIS can already listen. They need a controlled conversation layer between them.**

### Prompt 4 — Timing
> “Do not connect the million-entity Data Dumper first. 😹
>
> Hey you're not the boss of me 😡😋
>
> Hmm... I think we should time in microseconds”

This established microseconds as the canonical reporting unit for transport and acknowledgment latency.

Timing should use a monotonic high-resolution clock such as `time.perf_counter_ns()`, with reported measurements converted to integer microseconds.

### Prompt 5 — Project plan
> “Ok, let's see the project plan. Definitions, existing components, new ones, workflow, etc. I feel like we've got a suite of these now for new projects. Prompt log at the top. What problem we're solving. Nat style explanations alongside the fancy words”

This established the documentation structure used below.

### Prompt 6 — Sender ontology and Nat-style correction
> “That's a bad definition for sender. It's the delivery person. The ACK is signing for the package. The receiver is the package recipient
>
> Also tone down the swears in the Nat Style 😹 Profanity is a tool for human salience, not sprinkles on a cake. Update the plan, decision log at the bottom”

This corrected the transport ontology and the documentation style.

The package-delivery analogy is now used consistently:

- **HL7 message** = package
- **Sender** = delivery person
- **IRIS receiver/service** = package recipient
- **ACK** = signature / receipt confirming what happened at delivery
- **Message control ID** = tracking number
- **Correlation** = confirming that the signed receipt belongs to the package that was sent

Nat-style explanations should be concrete and memorable without forcing profanity where ordinary language works better.

### Prompt 7 — Branch and documentation
> “Ok, let's branch Medilacra for this project, add this plan to the documentation section”

This created the `yakkity-ack` branch from `agent/connectathon-fast-generation-prep` so the project inherits the current batch-generation work, and established this document as the branch planning baseline.

---

# 1. What Problem Are We Solving?

MediLacra can create synthetic healthcare reality and project that reality into HL7 messages.

IRIS can receive HL7 messages and operate as an interface engine.

What MediLacra does not currently provide is a controlled way to ask:

> **What actually happens when this message hits a real interface engine?**

Writing an HL7 file proves that a string was generated.

It does not prove:

- that the message can cross an interface boundary;
- that MLLP framing is correct;
- that IRIS receives the message;
- that IRIS rejects malformed messages appropriately;
- that an ACK belongs to the message we think it does;
- how long acknowledgment takes;
- what happens during retries;
- what happens during duplicates;
- what happens under increasing message pressure;
- where transport acceptance ends and application acceptance begins.

Yakkity ACK adds that missing boundary.

## Fancy version

Yakkity ACK is a controlled interoperability test harness for measuring message transport, acknowledgment semantics, correlation integrity, failure classification, and latency across a real HL7 v2 interface-engine boundary.

## Nat version

**Send a fake healthcare message to IRIS, see what it says back, and keep the receipts.**

---

# 2. Core Principle

A successful write is not the same thing as successful receipt.

Successful receipt is not the same thing as successful parsing.

Successful parsing is not the same thing as successful processing.

Successful processing is not necessarily the same thing as correct semantic interpretation.

Yakkity ACK begins by isolating the first observable boundary:

```text
MESSAGE SENT
      ↓
MESSAGE RECEIVED
      ↓
ACK RETURNED
```

Later phases can move deeper into:

```text
TRANSPORT ACCEPTANCE
        ↓
MESSAGE PARSING
        ↓
APPLICATION ACCEPTANCE
        ↓
BUSINESS PROCESSING
        ↓
SEMANTIC VALIDATION
```

## Fancy version

The project separates transport acknowledgment from application and semantic acceptance so that distinct state transitions are not collapsed into a single binary success flag.

## Nat version

**“It got there” is different from “they understood it” and different again from “they did the right thing with it.”**

---

# 3. Package-Delivery Analogy

The physical-delivery analogy maps closely to the actual interface responsibilities.

```text
PACKAGE
HL7 message

DELIVERY PERSON
Sender

DELIVERY ROUTE
TCP connection

PACKAGING RULES
MLLP framing

RECIPIENT
IRIS HL7 receiver / business service

TRACKING NUMBER
MSH-10

SIGNED RECEIPT
ACK

TRACKING NUMBER ON RECEIPT
MSA-2

DELIVERY PROBLEM
timeout / rejected connection / malformed response

RECIPIENT REFUSAL OR ERROR
AE / AR or downstream failure depending on ACK mode
```

This analogy prevents an important conceptual mistake:

**The sender is not the recipient.**

The sender delivers the package. IRIS receives it. The ACK records what happened at the delivery boundary.

---

# 4. Existing MediLacra Components

The current connectathon preparation branch already contains most of the upstream machinery Yakkity ACK needs.

## 4.1 Synthetic entity generation

Existing MediLacra generators create:

- Patient
- Encounter
- Observation
- Transaction

The batch pipeline preserves relationships between them rather than generating unrelated flat records.

This matters because ACK testing should eventually operate against coherent healthcare scenarios rather than isolated HL7 strings.

## 4.2 Existing HL7 message families

Current batch generation includes:

- ADT
- ORU
- DFT
- ORM
- ORU_LABS

One ADT, narrative ORU, and DFT are generated per encounter. Optional lab messages add ORM and ORU_LABS.

### MVP use

Start with ADT because it provides the smallest useful end-to-end proof while the other families remain available for expansion.

## 4.3 Batch CLI

Existing batch controls include:

```text
--patients
--encounters-per-patient
--observations-per-encounter
--transactions-per-encounter
--seed
--bulk
--per-encounter
--no-labs
--no-vitals
--no-gender-harmony
--verbose
--no-progress
```

This gives Yakkity ACK controlled input cardinality for one-message debugging, deterministic regression tests, controlled bursts, and large throughput experiments.

## 4.4 Deterministic synthetic reality

Seeded generation already exists.

That allows experiments where the generated clinical world remains materially comparable across runs while transport or interface configuration changes.

## 4.5 Batch and per-encounter output

MediLacra already supports:

- **bulk mode** — optimized for volume;
- **per-encounter mode** — optimized for inspection and debugging.

Yakkity ACK can initially consume per-encounter messages without changing existing generation behavior.

## 4.6 Existing test scenarios

The branch already contains behavioral and scale scenarios including:

- smoke tests;
- regression tests;
- sparse encounters;
- no observations;
- no transactions;
- Gender Harmony disabled;
- labs disabled;
- vitals disabled;
- deterministic-seed comparisons;
- scale runs through approximately one million generated entities.

Yakkity ACK therefore does not need to invent a synthetic test suite from scratch. It can add transport behavior to an existing one.

## 4.7 Existing IRIS components

The repository already contains IRIS/ObjectScript artifacts, including a business process that accepts an `EnsLib.HL7.Message`, reads MSH metadata, and files the message.

That gives the project an existing IRIS-side reference implementation rather than a blank interface-engine target.

---

# 5. New Components

Suggested package:

```text
yakkity_ack/
    __init__.py
    cli.py
    sender.py
    mllp.py
    ack.py
    models.py
    ledger.py
    scenarios.py
```

Testing follows the established project convention:

```text
testing/
    yakkity_ack/
```

---

# 6. Component Definitions

## 6.1 MLLP Framer

### Fancy definition

A transport framing component that serializes and deserializes HL7 v2 payloads using Minimal Lower Layer Protocol delimiters.

### Nat definition

**The packaging.**

The HL7 message is the thing being delivered. MLLP wraps it so the receiving system knows where the package begins and ends.

Responsibilities:

- prepend VT / `0x0B`;
- append FS + CR / `0x1C 0x0D`;
- remove framing from incoming ACKs;
- detect incomplete or malformed frames.

## 6.2 Sender

### Fancy definition

A transport client that delivers an HL7 message to a configured receiving endpoint over TCP/MLLP and waits for the corresponding acknowledgment.

### Nat definition

**The delivery person.**

The sender picks up the package, takes it to the correct address, hands it to the recipient, and waits for the signed receipt.

Responsibilities:

- open the delivery route;
- deliver the framed HL7 message;
- wait for the recipient’s acknowledgment;
- handle timeout or failed delivery;
- close or reuse the route;
- record timing for each delivery phase.

The sender is responsible for delivery. It is not the receiver, and it is not the ACK.

## 6.3 Receiver

### Fancy definition

The configured IRIS HL7 business service or receiving endpoint that accepts inbound HL7 messages over TCP/MLLP.

### Nat definition

**The package recipient.**

IRIS is the system standing at the other end of the route. It receives the package and determines what acknowledgment should be returned according to its configuration and processing state.

## 6.4 ACK

### Fancy definition

An HL7 acknowledgment message communicating the receiving system’s disposition of the inbound message at a defined acknowledgment boundary.

### Nat definition

**The signed delivery receipt.**

The ACK tells us what the recipient says happened when the package arrived.

A signature for delivery does not necessarily mean the contents were later processed correctly. That distinction becomes important when we separate commit ACKs, application ACKs, and downstream semantic behavior.

## 6.5 ACK Parser

### Fancy definition

A response interpreter that extracts acknowledgment state, message correlation identifiers, and error metadata from returned HL7 ACK messages.

### Nat definition

**Read the signed receipt.**

Minimum fields:

```text
MSA-1    acknowledgment code
MSA-2    original message control ID
MSA-3    acknowledgment text
ERR      structured error information where available
```

Initial classifications:

```text
AA
AE
AR
TIMEOUT
CONNECTION_ERROR
MALFORMED_ACK
UNMATCHED_ACK
```

## 6.6 Correlator

### Fancy definition

A message-response integrity mechanism that verifies that the acknowledgment references the intended outbound message.

### Nat definition

**Check the tracking number on the receipt.**

Core invariant:

```text
outbound MSH-10 == inbound ACK MSA-2
```

An ACK without valid correlation is not treated as a successful test result.

## 6.7 Timing Instrumentation

### Fancy definition

High-resolution monotonic latency instrumentation for measuring discrete transport and acknowledgment phases.

### Nat definition

**Put a stopwatch on each part of the delivery.**

Canonical reporting unit:

```text
microseconds
```

Recommended measurement source:

```python
time.perf_counter_ns()
```

Converted for storage:

```text
microseconds = nanoseconds / 1000
```

Measurements:

```text
connect_us
send_us
ack_wait_us
round_trip_us
```

Clock resolution does not equal measurement accuracy. Python scheduling, TCP buffering, operating-system scheduling, IRIS worker availability, and network behavior create real noise.

The goal is not fake nanosecond precision. The goal is useful microsecond-resolution observation.

## 6.8 Run Ledger

### Fancy definition

A persistent experimental provenance store recording test configuration, message identity, observed acknowledgment state, latency, and failures.

### Nat definition

**The delivery log.**

Suggested implementation: **DuckDB**.

Suggested tables:

### `runs`

```text
run_id
started_at
completed_at
host
port
connection_mode
scenario
message_count
success_count
error_count
status
```

### `message_results`

```text
run_id
message_control_id
message_type
event_type
sent_at
ack_at
ack_code
ack_text
connect_us
send_us
ack_wait_us
round_trip_us
correlation_status
transport_status
raw_ack
error_detail
```

## 6.9 Scenario Mutator

Not required for the first successful ACK, but part of the MVP system design because negative testing is central to the project.

### Fancy definition

A controlled mutation layer that introduces one known defect into an otherwise stable HL7 fixture so acknowledgment behavior can be compared against a known baseline.

### Nat definition

**Change one thing in the package and see what the recipient does differently.**

Initial mutations:

```text
bad MSH
missing required field
unsupported event
malformed segment
duplicate MSH-10
invalid value
```

Critical rule: **change one thing at a time.** Otherwise a NACK does not tell us which defect caused the behavior.

---

# 7. Workflow

## Phase 1 — Generate

MediLacra creates a deterministic synthetic patient and encounter.

```text
Patient
   ↓
Encounter
   ↓
ADT
```

Example:

```bash
python -m hl7_demo.batch_cli \
  --patients 1 \
  --encounters-per-patient 1 \
  --observations-per-encounter 1 \
  --transactions-per-encounter 1 \
  --seed 42 \
  --per-encounter
```

## Phase 2 — Inspect

Yakkity ACK extracts:

```text
MSH-9
MSH-10
MSH-12
```

These become outbound test metadata.

## Phase 3 — Package

The raw HL7 message is framed using MLLP.

```text
VT
HL7 MESSAGE
FS
CR
```

## Phase 4 — Open Delivery Route

The sender opens a TCP connection to the configured IRIS receiver. Timing begins using a monotonic clock.

## Phase 5 — Deliver

The sender transmits the framed HL7 package and records send start/completion.

## Phase 6 — Recipient Receives

IRIS receives the HL7 message through its configured business service. What happens internally after receipt depends on IRIS production configuration and acknowledgment mode.

## Phase 7 — Receipt Returned

The sender waits until a complete ACK frame arrives, timeout occurs, or the connection fails.

## Phase 8 — Parse Receipt

The ACK parser extracts the ACK code, message correlation ID, ACK text, and ERR contents.

## Phase 9 — Correlate

Compare:

```text
sent MSH-10
       ==
ACK MSA-2
```

This verifies that the signed receipt belongs to the package that was sent.

## Phase 10 — Classify

Result becomes something like:

```text
ACCEPTED
APPLICATION_ERROR
REJECTED
TIMEOUT
TRANSPORT_FAILURE
MALFORMED_RESPONSE
CORRELATION_FAILURE
```

## Phase 11 — Persist

Store input identity, scenario, acknowledgment, latency, correlation status, raw response, and failure details.

## Phase 12 — Summarize

At run completion report:

```text
messages sent
AA count
AE count
AR count
timeouts
correlation failures
min RTT
median RTT
p95 RTT
p99 RTT
max RTT
messages/sec
```

---

# 8. End-to-End Architecture

```text
MediLacra synthetic reality
            │
            ▼
Patient / Encounter / Observation / Transaction
            │
            ▼
HL7 message builder
            │
            ▼
       Yakkity ACK
 ┌───────────────────────┐
 │ fixture inspection    │
 │ MLLP framing          │
 │ sender                │
 │ timing                │
 │ ACK receiver          │
 │ parser                │
 │ correlator            │
 │ classifier            │
 │ ledger                │
 └───────────┬───────────┘
             │
             ▼
          TCP / MLLP
             │
             ▼
      IRIS HL7 Receiver
             │
             ▼
    IRIS Business Process
             │
             ▼
         ACK / NACK
             │
             └──────────────► Yakkity ACK
```

Package view:

```text
PACKAGE
MediLacra HL7
      ↓
DELIVERY PERSON
Yakkity ACK Sender
      ↓
DELIVERY ROUTE
TCP / MLLP
      ↓
RECIPIENT
IRIS
      ↓
SIGNED RECEIPT
ACK
      ↓
RECEIPT VERIFICATION
Correlation + timing + persistence
```

---

# 9. MVP Acceptance Criteria

Yakkity ACK MVP is complete when the following can be performed reproducibly.

## Happy path

Given one deterministic MediLacra ADT:

```text
send message
receive ACK
parse ACK
correlate MSA-2 to MSH-10
record latency in microseconds
persist result
```

Illustrative output:

```text
Message: ADT^A01
MSH-10: MEDILACRA-12345

ACK: AA
Correlation: PASS

Connect:       812 us
Send:           41 us
ACK wait:     1438 us
Round trip:   1479 us

Persisted: PASS
```

## Controlled failure

Given the same baseline fixture with one intentional mutation:

```text
send mutated message
receive non-AA response or other observable failure
parse response
correlate where possible
record latency
persist result
```

Illustrative output:

```text
Scenario: bad_msh

ACK: AE
Correlation: PASS
ERR: ...

Round trip: 1312 us

Persisted: EXPECTED_ERROR
```

---

# 10. What Is Explicitly Not MVP

Do not let the first version become an interface-engine certification platform.

Not yet:

- full HL7 conformance profiles;
- FHIR;
- X12;
- complex routing;
- arbitrary interface engines;
- distributed load generation;
- container orchestration;
- production benchmarking claims;
- automatic remediation;
- message-ordering guarantees;
- sophisticated retry policy;
- dashboard UI;
- massive scenario DSL;
- formal IRIS application-ACK certification.

These can emerge naturally once the basic evidence path works.

---

# 11. Immediate Testing Sequence

The smallest useful progression is:

```text
1 message
10 messages
100 messages
1,000 messages
```

At each scale ask:

```text
Did every package arrive?
Did every package receive a receipt?
Did every receipt match the correct tracking number?
What was the ACK distribution?
What was the latency distribution?
Did behavior change as pressure increased?
```

Once the mechanics are trustworthy, larger-scale testing becomes meaningful.

---

# 12. Post-MVP Expansion

## 12.1 Persistent connections

Compare connect-per-message against connection reuse. Measure connection setup separately so TCP setup does not contaminate ACK latency.

## 12.2 Message-family matrix

Test ADT, ORU, ORM, DFT, and ORU_LABS against known scenarios.

## 12.3 Retry and replay

Introduce timeout, disconnect, retry, replay, and duplicate behavior and observe actual engine behavior.

## 12.4 ACK semantic depth

Separate:

```text
commit ACK
application ACK
semantic/process outcome
```

An interface engine can successfully receive a message that a downstream process later rejects.

## 12.5 Throughput experiments

Run increasing pressure and measure throughput, latency, p95, p99, timeouts, errors, and reconnects.

The useful question is:

> **Where does system behavior change?**

That is more informative than only asking how many messages per second it can take.

## 12.6 MediLacra Data Dumper integration

Eventually:

```text
MediLacra Data Dumper
          ↓
       Yakkity ACK
          ↓
          IRIS
```

Now the generator becomes a controlled workload source rather than merely a file generator.

---

# 13. Key Definitions

## ACK

**Fancy:** HL7 acknowledgment communicating message disposition at a defined receiving boundary.

**Nat:** **The signed receipt.**

## NACK

Common informal term for a negative acknowledgment such as an error or rejection.

**Nat:** **The recipient did not accept the package cleanly.**

## MLLP

**Minimal Lower Layer Protocol** — a lightweight framing convention commonly used to transport HL7 v2 messages over TCP.

**Nat:** **The packaging rules for delivering the HL7 message over the network.**

## Sender

A client responsible for delivering a message to a receiving endpoint.

**Nat:** **The delivery person.**

## Receiver

The system endpoint configured to accept the delivered message.

**Nat:** **The package recipient.**

## Message correlation

Association between an outbound message and its corresponding acknowledgment.

**Nat:** **Checking that the tracking number on the signed receipt matches the package we sent.**

## MSH-10

HL7 message control identifier.

**Nat:** **The package tracking number.**

## MSA-2

The acknowledgment field containing the control identifier of the original message.

**Nat:** **The tracking number written on the receipt.**

## Round-trip latency

Elapsed time between initiating message transmission and receiving the corresponding acknowledgment.

**Nat:** **How long it took to deliver the package and get the signed receipt back.**

## Monotonic clock

A timer that only moves forward and is independent of wall-clock corrections.

**Nat:** **A stopwatch instead of checking the wall clock twice.**

## Microsecond

One millionth of a second.

```text
1 second       = 1,000 milliseconds
1 millisecond  = 1,000 microseconds
```

Used here as the canonical latency reporting unit.

## Percentile latency

A distribution measure describing how quickly some percentage of requests completed.

Example: `p95 = 2,400 us` means 95% of observed acknowledgments completed in 2,400 microseconds or less.

**Nat:** **Most deliveries were faster than this; the unusually slow ones are above it.**

## Scenario

A defined test condition applied to a message or run.

Examples:

```text
valid_adt
bad_msh
duplicate_control_id
unsupported_event
```

**Nat:** **The specific thing we changed for this test.**

## Fixture

A controlled input used repeatedly during testing.

**Nat:** **A known fake patient/message we can reuse so the input is not changing underneath the experiment.**

## Provenance

Evidence showing where a result came from and how it was produced.

**Nat:** **The record showing exactly how we got this result.**

---

# 14. Design Principles

## Preserve the working generator

Do not rewrite MediLacra just because Yakkity ACK exists. Generation and transport are separate responsibilities.

## One mutation at a time

Controlled experiments require known differences.

## Persist raw responses

Interpretations can improve later. Raw evidence cannot be reconstructed if we throw it away.

## Correlation before success

An ACK that cannot be tied to its source message is not trustworthy evidence.

## Measure distributions, not anecdotes

One fast ACK proves almost nothing about system behavior. Repeated observations reveal the distribution.

## Keep transport separate from semantics

An engine saying “I received this” does not necessarily mean “this message represented reality correctly.”

That distinction is central to the larger MediLacra / PIQITT / SaSI family.

---

# 15. Relationship to the Existing Tool Suite

```text
MediLacra
creates synthetic healthcare reality

        ↓

MediLacra Data Dumper
creates lots of it quickly

        ↓

Yakkity ACK
delivers HL7 across a real interface boundary
and observes acknowledgment behavior

        ↓

PIQITT
transforms / interprets healthcare representations

        ↓

PIQI
evaluates resulting data quality

        ↓

SaSI
asks what survived transformation

        ↓

WAP
runs large workloads and preserves execution evidence

        ↓

ASSES
changes representation topology and measures consequences
```

These are not one giant application. They are increasingly becoming a set of small experimental instruments that can be combined.

## Fancy version

A composable healthcare data experimentation toolkit.

## Nat version

**A collection of small tools for asking different questions about how healthcare data behaves.**

---

# 16. First Implementation Target

The first implementation should prove exactly one complete loop:

```text
MediLacra ADT
      ↓
MLLP packaging
      ↓
Sender / delivery person
      ↓
IRIS receiver
      ↓
ACK / signed receipt
      ↓
correlation
      ↓
microsecond timing
      ↓
DuckDB result
```

Once that loop works reliably, everything else becomes an experiment rather than infrastructure debugging.

---

# 17. Decision Log

### Decision 001 — Reuse MediLacra generation
**Decision:** Do not create a separate synthetic HL7 generator.  
**Reason:** MediLacra already creates linked synthetic healthcare entities and multiple HL7 message families.

### Decision 002 — Branch from connectathon preparation work
**Decision:** Create `yakkity-ack` from `agent/connectathon-fast-generation-prep`.  
**Reason:** Yakkity ACK should inherit the latest experiment-oriented generation controls and Data Dumper groundwork rather than reconstructing them.

### Decision 003 — ADT first
**Decision:** Use ADT as the first Yakkity ACK message family.  
**Reason:** It provides the smallest meaningful complete transport test while existing ORU/ORM/DFT support remains available for expansion.

### Decision 004 — Transport is a separate component
**Decision:** Do not embed socket behavior directly inside entity generators.  
**Reason:** Synthetic reality generation and message delivery represent different responsibilities.

### Decision 005 — Sender means delivery person
**Decision:** Define the sender as the transport actor responsible for delivering the HL7 package to the receiving endpoint.  
**Reason:** This preserves the actual responsibility boundary. The sender delivers; IRIS receives; the ACK is the receipt.

### Decision 006 — Use the package-delivery analogy consistently
**Decision:** Model the transport layer using HL7 message = package, sender = delivery person, IRIS receiver = package recipient, MSH-10 = tracking number, ACK = signed receipt, MSA-2 = tracking number on receipt.  
**Reason:** The analogy is mechanically accurate enough to clarify responsibility without hiding the actual HL7 terminology.

### Decision 007 — Persist experimental state
**Decision:** Store runs and message outcomes in DuckDB.  
**Reason:** Test history, timing distributions, failures, and correlation evidence become useful almost immediately.

### Decision 008 — Report latency in microseconds
**Decision:** Use microseconds as the canonical stored and displayed timing unit.  
**Reason:** Milliseconds are unnecessarily coarse for local/interface-engine experimentation; nanoseconds would imply precision the runtime and network stack do not actually provide.

### Decision 009 — Use monotonic high-resolution timing
**Decision:** Measure with `time.perf_counter_ns()` and convert to microseconds.  
**Reason:** Wall-clock timestamps are useful for provenance; monotonic timers are appropriate for duration measurement.

### Decision 010 — Preserve raw ACKs
**Decision:** Store the raw acknowledgment alongside parsed fields.  
**Reason:** Future parsers and interpretations may improve; original evidence should remain available.

### Decision 011 — Correlation is mandatory
**Decision:** An ACK does not count as a successful observation unless its response can be correlated to the outbound message where correlation is expected.  
**Reason:** At scale, receipt of an ACK is not evidence that the correct message was acknowledged.

### Decision 012 — Controlled failure is part of MVP
**Decision:** MVP includes at least one intentionally malformed test fixture.  
**Reason:** A harness that demonstrates only successful acknowledgment proves much less than one that also demonstrates observable failure behavior.

### Decision 013 — Scale follows a trustworthy measurement loop
**Decision:** Establish reliable send → receive → correlate → persist behavior before drawing performance conclusions from large runs.  
**Reason:** Otherwise the experiment may measure defects or overhead in the harness rather than IRIS behavior.

This does not prohibit immediately pointing a very large MediLacra workload at IRIS. It merely affects what conclusions we are entitled to draw from the resulting adventure. 😹

### Decision 014 — Nat-style language should clarify, not decorate
**Decision:** Use concrete plain-language explanations alongside technical terminology. Profanity should be rare and intentional rather than used as a default stylistic marker.  
**Reason:** Nat-style explanations exist to reduce abstraction and improve salience. The point is comprehension, not performance.

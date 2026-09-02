# Connectathon 43 Working Index

This directory contains the MediLacra / PIQITT working artifacts for HL7 FHIR Connectathon 43, September 19–20, 2026.

## Active plan

- [`PIQI_CONNECTATHON_43_MVP_BUILD_PLAN.md`](PIQI_CONNECTATHON_43_MVP_BUILD_PLAN.md) — operating contract, scope boundary, phased build plan, acceptance criteria, kickoff questions, and evidence model for the PIQI Framework track.

## Implementation status

- [`IMPLEMENTATION_STATUS_2026-09-02.md`](IMPLEMENTATION_STATUS_2026-09-02.md) — first-pass implementation map, UI/CLI workflow, provenance boundary, validation status, known limitation, and the exact work intentionally deferred until the PIQI track kickoff clarifies the live endpoint/report contract.

## Branch

`connectathon/piqi-43`

This branch was created from `experiment/disco-inferno` so the Connectathon work can reuse the completed controlled-entropy experiment without merging unrelated experimental work into `main` prematurely.

PIQITT has a matching `connectathon/piqi-43` branch containing the thin non-UI FHIR conversion wrapper used by the Connectathon work.

## Current objective

Generate known synthetic FHIR cases, introduce one declared information-quality defect at a time, submit baseline and mutant payloads to multiple PIQI-enabled endpoints, preserve raw reports, and compare both endpoint agreement and results against known mutation ground truth.

The local path through FHIR baseline → controlled mutants → manifests/preflight/evidence pack is implemented. External PIQI endpoint execution remains intentionally gated on the current track contract.

## Scope discipline

The Connectathon branch is a thin experimental integration layer. It is not a general MediLacra rewrite and does not attempt to make PIQITT an independent conformant PIQI endpoint during MVP.

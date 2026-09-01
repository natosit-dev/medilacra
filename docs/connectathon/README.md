# Connectathon 43 Working Index

This directory contains the MediLacra / PIQITT working artifacts for HL7 FHIR Connectathon 43, September 19–20, 2026.

## Active plan

- [`PIQI_CONNECTATHON_43_MVP_BUILD_PLAN.md`](PIQI_CONNECTATHON_43_MVP_BUILD_PLAN.md) — operating contract, scope boundary, phased build plan, acceptance criteria, kickoff questions, and evidence model for the PIQI Framework track.

## Branch

`connectathon/piqi-43`

This branch was created from `experiment/disco-inferno` so the Connectathon work can reuse the completed controlled-entropy experiment without merging unrelated experimental work into `main` prematurely.

## Current objective

Generate known synthetic FHIR cases, introduce one declared information-quality defect at a time, submit baseline and mutant payloads to multiple PIQI-enabled endpoints, preserve raw reports, and compare both endpoint agreement and results against known mutation ground truth.

## Scope discipline

The Connectathon branch is a thin experimental integration layer. It is not a general MediLacra rewrite and does not attempt to make PIQITT an independent conformant PIQI endpoint during MVP.

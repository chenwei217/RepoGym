# ADR 0005: Versioned structured execution evidence

## Problem and context

Execution details existed inside `result.json` and `metadata.json`, while test counts and output
files used separate shapes. Machine integrations could not consume all evidence through one
versioned contract or verify which sanitized artifact content a record described.

## Current behavior

Runs persisted compatible grading results and output files, but had no unified evidence document,
schema negotiation, record source, observation time, or deterministic cross-kind ordering.

## Alternatives considered

- Replace `result.json`. This would break reports and comparisons unnecessarily.
- Add more unrelated fields to metadata. This preserves fragmentation and lacks record semantics.
- Persist an additive evidence document and synthesize it for older runs.

## Decision

Evidence schema v1 contains command, test, environment, and artifact records. Every record has a
kind, source, observation time, status, summary, task ID, and typed details. Records sort by kind,
source, and summary. Commands and artifact contents are sanitized first; environment evidence is
limited to non-secret runtime identity. Output records include SHA-256 and encoded byte length.

## External behavior and compatibility risk

New runs add `evidence.json`; existing result and metadata shapes remain readable. `load_evidence`
synthesizes v1 from legacy run artifacts without rewriting them. Unknown versions and fields fail
strict validation. Consumers should treat observation time as metadata, not deterministic input.

## Verification

Tests cover all record kinds, stable ordering, JSON round-trip, unknown schema rejection, strict
fields, path privacy, artifact hashes, corrupt input, persisted integration, and legacy synthesis.

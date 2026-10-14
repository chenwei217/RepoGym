# 0018: Portable run archives

## Problem and current behavior

Task bundles transfer definitions, but execution evidence must be copied manually. There is no
bounded, integrity-checked format for moving a completed run between machines.

## Alternatives and decision

Reusing task bundles would confuse definitions with outputs. Arbitrary directory ZIPs admit
unnecessary content and extraction hazards. Define independent archive schema 1 with a flat
allowlist, SHA-256 manifest, bounded reads, and existing result/evidence models.

## External behavior and compatibility

`archive export`, `archive verify`, and `archive import` never execute task code. Export reapplies
privacy filters and rebuilds output hashes. Verify checks exact membership, identities, and evidence
associations. Import verifies before staging, serializes same-ID publications with an exclusive
lock, and refuses existing targets. Legacy runs may omit evidence and timestamps. Files already
inside a run remain unchanged. Hashes detect corruption, not maliciously rewritten provenance.

## Acceptance

Round-trip current and legacy runs; byte-identical exports; replay all reports; test tampering,
missing/duplicate/unsafe members, links, versions, limits, conflicting targets, lock contention,
and failed publication cleanup. No network or real task execution is needed for import.

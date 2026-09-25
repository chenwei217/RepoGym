# ADR 0008: Atomic incremental execution cache

## Problem and context

Repeated grading of identical task and submission inputs reran the same local commands. Batch and
interactive workflows need safe reuse without confusing a replay with a new execution or trusting
partially written and tampered artifacts.

## Current behavior

Every `grade` call created a new run and executed all, public, and quality commands. Run artifacts
were sanitized and durable, but no compatibility key, locking, integrity manifest, or cache
maintenance interface existed.

## Alternatives considered

- Return the original run directory on a hit. This would hide invocation identity and make callers
  mutate or compare one shared run.
- Cache only the final score. That would discard evidence needed by reports and comparisons.
- Cache sanitized complete run artifacts, then materialize a distinct replay run with provenance.

## Decision

Cache schema v1 keys canonical SHA-256 input containing the full task fingerprint, submission file
hashes, resolved command, executor identity and output limits, Python/OS identity, and RepoGym
version. Per-key exclusive files serialize same-key work; stale files are recoverable. Completed
runs are copied to a sibling staging directory, hashed in a manifest, and atomically renamed.

On a hit, membership and every hash are checked before artifacts are copied to a new staged run.
The new run ID and cache hit/source metadata are written before atomic publication. Corrupt entries
are removed under the key lock and recomputed. Cancelled, timed-out, and launch-error runs are not
cached. CLI grading enables caching by default; the Python API requires an explicit `cache_root`.

## External behavior and compatibility risk

`grade` adds `--no-cache` and `--cache-dir`; `cache list`, `cache verify`, and `cache clear` manage
the store. Cached CLI grades may avoid executing candidate code, so callers requiring fresh side
effects must opt out. Existing run fields retain their meanings and receive an optional additive
`cache` object. Cache format versions are isolated under their own directory.

## Verification

Tests cover deterministic keys and task/submission/command/executor/runtime invalidation, atomic
failure cleanup, hashes and exact membership, distinct replay identity, corruption recovery,
stale and contended locks, concurrent single execution, incomplete-result exclusion, CLI controls,
disable behavior, and full example-task verification on Windows and Ubuntu CI.

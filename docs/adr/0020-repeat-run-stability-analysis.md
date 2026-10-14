# 0020: Comparable repeated-run analysis

## Problem and current behavior

Pairwise comparison locates regressions, but cannot summarize repeated measurements. Runs identify
tasks and environments, not the prepared candidate content; grouping different solutions would
mislabel ordinary code changes as test instability.

## Alternatives and decision

Grouping by task alone is misleading. Cache keys include extra runtime inputs and are absent when
caching is disabled. Persist a version-one SHA-256 identity of the prepared file manifest before
test injection. Group by task ID, task fingerprint, candidate fingerprint, and persisted environment
fingerprint. Use bounded result-only reads, never raw stdout/stderr, and exclude cache replays by
default. Duration summaries always exclude cached and incomplete executions.

## External behavior and compatibility

`analyze RUN...` renders versioned JSON, terminal, or escaped HTML with outcome rates, nearest-rank
p95/median durations, and per-case observed variation. Old results remain readable but missing
identity is explicitly excluded. New optional result/metadata fields and an artifact evidence
record preserve format compatibility. A cache-key capability marker prevents pre-identity entries
from replaying as new observations. No source files or environment values are recorded.

## Limits and verification

Observed variation is not proof of randomness: network, time, hardware contention, and undeclared
inputs can still differ. Missing/skipped cases are not failures; insufficient observations are
labeled. Test grouping boundaries, legacy data, duplicates/conflicting IDs, cache exclusions,
quantiles, pass/fail variation, privacy, HTML escaping, bounded inputs, and candidate hash stability.

# 0010: Deterministic batch evaluation

Status: Accepted

## Problem and context

Automation needs to evaluate multiple task/submission pairs in one invocation while preserving
RepoGym's validation, cache, evidence, reporting, and stable exit-code behavior. One malformed or
failed job must not prevent independent jobs from producing reviewable run artifacts.

## Current behavior

Before this decision, callers had to invoke `grade` repeatedly and invent their own ordering,
failure continuation, result aggregation, machine reports, and exit-code policy. Individual run
artifacts could be replayed, but there was no durable batch-level result.

## Alternatives considered

- Accept alternating task and submission arguments. This is concise but gives jobs no stable
  identity and is difficult to review or replay.
- Run jobs concurrently by default. This improves throughput but makes duplicate-job cache
  ownership and resource use depend on scheduling.
- Use a versioned manifest, stable job order, sequential execution, and a replayable batch result.

## Decision

Introduce batch manifest schema version 1 with unique job IDs and task/submission paths resolved
relative to the manifest. Jobs execute in lexical ID order regardless of YAML order. Duplicate
task/submission pairs are allowed and reuse the normal cache; duplicate IDs are rejected.

Every job maps to one existing stable exit code. Execution continues after validation, execution,
environment, score, or unexpected failures. The aggregate code uses a documented severity order:
internal error, environment error, invalid task/input, execution failure, score below 100, then
success. The batch persists sorted, sanitized job snapshots atomically in `batch.json`; individual
runs remain ordinary `.repogym/runs` artifacts.

`batch report` replays terminal, JSON, JUnit, or SARIF summaries without executing code. JUnit
uses one testcase per job and exposes underlying test counts as properties. SARIF combines scope
violations and adds a batch-outcome result for every non-successful job.

## External behavior

Users run `repogym batch run MANIFEST` and replay with `repogym batch report BATCH_RUN`. Machine
reports may be printed or written before the command returns the persisted aggregate exit code.
Cache control and artifact roots are explicit CLI options.

## Compatibility and security risks

Unknown manifest versions are rejected rather than guessed. Batch results embed the existing
`GradeResult` schema, so compatible extensions to that model remain readable. Manifest paths may
name any local location the invoking user can access; batch execution is not a sandbox. Paths are
not persisted, and exception/report text crosses the shared redaction boundary.

## Verification

Tests cover schema and duplicate validation, relative path resolution, input-order independence,
mixed success/failure continuation, severity aggregation, duplicate-task cache reuse, distinct run
IDs, a correct 100-point submission, deterministic JSON/JUnit/SARIF/terminal output, path
redaction, output files, replay without execution, and CLI exit-code parity.

# 0011: Per-test execution evidence

Status: Accepted

## Problem and context

RepoGym persists only aggregate test counts parsed from terminal text. Reports cannot identify a
specific regression, recovery, skip, error, or duration change, and synthetic JUnit cases lose the
original pytest identity.

## Current behavior

The test runner executes the configured command directly and searches stdout/stderr for pytest
summary phrases. `GradeResult` contains totals only. Evidence has one aggregate test record,
comparison reports count deltas, and JUnit invents `passed-1` and `failed-1` names. Older run files
must remain readable after adding detail.

## Alternatives considered

- Parse verbose pytest terminal output. Formatting, plugins, tracebacks, and localization make it
  unstable.
- Require an additional pytest plugin dependency. This increases installation and task coupling.
- Request pytest's built-in JUnit XML and parse a bounded, standard-library-readable artifact.

## Decision

For commands recognized as pytest, append a RepoGym-owned `--junitxml` path and parse the file
immediately after execution. Stable case IDs use `classname::name`, with deterministic suffixes
for true duplicates. Case records contain status, duration, a bounded sanitized failure summary,
and references to the already-sanitized aggregate stdout/stderr artifacts; raw per-test captured
output is never persisted.

The version-1 per-test model is embedded in `GradeResult`. Old results receive an explicit
`legacy_run` unavailable state in memory. Non-pytest commands, missing/corrupt structured output,
timeouts, and cancellation also produce reasoned unavailable states. Evidence schema advances to
version 2 and migrates schema-1 documents in memory.

Comparison reports newly failing tests, tests restored to passing, and shared-test duration
changes of at least 0.1 seconds and 50 percent. Terminal, JSON, HTML, and JUnit consume the same
sorted model; JUnit retains its aggregate compatibility adapter only when details are unavailable.

## External behavior

New run JSON and evidence include deterministic per-test data. Report output shows real test IDs,
statuses, durations, and sanitized failure summaries. Comparison adds detailed regression fields
without changing existing score/count fields. Existing task definitions and old run directories
remain valid.

## Compatibility and security risks

Appending JUnit output is limited to pytest commands and does not use a shell. A killed process may
leave partial XML, which is treated as unavailable rather than complete. Failure bodies and
`system-out` are not retained; summaries are length-bounded and redact paths and credential-like
values before persistence. The full result is redacted again at the grading boundary.

## Verification

Tests cover pass, failure, error, skip, duplicate/stable ordering, missing and malformed XML,
timeout and cancellation, legacy result/evidence migration, regression and recovery comparison,
duration thresholds, terminal/JSON/HTML/JUnit rendering, deterministic repeated runs, and path or
token redaction.

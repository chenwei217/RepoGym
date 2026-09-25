# ADR 0006: Deterministic machine report formats

## Problem and context

RepoGym reports were useful to people and bespoke JSON consumers, but common CI test viewers and
code-scanning systems could not ingest runs through their standard JUnit XML and SARIF contracts.

## Current behavior

The report service rehydrated and sanitized a persisted `GradeResult`, then rendered terminal,
JSON, or self-contained HTML. Results contain aggregate test counts and scope-violation strings,
not individual test identities or a separate source-location model.

## Alternatives considered

- Invent per-test identities from captured pytest output. That parser would be fragile and would
  imply evidence that the persisted model does not contain.
- Add JUnit and SARIF only after replacing the result schema. That would delay useful integrations
  and unnecessarily couple additive formats to a breaking migration.
- Serialize the existing aggregate evidence honestly, using stable synthetic JUnit cases and
  extracting SARIF locations only from known violation forms.

## Decision

JUnit uses deterministic synthetic passed, failed, and skipped cases. Skips are the nonnegative
difference between total and recorded pass/fail counts. SARIF 2.1.0 declares stable RepoGym scope
rules, sorts violations, and adds a physical location only when a relative path and optional line
are present. Both formats use the sanitized run model; SARIF also re-applies generic path
redaction when its serializer is called directly.

## External behavior and compatibility risk

`repogym report --format junit|sarif` prints the selected format or writes it with `--output`.
Existing formats and result fields are unchanged. Synthetic JUnit names are stable but are not
real test node IDs. Consumers must not treat inferred skipped cases as separately observed tests.

## Verification

Tests parse XML and JSON, assert format versions and statistics, cover failures, derived skips,
special characters, empty results, deterministic ordering, relative file and line locations,
direct-call path redaction, CLI stdout, and output files.

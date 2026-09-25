# ADR 0007: Stable automation exit codes

## Problem and context

RepoGym returned zero for successful command completion and mostly one for every expected failure.
Automation could not distinguish invalid tasks, process failures, incomplete scores, broken local
environments, and RepoGym defects without parsing human-readable output.

## Current behavior

Validation and doctor used ad hoc `1` exits, domain exceptions flowed through one error helper,
and grading returned zero even for timeouts or scores below 100. Typer separately used code 2 for
command syntax errors.

## Alternatives considered

- Keep one generic nonzero code and require JSON parsing. Not every command has JSON output, and
  process status should remain useful without reading artifacts.
- Reuse nearby POSIX `sysexits` values. Their categories do not express benchmark score outcomes
  and are inconsistently available on Windows.
- Publish a sparse, RepoGym-owned enum while preserving code 2 for framework usage errors.

## Decision

Codes are `0` success, `10` invalid task or input, `20` execution failure, `30` completed grade
below 100, `40` environment or artifact I/O failure, and `70` unexpected internal error. Verify
raises a distinct execution-domain exception after a process has run. Grade prints and persists
its result before returning `20` or `30`. A CLI group boundary maps otherwise unhandled `OSError`
to `40` and unexpected exceptions to `70`; Typer control-flow and usage exceptions pass through.

## External behavior and compatibility risk

Existing success codes remain zero. Scripts that asserted the former generic code 1 must adopt
the published values. A completed grade below 100 now returns 30, which intentionally makes strict
CI fail while still distinguishing a valid benchmark result from infrastructure failure. The
Python service APIs continue to return models or raise domain exceptions and do not return codes.

## Verification

Tests freeze all numeric values and cover invalid validation/list input, unhealthy doctor output,
verification execution failures, completed and incomplete grades, timeout/cancel/error statuses,
terminal and machine report/compare parity, filesystem failures, internal exceptions, and Typer
usage errors. CLI help and shell, PowerShell, and CI documentation publish the same mapping.

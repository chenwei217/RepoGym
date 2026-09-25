# Testing and quality gates

Run the full local gate before every change:

```bash
ruff check .
ruff format --check .
mypy src/repogym
pytest
coverage run -m pytest
coverage report --fail-under=85
```

The suite is organized by responsibility: task loading and validation, command parsing and test
execution, reproducibility, submission and patch security, diagnostics, scoring, comparisons,
machine-report format contracts, and end-to-end CLI workflows. The CI matrix runs the same
checks on Ubuntu and Windows with
Python 3.11 and 3.12, then verifies both bundled tasks and smoke-tests doctor and comparison.

Some link-related tests are skipped on Windows runners without the privilege required to create a
symbolic link. A skip is reported by pytest and must not be used to avoid testing portable
behavior. Tests use only task fixtures and local subprocesses; after dependencies are installed,
the core suite and bundled-task verification require no network connection.

New production behavior needs a normal-path test, an error-path test, and an integration test
where it crosses a CLI, filesystem, subprocess, or persisted-artifact boundary.

JUnit tests parse the emitted XML and assert counts, failures, derived skips, duration, escaping,
and empty results. SARIF tests assert the 2.1.0 contract, stable rule and result ordering, relative
locations, line numbers, empty results, deterministic serialization, and absolute-path redaction.

CLI contract tests assert the numeric exit-code enum, validation versus environment failures,
execution and score outcomes, terminal/machine-format parity, unhandled filesystem errors,
unexpected internal errors, and preservation of the framework's usage-error code.

Cache tests cover key stability and invalidation, atomic-publication cleanup, independent replay
run IDs, stale-lock recovery, thread contention, one-execution concurrent grading, corrupted-entry
recomputation, exclusion of incomplete runs, CLI inspection/verification/clearing, and one-off
cache disabling.

Executor coverage includes independent stdout/stderr limits, encoded Unicode byte boundaries,
large single writes, timeout capture, and persisted truncation evidence. Assertions use encoded
byte counts rather than platform newline assumptions.

Cancellation tests cover pre-cancelled tokens, repeated cancellation, completed and abnormal
exits, nested child cleanup, verification interruption, and persisted grading status. Timeout and
cancellation assertions run on both Windows and Ubuntu to protect their shared cleanup semantics.

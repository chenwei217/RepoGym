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
checks on Ubuntu 24.04 and Windows with Python 3.11 through 3.14, then verifies both bundled tasks and
smoke-tests doctor and comparison. A separate CI job runs Bandit against production code and
pip-audit in a clean environment. GitHub Actions are pinned to immutable commit SHAs and updated
through Dependabot.

Linux test, security, and release jobs explicitly select `ubuntu-24.04`. This prevents an
unreviewed major-image migration through `ubuntu-latest`; hosted image patches and permitted
dependency versions still receive updates. Future OS-major upgrades require an explicit matrix
change and the same full gates. Windows continues using the hosted `windows-latest` baseline.

Run-history tests enforce actual SQLite read-only connections, transaction rollback, legacy
timestamps, corrupt/linked entries, URI-sensitive paths, and preservation of unrelated databases.
Archive tests verify bounded exact membership, hashes and evidence associations, deterministic
exports, tampering, ZIP links/traversal, Windows reserved names, atomic publication and replay.
Catalog tests cover discovery, strict versions, drift, metadata privacy, relative pinned batch
planning and refusal to execute changed tasks. Repetition analysis covers candidate/environment
identity, deduplication, replay exclusions, missing/skipped cases, quantiles and HTML escaping.

Parallel batch tests use synchronization barriers to verify worker/future bounds and serial pair
ordering, exercise real concurrent child-process cancellation, preserve cache-lock ownership on
cancel, and verify continued evaluation after per-job failures. Barriers and events make
worker-bound assertions independent of scheduler speed.

Some link-related tests are skipped on Windows runners without the privilege required to create a
symbolic link. A skip is reported by pytest and must not be used to avoid testing portable
behavior. Tests use only task fixtures and local subprocesses; after dependencies are installed,
the core suite and bundled-task verification require no network connection.

New production behavior needs a normal-path test, an error-path test, and an integration test
where it crosses a CLI, filesystem, subprocess, or persisted-artifact boundary.

Per-test evidence tests cover pass, failure, error, skip, duplicate identities, stable repeated
runs, timeout and corrupt/missing/malicious JUnit input, legacy loading, bounded failure summaries,
and credential/path redaction. JUnit input is parsed with defusedxml. Report tests parse emitted XML
and assert real-case and legacy
aggregate contracts, counts, failures, errors, skips, duration, escaping, and empty results.
SARIF tests assert the 2.1.0 contract, stable rule and result ordering, relative locations, line
numbers, empty results, deterministic serialization, and absolute-path redaction.

Runtime-environment tests freeze platform and package providers to assert repeatable fingerprints,
missing-dependency behavior, fingerprint validation, privacy exclusions, CLI terminal/JSON parity,
persisted grading evidence, legacy availability, report rendering, and sorted comparison diffs.

Authoring tests cover interactive and non-interactive scaffolding, paths containing spaces,
immediate structural validation, invalid IDs and traversal attempts, duplicate protection,
validation-failure cleanup, placeholder and empty content, conflicting counts, risky commands,
stable CLI exit codes, and compatibility with both bundled tasks.

CLI contract tests assert the numeric exit-code enum, validation versus environment failures,
execution and score outcomes, terminal/machine-format parity, unhandled filesystem errors,
unexpected internal errors, and preservation of the framework's usage-error code.

Cache tests cover key stability and invalidation, atomic-publication cleanup, independent replay
run IDs, stale-lock recovery, thread contention, one-execution concurrent grading, corrupted-entry
recomputation, exclusion of incomplete runs, CLI inspection/verification/clearing, and one-off
cache disabling.

Plugin tests cover deterministic entry-point ordering, API compatibility, duplicate-name policy,
malformed and raising imports, loader schema validation, executor DTO conversion and cancellation,
report redaction, CLI diagnostics, and isolation from built-in commands.

Batch tests cover manifest versions and duplicate IDs, relative paths, order-independent sorting,
mixed-outcome continuation, exit severity, duplicate-task cache hits, 100-point grading, atomic
persistence, four deterministic/redacted report formats, output files, and replay without task
execution.

Executor coverage includes independent stdout/stderr limits, encoded Unicode byte boundaries,
large single writes, timeout capture, and persisted truncation evidence. Assertions use encoded
byte counts rather than platform newline assumptions.

Cancellation tests cover pre-cancelled tokens, repeated cancellation, completed and abnormal
exits, nested child cleanup, verification interruption, and persisted grading status. Timeout and
cancellation assertions run on both Windows and Ubuntu to protect their shared cleanup semantics.

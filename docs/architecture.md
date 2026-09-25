# Architecture

RepoGym uses a linear pipeline with small modules and explicit data models.

1. `loader` migrates versioned task mappings and parses them into strict Pydantic models.
2. `validator` checks layout, safe relative paths, test discovery, and constraint overlap.
3. `doctor` inspects the local Python runtime, command, dependencies, working directory, and
   discovered tests without executing candidate code. It uses the same resolved command as the
   execution path and reports the executable it actually checked.
4. `reproducibility` hashes every task input, including the reference patch, into a stable
   SHA-256 identity.
5. `security` audits submission trees before copying, records content hashes, and applies the
   shared redaction policy used by persistence and reporting.
6. `Executor` abstracts command execution; `LocalExecutor` owns the exact child process, drains
   both pipes into bounded head/tail buffers, and uses `psutil` to terminate descendants on
   timeout or cooperative cancellation.
7. `verifier` compares the starter failure count with metadata, applies a strict unified diff,
   and proves the reference result.
8. `grader` overlays a candidate, runs all and public tests, then persists artifacts and
   structured execution evidence.
9. `scoring` computes independent deterministic dimensions.
10. `reports` rehydrates `result.json` and renders terminal, JSON, or escaped HTML.
11. `comparison` computes stable A-to-B deltas without re-executing either run.
12. `bundles` exports the fingerprint input surface and verifies it before atomic import.

The public Python surface is intentionally small: `load_task`, `validate_task`, `verify_task`,
`grade_submission`, report generation, and comparison are the supported orchestration entry
points. The Typer CLI is a thin adapter over those services. Executor implementations conform to
the `Executor` protocol; today only `LocalExecutor` is shipped.

The configured test command is generic rather than pytest-specific, but the MVP count adapter
parses pytest summary output. Public tests are run separately for regression scoring. Submission
deletions are not represented by an overlay directory in the MVP; submissions add or replace
files. Reference patches deliberately support modifications only—file creation, deletion, and
rename are excluded to keep the bundled applier small and auditable.

Command resolution tokenizes the configured string once. An exact first token of `python` or
`python.exe` is replaced with `sys.executable` before both doctor diagnostics and execution, so
the two paths cannot select different Python installations through `PATH`. Absolute Python
paths, alternate interpreter names, and all other commands retain their configured first token.
The resolved argument vector is executed directly and never through a shell.

`CancellationToken` is a thread-safe one-way signal in the public executor protocol. A token set
before launch produces a cancelled result without starting a process. During execution the local
backend polls the token and timeout deadline, giving a completed process precedence when both are
observed together, then routes cancellation and timeout through the same terminate/wait/kill
cleanup. Verification reports cancellation as a domain error; grading persists a zero-score
cancelled result and does not launch remaining test or quality commands.

`result.json` records the task fingerprint plus sanitized argv, exit code, timeout state,
duration, `<WORKSPACE>` working directory, output filenames, termination diagnostics, and the
test-statistics source. Output evidence includes original byte counts and per-stream truncation
flags. The executor retains bounded beginnings and endings while continuously draining the child
pipes, preventing pipe deadlocks and unbounded capture memory without losing the final pytest
summary. `metadata.json` contains the same structured evidence with creation time and schema
version. Old results using `execution.command` remain readable. Neither file stores the original
task or submission absolute path. Loading an existing run applies redaction again before
terminal, JSON, HTML, or comparison rendering.

The fingerprint incorporates length-prefixed normalized relative paths and file bytes in lexical
path order. Required inputs are `task.yaml`, prompt/description, `starter/`, public tests, private
tests, and `reference/solution.patch`. Missing inputs are an error. Length prefixes prevent
ambiguous concatenation, ordering makes the digest stable, and byte-level hashing makes
line-ending or encoding changes visible.

## Current architectural boundaries

Task definitions and run artifacts are versioned independently. `TaskSpec.schema_version`
selects the YAML format and its migration path, while `TaskSpec.version` describes the task
contract. Unversioned and explicit v0 definitions normalize in memory to v1; unknown future
versions are rejected. Result loading separately adapts the original execution-evidence field
name. Task inputs can also be exported as package format version 1. Import accepts exactly the
members declared by the manifest and publishes a task only after archive safety, content
integrity, TaskSpec validation, and full fingerprint verification succeed.

# Architecture

RepoGym uses a linear pipeline with small modules and explicit data models.

1. `loader` parses YAML into strict Pydantic models.
2. `validator` checks layout, safe relative paths, test discovery, and constraint overlap.
3. `doctor` inspects the local Python runtime, command, dependencies, working directory, and
   discovered tests without executing candidate code.
4. `reproducibility` hashes every task input, including the reference patch, into a stable
   SHA-256 identity.
5. `security` audits submission trees before copying, records content hashes, and applies the
   shared redaction policy used by persistence and reporting.
6. `Executor` abstracts command execution; `LocalExecutor` owns the exact child process and
   uses `psutil` to terminate its descendants on timeout.
7. `verifier` compares the starter failure count with metadata, applies a strict unified diff,
   and proves the reference result.
8. `grader` overlays a candidate, runs all and public tests, then persists artifacts and
   structured execution evidence.
9. `scoring` computes independent deterministic dimensions.
10. `reports` rehydrates `result.json` and renders terminal, JSON, or escaped HTML.
11. `comparison` computes stable A-to-B deltas without re-executing either run.

The configured test command is generic rather than pytest-specific, but the MVP count adapter
parses pytest summary output. Public tests are run separately for regression scoring. Submission
deletions are not represented by an overlay directory in the MVP; submissions add or replace
files. Reference patches deliberately support modifications only—file creation, deletion, and
rename are excluded to keep the bundled applier small and auditable.

`result.json` records the task fingerprint plus sanitized argv, exit code, timeout state,
duration, `<WORKSPACE>` working directory, output filenames, termination diagnostics, and the
test-statistics source. `metadata.json` contains the same structured evidence with creation time
and schema version. Old results using `execution.command` remain readable. Neither file stores
the original task or submission absolute path. Loading an existing run applies redaction again
before terminal, JSON, HTML, or comparison rendering.

The fingerprint incorporates length-prefixed normalized relative paths and file bytes in lexical
path order. Required inputs are `task.yaml`, prompt/description, `starter/`, public tests, private
tests, and `reference/solution.patch`. Missing inputs are an error. Length prefixes prevent
ambiguous concatenation, ordering makes the digest stable, and byte-level hashing makes
line-ending or encoding changes visible.

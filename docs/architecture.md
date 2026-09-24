# Architecture

RepoGym uses a linear pipeline with small modules and explicit data models.

1. `loader` parses YAML into strict Pydantic models.
2. `validator` checks layout, safe relative paths, test discovery, and constraint overlap.
3. `doctor` inspects the local Python runtime, command, dependencies, working directory, and
   discovered tests without executing candidate code.
4. `reproducibility` hashes the task definition, prompt, starter tree, and tests into a stable
   SHA-256 identity.
5. `security` copies regular files into a temporary workspace, records content hashes, and
   redacts known local paths from persisted evidence.
6. `Executor` abstracts command execution; `LocalExecutor` is the MVP implementation.
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

`result.json` records the sanitized command argument vector, exit code, timeout state, and
`pytest_summary` as the test statistics source. `metadata.json` contains the task fingerprint,
creation time, schema version, and sanitized execution fields. Neither file stores the original
task or submission absolute path. Known local roots are also replaced in captured stdout and
stderr before those artifacts are written.

The fingerprint incorporates length-prefixed relative paths and file bytes in lexical path
order. Length prefixes prevent ambiguous concatenation, path ordering makes the digest stable,
and byte-level hashing makes line-ending or encoding changes visible.

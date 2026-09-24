# Architecture

RepoGym uses a linear pipeline with small modules and explicit data models.

1. `loader` parses YAML into strict Pydantic models.
2. `validator` checks layout, safe relative paths, test discovery, and constraint overlap.
3. `security` copies regular files into a temporary workspace and records content hashes.
4. `Executor` abstracts command execution; `LocalExecutor` is the MVP implementation.
5. `verifier` compares the starter failure count with metadata, applies a strict unified diff,
   and proves the reference result.
6. `grader` overlays a candidate, runs all and public tests, then persists artifacts.
7. `scoring` computes independent deterministic dimensions.
8. `reports` rehydrates `result.json` and renders terminal, JSON, or escaped HTML.

The configured test command is generic rather than pytest-specific, but the MVP count adapter
parses pytest summary output. Public tests are run separately for regression scoring. Submission
deletions are not represented by an overlay directory in the MVP; submissions add or replace
files. Reference patches deliberately support modifications only—file creation, deletion, and
rename are excluded to keep the bundled applier small and auditable.

Run directories contain absolute source paths in `metadata.json` for local traceability. They
are ignored by Git and should be sanitized before sharing if local path disclosure matters.


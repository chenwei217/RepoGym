# Engineering roadmap

This roadmap records audited facts and prioritized work. It is not a release promise.

## Current capabilities

- versioned YAML task loading with legacy migration, structural validation, reference-patch
  verification, and deterministic SHA-256 fingerprints of task inputs;
- a local cross-platform executor with direct argv execution, timeout process-tree cleanup, and
  an active-interpreter binding for generic Python test commands, plus an explicit optional
  Docker/OCI adapter with declared isolation and resource policy;
- preflight submission auditing, safe copying, path redaction, scoring, persisted evidence, and
  terminal, JSON, HTML, JUnit XML, and SARIF reports;
- stable automation exit codes separating invalid input, execution, score, environment, and
  internal failures;
- content-addressed execution caching with per-key locks, atomic publication, corruption recovery,
  explicit invalidation inputs, and CLI maintenance;
- versioned task-loader, executor, and reporter plugin contracts with isolated deterministic
  discovery and stable adapters;
- deterministic batch evaluation with failure continuation, cache reuse, replayable artifacts,
  four summary formats, and stable aggregate exit codes;
- deterministic comparison of persisted runs; and
- Windows and Ubuntu CI on Python 3.11–3.14, with an 85% branch-coverage floor;
- a rebuildable transactional run inventory with filters, pagination, and stale-source checks.

## Confirmed gaps and technical debt

| Priority | Need | Acceptance criteria | Likely modules |
| --- | --- | --- | --- |
| P1 | Hardened remote/VM execution | A separately operated backend authenticates requests, transfers only verified bundles, contains hostile kernels/runtime escapes, and returns signed evidence. | executor plugin, bundle transport, deployment docs |

## Completed roadmap items

- Derived run history, verified portable run archives, and fingerprint-pinned local catalogs now
  support finding, moving, and curating evaluation artifacts without executing task code.
- Repeated-run analysis groups equal task/candidate/environment identities and distinguishes
  missing data, cache replays, observed test variation, and incomplete duration measurements.

- TaskSpec schema version 1 is explicit; unversioned and v0 definitions migrate in memory, and
  unknown versions fail with stable compatibility errors.
- Local execution drains stdout and stderr into independently configurable bounded buffers while
  recording original byte counts and truncation evidence.
- A thread-safe cancellation token stops launches or active process trees, records a distinct
  cancelled result, and prevents remaining grading commands from starting.
- Evidence schema v2 unifies command, aggregate/per-test, persisted runtime-environment, and
  artifact records with stable ordering and in-memory adapters for older runs.
- JUnit XML exposes aggregate test outcomes and SARIF 2.1.0 exposes sorted scope violations with
  stable rules, optional relative locations, and shared path redaction.
- CLI exit codes provide one outcome mapping across terminal and machine-oriented commands while
  retaining Typer's standard syntax-error code.
- Completed grades use a versioned content-addressed cache; cache hits create distinct replay runs,
  while per-key locks, hashes, atomic rename, and re-execution recover contention and corruption.
- Portable task package format version 1 exports the complete fingerprint input surface with
  hashes and a non-secret environment summary. Import validates archive safety, exact membership,
  integrity, task structure, and fingerprint before atomic publication.
- Plugin API version 1 discovers loader, executor, and reporter registrations deterministically;
  incompatible, conflicting, malformed, and raising plugins remain isolated diagnostics.
- Batch schema version 1 sorts jobs independently of manifest order, continues after job failures,
  reuses cache and run evidence, and replays terminal, JSON, JUnit, and SARIF summaries.
- Pytest execution persists sorted versioned case identities, outcomes, durations, bounded failure
  summaries, and output references. Reports render real cases, comparisons locate regressions,
  recoveries, and significant duration changes, and old runs remain explicitly compatible.
- Environment schema v1 persists a fixed non-sensitive runtime allowlist and canonical digest.
  CLI and reports render it, cache keys include it, and comparison explains sorted differences
  without substituting the reader's environment for legacy runs.
- Task scaffolding validates in a same-filesystem staging tree before atomic publication;
  interactive/non-interactive CLI paths and coded author lint cover placeholders, incomplete
  counts, risky commands, broad scope, duplicate targets, and path traversal.
- Executor capabilities distinguish host and container controls. Explicit Docker execution uses a
  read-only root, workspace bind, default-disabled network, resource/PID limits, availability
  diagnostics, stopped-container cleanup, and fail-closed selection without changing local default.

## Test gaps

- Nested-child timeout coverage is intentionally platform-constrained; Windows link tests skip
  when the runner lacks link-creation privileges.
- Plugin contracts have unit and CLI integration coverage; independently packaged fixture wheels
  are not yet built and installed in CI.
- Batch scheduling now has bounded opt-in parallelism, shared cancellation, and per-pair ordering;
  recoverable incremental batch checkpoints/resume are not yet implemented.
- Language-specific structured adapters beyond pytest are not yet implemented.
- Core tests need no network after dependencies are installed. A fresh editable installation does
  require package retrieval unless a local wheelhouse is supplied.

## Delivery order

A hardened remote or disposable-VM backend is the next security priority for hostile workloads.

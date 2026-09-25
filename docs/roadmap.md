# Engineering roadmap

This roadmap records audited facts and prioritized work. It is not a release promise.

## Current capabilities

- versioned YAML task loading with legacy migration, structural validation, reference-patch
  verification, and deterministic SHA-256 fingerprints of task inputs;
- a local cross-platform executor with direct argv execution, timeout process-tree cleanup, and
  an active-interpreter binding for generic Python test commands;
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
- Windows and Ubuntu CI on Python 3.11 and 3.12, with an 85% branch-coverage floor.

## Confirmed gaps and technical debt

| Priority | Need | Acceptance criteria | Likely modules |
| --- | --- | --- | --- |
| P1 | Sandboxed execution backend | A separately configured backend enforces filesystem, network, CPU, memory, and process limits without weakening the local executor contract. | `executors`, `plugins`, deployment docs |
| P2 | Per-test evidence | Persist stable test-case identities and outcomes so JUnit no longer needs aggregate or job-level adapters. | `testing`, `evidence`, `reports` |

## Completed roadmap items

- TaskSpec schema version 1 is explicit; unversioned and v0 definitions migrate in memory, and
  unknown versions fail with stable compatibility errors.
- Local execution drains stdout and stderr into independently configurable bounded buffers while
  recording original byte counts and truncation evidence.
- A thread-safe cancellation token stops launches or active process trees, records a distinct
  cancelled result, and prevents remaining grading commands from starting.
- Evidence schema v1 unifies command, test, non-secret environment, and artifact records with
  stable ordering and an in-memory adapter for older runs.
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

## Test gaps

- Nested-child timeout coverage is intentionally platform-constrained; Windows link tests skip
  when the runner lacks link-creation privileges.
- Plugin contracts have unit and CLI integration coverage; independently packaged fixture wheels
  are not yet built and installed in CI.
- Batch execution is sequential by design; controlled parallel scheduling has not been specified.
- Persisted grading currently contains aggregate test counts rather than per-test identities.
- Core tests need no network after dependencies are installed. A fresh editable installation does
  require package retrieval unless a local wheelhouse is supplied.

## Delivery order

A separately configured sandboxed backend is the next security priority. Per-test evidence is the
next reporting priority now that single and batch report contracts are stable.

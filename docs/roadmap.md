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
- deterministic comparison of persisted runs; and
- Windows and Ubuntu CI on Python 3.11 and 3.12, with an 85% branch-coverage floor.

## Confirmed gaps and technical debt

| Priority | Need | Acceptance criteria | Likely modules |
| --- | --- | --- | --- |
| P2 | Stable plugin contracts | Versioned loader, executor, and reporter protocols isolate load failures and have conflict tests plus a minimal example. | `plugins`, `executors`, `reports` |

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

## Test gaps

- Nested-child timeout coverage is intentionally platform-constrained; Windows link tests skip
  when the runner lacks link-creation privileges.
- No plugin contract tests exist yet because that capability does not exist.
- Core tests need no network after dependencies are installed. A fresh editable installation does
  require package retrieval unless a local wheelhouse is supplied.

## Delivery order

Versioned plugin contracts are the next priority now that task, execution, evidence, report, and
cache boundaries are explicit.

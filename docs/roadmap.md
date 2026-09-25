# Engineering roadmap

This roadmap records audited facts and prioritized work. It is not a release promise.

## Current capabilities

- strict YAML task loading, structural validation, reference-patch verification, and deterministic
  SHA-256 fingerprints of task inputs;
- a local cross-platform executor with direct argv execution, timeout process-tree cleanup, and
  an active-interpreter binding for generic Python test commands;
- preflight submission auditing, safe copying, path redaction, scoring, persisted evidence, and
  terminal, JSON, and HTML reports;
- deterministic comparison of persisted runs; and
- Windows and Ubuntu CI on Python 3.11 and 3.12, with an 85% branch-coverage floor.

## Confirmed gaps and technical debt

| Priority | Need | Acceptance criteria | Likely modules |
| --- | --- | --- | --- |
| P1 | Versioned TaskSpec migrations | A declared schema version selects a documented migration path; legacy fixtures load identically or fail with an actionable error. | `models`, `loader`, `validator` |
| P1 | Bounded execution output and cancellation | A caller can cancel an execution; stdout/stderr are bounded with explicit truncation evidence; timeout and cancellation clean the same process tree on Windows and Linux. | `executors`, `models`, `grader` |
| P1 | Machine-oriented reports | JUnit XML and SARIF serializers have stable schemas, redact sensitive paths, and carry actionable locations when available. | `reports`, `cli`, `models` |
| P2 | Cache and incremental execution | Cache keys include task fingerprint, resolved command, and relevant inputs; writes are atomic, corrupt entries recover, and CLI inspection/clearing is tested. | `cache`, `grader`, `cli` |
| P2 | Stable plugin contracts | Versioned loader, executor, and reporter protocols isolate load failures and have conflict tests plus a minimal example. | `plugins`, `executors`, `reports` |

## Completed roadmap items

- Portable task package format version 1 exports the complete fingerprint input surface with
  hashes and a non-secret environment summary. Import validates archive safety, exact membership,
  integrity, task structure, and fingerprint before atomic publication.

## Test gaps

- Nested-child timeout coverage is intentionally platform-constrained; Windows link tests skip
  when the runner lacks link-creation privileges.
- No cache-contention, cancellation, schema-migration, JUnit, SARIF, or plugin contract tests
  exist yet because those capabilities do not exist.
- Core tests need no network after dependencies are installed. A fresh editable installation does
  require package retrieval unless a local wheelhouse is supplied.

## Delivery order

TaskSpec migrations, bounded lifecycle controls, and machine reports are the next priorities
because they build on stable task, package, and evidence contracts. Caching and plugins remain
later: their contracts should be designed after those formats are stable.

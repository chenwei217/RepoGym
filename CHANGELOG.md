# Changelog

All notable changes to this project will be documented here. The format follows Keep a
Changelog, and versions follow Semantic Versioning.

## [Unreleased]

- Enforced read-only run-history queries, rejected accidental adoption of foreign SQLite files,
  and closed test database connections explicitly to avoid delayed resource warnings.

- Added bounded opt-in parallel batch workers, deterministic pair ordering, shared process
  cancellation, isolated path failures, and versioned scheduling policy evidence.

- Added comparable repeated-run analysis in terminal/JSON/HTML with candidate content identity,
  replay exclusions, per-test variation, and measured-only timing distributions.
- Extended runtime identity to include the direct `defusedxml` dependency.

- Added portable pinned task catalogs, metadata filtering and drift diagnostics, and batch planning
  with execution-time task fingerprint checks while retaining legacy unpinned manifests.

- Added deterministic, sanitized run archives with bounded integrity verification, evidence
  association checks, exclusive atomic import, and offline report replay.

- Applied shared credential filtering to captured diagnostics, structured values, and legacy report
  replay, including authentication headers, labeled secrets, URL passwords, and private-key blocks.

- Added searchable run history with transactional rebuilds, legacy compatibility, and coded
  invalid-artifact diagnostics (`runs refresh`, `runs list`, `runs show`).

### Added

- Least-privilege, SHA-pinned CI with Python 3.11-3.14 coverage, Bandit, pip-audit, Dependabot,
  structured contribution templates, and explicit maintenance/support policies
- PEP 561 typed-package metadata and an explicit compatibility policy for documented APIs,
  schemas, artifacts, plugins, CLI automation, and supported Python versions
- CI-gated, fail-closed GitHub Release automation with exact tag/commit verification, clean builds,
  offline wheel installation, checksums, and visibility-aware artifact attestation

### Security

- Rejected XML entities in pytest JUnit evidence and replaced optimization-sensitive execution
  assertions with explicit runtime checks
- Documented the plan-compatible private security contact path without exposing a dead advisory URL

## [0.2.0] - 2026-09-28

### Added

- Versioned TaskSpec schemas with deterministic legacy migration and future-version rejection
- Memory-bounded stdout and stderr capture with byte counts and truncation evidence
- Cooperative execution cancellation with process-tree cleanup and persisted cancellation status
- Versioned, deterministic command/test/environment/artifact evidence documents
- Deterministic JUnit XML and SARIF 2.1.0 machine reports
- Stable CLI exit codes for invalid input, execution, score, environment, and internal failures
- Atomic content-addressed execution cache with locking, integrity recovery, and CLI maintenance
- Versioned task-loader, executor, and reporter plugin contracts with isolated discovery
- Deterministic batch evaluation with cache reuse, failure isolation, replay, and four summaries
- Deterministic SHA-256 task fingerprints persisted with run metadata
- `repogym doctor` environment diagnostics
- Terminal and JSON comparison of persisted grading runs
- Structured execution evidence in `result.json`
- Preflight submission auditing before candidate files are copied or executed
- Recursive timeout cleanup for the exact local process tree
- CLI output-file support for terminal and JSON run comparisons
- Reproducibility and run-comparison workflow documentation
- Versioned task bundle export and integrity-checked atomic import
- Versioned per-test pytest evidence with stable IDs, detailed reports, and regression comparison
- Comparable versioned runtime environments in grading, reports, CLI, cache keys, and comparisons
- Atomic task scaffolding and coded author lint diagnostics
- Optional Docker/OCI execution with capability diagnostics, resource policy, and fail-closed selection
- Distribution build and isolated wheel-install verification

### Changed

- Removed task and submission absolute paths from persisted metadata
- Expanded fingerprints to include public/private tests and `reference/solution.patch`
- Expanded execution evidence with duration, workspace placeholder, output files, and cleanup data
- Unified local-path redaction across output, JSON, terminal, HTML, and comparisons
- Comparisons now reject task-ID mismatches and warn on fingerprint mismatches
- JUnit reports use real pytest cases when available and retain aggregate legacy compatibility
- Made the Quick Start checkout path portable across case-sensitive filesystems

## [0.1.0] - 2026-09-25

### Added

- Strict task specification validation
- Local verification and deterministic submission grading
- Terminal, JSON, and standalone HTML reports
- Original cache TTL and configuration merge example tasks
- Cross-platform CI for Python 3.11 and 3.12

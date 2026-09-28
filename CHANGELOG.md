# Changelog

All notable changes to this project will be documented here. The format follows Keep a
Changelog, and versions follow Semantic Versioning.

## [Unreleased]

### Added

- Least-privilege, SHA-pinned CI with Python 3.11-3.14 coverage, Bandit, pip-audit, Dependabot,
  structured contribution templates, and explicit maintenance/support policies

### Security

- Rejected XML entities in pytest JUnit evidence and replaced optimization-sensitive execution
  assertions with explicit runtime checks

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

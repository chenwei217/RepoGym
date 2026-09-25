# Changelog

All notable changes to this project will be documented here. The format follows Keep a
Changelog, and versions follow Semantic Versioning.

## [Unreleased]

### Added

- Versioned TaskSpec schemas with deterministic legacy migration and future-version rejection
- Deterministic SHA-256 task fingerprints persisted with run metadata
- `repogym doctor` environment diagnostics
- Terminal and JSON comparison of persisted grading runs
- Structured execution evidence in `result.json`
- Preflight submission auditing before candidate files are copied or executed
- Recursive timeout cleanup for the exact local process tree
- CLI output-file support for terminal and JSON run comparisons
- Reproducibility and run-comparison workflow documentation
- Versioned task bundle export and integrity-checked atomic import

### Changed

- Removed task and submission absolute paths from persisted metadata
- Expanded fingerprints to include public/private tests and `reference/solution.patch`
- Expanded execution evidence with duration, workspace placeholder, output files, and cleanup data
- Unified local-path redaction across output, JSON, terminal, HTML, and comparisons
- Comparisons now reject task-ID mismatches and warn on fingerprint mismatches

## [0.1.0] - 2026-09-25

### Added

- Strict task specification validation
- Local verification and deterministic submission grading
- Terminal, JSON, and standalone HTML reports
- Original cache TTL and configuration merge example tasks
- Cross-platform CI for Python 3.11 and 3.12

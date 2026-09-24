# Changelog

All notable changes to this project will be documented here. The format follows Keep a
Changelog, and versions follow Semantic Versioning.

## [Unreleased]

### Added

- Deterministic SHA-256 task fingerprints persisted with run metadata
- `repogym doctor` environment diagnostics
- Terminal and JSON comparison of persisted grading runs
- Structured execution evidence in `result.json`

### Changed

- Removed task and submission absolute paths from persisted metadata
- Redacted known local paths from captured process output

## [0.1.0] - 2026-09-25

### Added

- Strict task specification validation
- Local verification and deterministic submission grading
- Terminal, JSON, and standalone HTML reports
- Original cache TTL and configuration merge example tasks
- Cross-platform CI for Python 3.11 and 3.12

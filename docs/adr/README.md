# Architecture decision records

ADRs capture decisions that change a public contract, trust boundary, persisted format, or
cross-platform behavior. They are immutable once accepted; a later decision supersedes an older
one rather than rewriting it.

Each record uses a numeric filename and states the problem, current behavior, alternatives,
decision, external behavior, compatibility risk, and verification method. Records describe the
reasoning for a change; implementation and user guidance belong in the relevant module and
feature documentation.

- [0001: Reproducible task bundles](0001-reproducible-task-bundles.md)
- [0002: Versioned TaskSpec migrations](0002-versioned-task-spec-migrations.md)
- [0003: Bounded process output capture](0003-bounded-process-output.md)
- [0004: Cooperative execution cancellation](0004-cooperative-execution-cancellation.md)
- [0005: Versioned structured execution evidence](0005-versioned-execution-evidence.md)
- [0006: Deterministic machine report formats](0006-machine-report-formats.md)
- [0007: Stable automation exit codes](0007-stable-automation-exit-codes.md)
- [0008: Atomic incremental execution cache](0008-atomic-execution-cache.md)
- [0009: Versioned plugin contracts](0009-versioned-plugin-contracts.md)
- [0010: Deterministic batch evaluation](0010-deterministic-batch-evaluation.md)
- [0011: Per-test execution evidence](0011-per-test-execution-evidence.md)
- [0012: Comparable runtime environments](0012-comparable-runtime-environments.md)
- [0013: Atomic task scaffolding and author lint](0013-task-authoring-workflow.md)
- [0014: Optional container isolation executor](0014-optional-container-executor.md)
- [0015: CI-gated releases](0015-ci-gated-release-automation.md)
- [0016: Queryable run history](0016-queryable-run-history.md)
- [0017: Shared credential filtering](0017-shared-credential-redaction.md)
- [0018: Portable run archives](0018-portable-run-archives.md)
- [0019: Pinned local task catalogs](0019-pinned-task-catalogs.md)

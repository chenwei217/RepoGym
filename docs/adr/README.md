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

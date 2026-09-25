# Security overview

RepoGym evaluates trusted task and submission code. It is not a sandbox: the local executor runs
with the invoking user's privileges and network access. Use a disposable VM or an independently
hardened container for untrusted material.

The project validates relative task paths, audits submission trees before copying, rejects links
and special files, applies patches within the workspace, starts commands with `shell=False`,
cleans the recorded process tree after a timeout, and redacts local absolute paths from persisted
results and report formats. Generic `python` task commands resolve to the active interpreter so
diagnostics and execution do not diverge through `PATH` precedence.

Portable task bundle import treats ZIP metadata and contents as untrusted. It rejects absolute or
traversing paths, backslash ambiguity, symbolic links, duplicate and case-conflicting names,
undeclared members, oversized content, and hash mismatches. Extraction occurs in a temporary
directory and the validated task is atomically published only when the final destination does not
already exist.

This overview is intentionally concise. The trust boundary, deployment guidance, and individual
defensive controls are specified in [the security model](security-model.md). Report suspected
vulnerabilities through the process in the repository-level [security policy](../SECURITY.md).

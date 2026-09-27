# 0012: Comparable runtime environments

Status: Accepted

## Problem and context

A task fingerprint identifies versioned task inputs but not the interpreter, operating system,
dependencies, RepoGym version, or executor that produced a run. The existing evidence builder
reads a few current-process values while rendering evidence, so old artifact reconstruction can
incorrectly describe the machine doing the reading rather than the original execution.

## Current behavior

`result.json` has no environment object. `evidence.json` records Python implementation/version
and OS family without its own schema or comparison behavior. There is no CLI for inspecting the
exact snapshot that a new grade will persist.

## Alternatives considered

- Persist all environment variables and installed distributions. This is noisy, unstable, and
  likely to disclose credentials or local identity.
- Persist only a digest. This supports equality but cannot explain a difference.
- Persist a fixed allowlist of non-sensitive facts plus a canonical digest.

## Decision

Runtime environment schema version 1 records Python implementation/version, OS family/release,
architecture, RepoGym version, six direct runtime dependency versions, and a stable executor
identity. Canonical sorted JSON is SHA-256 hashed. Paths, executable locations, environment
variables, usernames, hostnames, process IDs, and arbitrary installed packages are excluded.

The snapshot is collected once at grading time and embedded in the result. Evidence consumes that
snapshot rather than inspecting the reader's machine. Old runs receive an explicit `legacy_run`
unavailable state. `repogym environment` shows the same local-executor snapshot in terminal or
JSON form. Comparison exposes sorted field-level differences and a prominent mismatch warning.

## External behavior

New run JSON, metadata, evidence, terminal reports, and HTML reports include the environment
fingerprint and non-sensitive details. Comparison JSON contains availability, equality, and
field differences; terminal comparison warns when snapshots differ.

## Compatibility and security risks

Existing artifacts remain readable and are never rewritten. Dependency names are a fixed internal
allowlist, so a malicious or private package name is not enumerated. OS release and architecture
describe compatibility but do not identify a host. Executor identities must never use object
`repr` values because those can contain memory addresses or configuration secrets.

## Verification

Tests freeze platform and package version providers to prove stable fingerprints, mutate each
category to prove readable comparison differences, verify legacy behavior, exercise both CLI
formats and report rendering, and assert that paths, environment values, usernames, and hostnames
do not appear.

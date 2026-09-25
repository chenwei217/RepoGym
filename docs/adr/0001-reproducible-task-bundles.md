# ADR 0001: use a verified ZIP task package

## Status

Accepted and implemented.

## Problem and current behavior

RepoGym fingerprints and verifies a task directory in place, but cannot move that verified task
between machines as one integrity-checked artifact. Copying directories manually provides no
manifest, hash check, or import safety boundary.

## Alternatives

- Keep directory copying and publish a checksum beside it.
- Depend on an external archive tool and document a convention.
- Use a standard-library ZIP archive with an in-archive JSON manifest.

## Decision

Use a versioned ZIP package with a deterministic lexical file manifest. The manifest records the
task ID and version, task fingerprint, SHA-256 and byte size for every packaged task input, and a
non-secret exporter environment summary. Import validates every ZIP member, rejects traversal,
links, duplicates, unexpected files, missing files, and hash mismatches, then validates the
extracted task and fingerprint before atomically publishing it into the destination directory.

## External behavior and compatibility

The CLI will expose explicit export and import commands. Package format version 1 is new and does
not change existing task directories or grading artifacts. Future incompatible package formats
require a new parser or migration path; unknown versions fail clearly.

## Verification

Tests cover a round trip, stable manifest ordering, corruption, missing members, unsafe ZIP paths,
link metadata, cross-platform name collisions, invalid extracted tasks, and CLI success/failure
paths. The full lint, type, test, and coverage gates remain required.

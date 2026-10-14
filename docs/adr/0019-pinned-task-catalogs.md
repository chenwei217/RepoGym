# 0019: Pinned local task catalogs

## Problem and current behavior

Task listing skips invalid tasks and batch manifests point at mutable directories. There is no
portable inventory for curating an evaluation set or detecting task changes before execution.

## Alternatives and decision

A hosted task registry introduces credentials and transport before local curation works. Store a
versioned JSON catalog of direct task IDs, metadata, and complete existing task fingerprints.
Discover without executing code, fail on invalid entries, and verify against an explicitly chosen
task root. Generate relative batch paths with optional expected fingerprints in batch schema 1.

## External behavior and compatibility

`catalog create`, `catalog list`, `catalog verify`, and `catalog batch` curate and pin tasks.
Metadata is privacy-filtered. No absolute source root is stored in the catalog. Existing unpinned
batch manifests retain their behavior; pinned jobs reject a changed task before grading. Extra
unselected tasks do not invalidate a curated catalog. Creation and batch export refuse overwrite.
Task trees must remain stable during validation/execution, matching the existing local trust model.

## Acceptance

Cover current examples, sorted discovery, malformed and linked tasks, strict schema versions,
duplicate IDs, metadata/fingerprint drift, missing submissions, portable relative batch paths,
CLI JSON/terminal behavior, and pre-execution rejection of changed pinned tasks.

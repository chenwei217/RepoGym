# ADR 0003: Bounded process output capture

## Problem and context

`subprocess.communicate()` drained pipes safely but accumulated every output byte in memory. A
noisy or defective task could exhaust the RepoGym process before its timeout was reached.

## Current behavior

The local executor returned complete decoded stdout and stderr. Reports persisted those strings
without recording their original size or whether output had been omitted.

## Alternatives considered

- Truncate after `communicate()`. This limits artifacts but not peak memory.
- Stop reading after a limit. This can fill an OS pipe and deadlock the child.
- Stream complete output to temporary files. This bounds memory but permits unbounded disk use and
  complicates cleanup.
- Drain continuously and retain bounded head and tail segments independently for each stream.

## Decision

Reader threads continuously drain stdout and stderr. Each stream tracks its original byte count
while retaining at most its configured positive limit, divided between the beginning and end.
The default is 1 MiB per stream. A deterministic marker separates retained segments after
truncation. Byte bounds are applied before UTF-8 replacement decoding; the final test summary in
the retained tail remains available to the pytest count adapter.

## External behavior and compatibility risk

`ExecutionResult` and persisted execution evidence add byte-count and truncation fields with
backward-compatible defaults. Very large output artifacts now omit their middle section. Python
callers may configure independent limits through `LocalExecutor`; task commands and CLI defaults
are unchanged.

## Verification

Tests cover untruncated output, independent stream limits, large writes, Unicode byte splits,
nonpositive configuration, timeout output, test-summary parsing, and persisted evidence. The
cross-platform CI matrix guards pipe and newline behavior.

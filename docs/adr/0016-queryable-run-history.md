# 0016: Queryable run history

## Problem and current behavior

Runs are independent directories. Users must know a directory before reporting or comparing it.
There is no searchable inventory of failed runs or scores for a task.

## Alternatives and decision

Scanning every query is simple but expensive. Making a database authoritative would couple grading
to another failure mode. Use a disposable SQLite index explicitly rebuilt from run artifacts.
A transaction replaces the inventory, so readers see an entire previous or next snapshot.

## External behavior and compatibility

`runs refresh`, `runs list`, and `runs show` index, filter, and inspect runs. Invalid directories
produce coded diagnostics without hiding valid records. Only non-linked direct children are
scanned with bounded JSON reads. The index stores IDs and allowlisted summaries, not output or
source paths. Legacy runs retain unknown timestamps. Show checks the current result digest.

## Acceptance

Cover old artifacts, deterministic ordering, corruption and links, query ranges, transaction
rollback, index versions, stale entries, and CLI machine output and exit codes.

# 0021: Bounded parallel batch evaluation

## Problem and current behavior

Batch jobs run sequentially. Curated evaluation sets cannot use independent execution capacity;
unbounded future submission would instead multiply memory use and complicate process cleanup.

## Alternatives and decision

Process pools duplicate orchestration and complicate shared cancellation on Windows. Use a bounded
thread pool around the existing per-job grader, whose child processes already own their lifecycle.
Keep one worker by default; explicit parallelism is limited to 32 workers. Submit at most one
group per worker. Identical resolved task/submission pairs execute serially in lexical job order,
while independent groups may finish in any order. Sort persisted results by job ID.

## External behavior and compatibility

`batch run --workers N` and `run_batch(max_workers=N)` reuse validation, pins, cache, and reports.
An optional cancellation token prevents queued launches and reaches active graders and cache-lock
waiters without removing another worker's lock. Interrupted
scheduling signals cancellation before waiting for workers. CLI interruption maps to code 20.
A `schedule.json` sidecar records policy without changing batch schema 1. Older results still replay.
Concurrency does not make local execution a sandbox, and timing/contention remain measurements.

## Acceptance

Use synchronization rather than speed assertions to test worker bounds, group ordering, failures,
and interruption. Cover duplicate-pair cache ownership, content-alias contention, pre-cancellation,
real concurrent child termination, CLI workers, replay sorting, and existing single-worker behavior.

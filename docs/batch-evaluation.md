# Batch evaluation

## Bounded parallel evaluation

`repogym batch run manifest.yaml --workers 4` opts into up to four independent grading groups.
The default remains one worker and preserves global lexical job execution order. Parallel workers
serialize identical resolved task/submission pairs in lexical order, so the first job for a pair
owns its cache miss. Independent content aliases still share the atomic cache; which alias wins
the miss may vary, but each hit records its real source run. Reports always sort jobs by ID.

The queue holds at most one group per worker; supported worker counts are 1–32. Each grader owns
its workspace, output and child process lifecycle. Individual validation/execution failures remain
isolated. `schedule.json` records schema 1, requested workers, group count, serial-pair policy,
result order, and cancellation state without changing the replayable `batch.json` schema.

Python callers may pass `max_workers` and an optional `CancellationToken` to `run_batch`. A token
set before a job starts prevents grading; active jobs use executor cancellation and do not launch
follow-up commands. Cache-lock waiters also observe the token, wake immediately, and preserve
another worker's lock. Cancellation before acquiring a cache lock returns an execution failure
without claiming a completed run. Ctrl+C signals cancellation before the pool waits for cleanup and exits with
code 20. Interrupted batches may leave completed individual runs, but do not publish a complete
batch result. Incremental batch checkpoint/resume remains future work.

Parallel execution changes contention and measured durations, not isolation guarantees. Use
trusted local code and choose workers appropriate for CPU/memory capacity. Reported job durations
are individual test-command measurements, not overall parallel wall time. Older batch results
without `schedule.json` still replay.

Batch evaluation runs several independent task/submission pairs through the ordinary grading,
cache, evidence, and artifact pipeline. A failure in one job is recorded and later jobs continue.

## Manifest format

Batch manifests use YAML schema version 1:

```yaml
schema_version: 1
jobs:
  - id: cache-ttl-fixed
    task: ../tasks/python-cache-ttl
    submission: submissions/cache-ttl-fixed
  - id: config-merge-fixed
    task: ../tasks/python-config-merge
    submission: submissions/config-merge-fixed
```

Job IDs use lowercase letters, digits, and single hyphens and must be unique. Task and submission
paths are resolved relative to the manifest file, so the same manifest works from any current
working directory. Absolute paths are accepted for local automation but are never persisted.
Duplicate task/submission pairs are valid; they receive distinct run IDs and later jobs may hit
the normal content-addressed cache.

RepoGym sorts jobs by ID before grouping and persistence. YAML order therefore does not change
result ordering or which job in an identical resolved pair first populates the cache. One worker
preserves global lexical execution order; `--workers` enables the bounded policy described above.

## Running and replaying

Run the bundled two-task example:

```bash
repogym batch run examples/batch.yaml
```

Each invocation creates ordinary per-job runs under `.repogym/runs` and one batch directory under
`.repogym/batches`. The batch directory contains an atomically written `batch.json` with sorted
job outcomes and sanitized `GradeResult` snapshots. Use `--no-cache`, `--cache-dir`, `--runs-dir`,
or `--batches-dir` to change the default storage behavior.

Re-render an existing batch without running task code:

```bash
repogym batch report .repogym/batches/<batch-id> --format json
repogym batch report .repogym/batches/<batch-id> --format junit --output batch.xml
repogym batch report .repogym/batches/<batch-id> --format sarif --output batch.sarif
```

Both `batch run` and `batch report` support terminal, JSON, JUnit, and SARIF. JSON preserves the
versioned batch contract. JUnit emits one testcase per job and records score and underlying test
counts as properties. SARIF combines scope violations and a `repogym/batch-outcome` result for
each non-successful job.

## Outcomes and exit codes

Every job has one outcome: success, score below 100, execution failure, invalid task/input,
environment error, or internal error. All jobs are attempted even after a failure. The command
returns the most severe observed code using this fixed order:

1. `70` internal error
2. `40` environment or artifact error
3. `10` invalid task or input
4. `20` execution failure
5. `30` completed score below 100
6. `0` success

This is a severity order, not numeric sorting. Reports are emitted or written before the nonzero
aggregate code is returned, allowing CI to retain diagnostics while still failing the step.

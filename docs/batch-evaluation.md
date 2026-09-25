# Batch evaluation

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

RepoGym sorts jobs by ID before execution and persistence. YAML order therefore does not change
result ordering or which duplicate job populates the cache. Execution is intentionally sequential
in schema version 1; concurrency and resource scheduling require a separate policy.

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

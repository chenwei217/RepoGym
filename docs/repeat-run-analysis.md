# Repeated-run analysis

Use independent re-executions to investigate test variation or timing changes:

```bash
repogym grade tasks/python-cache-ttl --submission examples/submissions/cache-ttl-fixed --no-cache
repogym grade tasks/python-cache-ttl --submission examples/submissions/cache-ttl-fixed --no-cache
repogym analyze .repogym/runs/RUN_A .repogym/runs/RUN_B --format json
repogym analyze .repogym/runs/RUN_A .repogym/runs/RUN_B --format html --output analysis.html
```

Each cohort has exactly equal task IDs, complete task fingerprints, candidate fingerprints, and
persisted runtime fingerprints. New grades identify the prepared starter-plus-submission file
manifest before test injection. The versioned canonical SHA-256 contains normalized relative file
names and content hashes, not absolute paths. Result and metadata store the digest; unified evidence
contains a `candidate_manifest` record. Source code is not copied into a run archive. Older runs
remain readable, but cannot be silently assumed to have the current candidate or environment.

JSON schema 1 lists sorted cohorts and explicit exclusions. Statistics include score distribution,
perfect-score rate, median and nearest-rank p95 duration, and stable/variable/insufficient per-test
observations. Skipped and missing tests are reported separately from failures. A test needs two
non-skipped outcomes before classification. Different observed non-skipped statuses indicate
variation; this is not proof of random flakiness or a statistical confidence claim.

Cache replays are excluded by default. `--include-cached` includes replayed outcomes, but timing
summaries always exclude cache hits and incomplete runs. Timeouts are censored observations, not
ordinary timing samples. Duplicate IDs with identical bytes count once; conflicting records with
the same ID are excluded. Groups with one run or missing case evidence carry explicit warnings.

Analysis reads bounded `result.json` files, never captured output or current environment values.
It accepts at most 200 inputs and 64 MiB combined result bytes. HTML is self-contained and escaped.
Missing/corrupt input still produces exclusions and exits 40. No eligible cohort or exceeded input
limits exit 10. Other completed analyses exit 0 in every format; variation is a finding, not an
execution failure. An explicit `--output` writes the chosen report file.

Known identities do not capture time, external services, scheduling contention, or undeclared
inputs. Use a controlled execution backend and repeated independent samples before drawing
performance conclusions. Cache keys include a candidate-identity capability marker, so older
entries without the new evidence are not mistaken for fresh identity-aware runs.

# Run comparison

`repogym compare RUN_A RUN_B` loads existing artifacts and never executes candidate or task code.
It reports B minus A for total score, each dimension, passed/failed/total tests, and duration. It
also compares status, timeout state, and added or removed violations. If both artifacts contain
structured pytest evidence, comparison lists newly failing cases, failures restored to passing,
and shared cases whose duration changed by at least 0.1 seconds and 50 percent. Case lists are
sorted by stable ID. Legacy, timeout, cancelled, non-pytest, or malformed-output runs carry an
explicit reason instead of pretending a case-level comparison is complete.

```bash
repogym compare .repogym/runs/<a> .repogym/runs/<b>
repogym compare .repogym/runs/<a> .repogym/runs/<b> --format json
repogym compare .repogym/runs/<a> .repogym/runs/<b> --format json --output comparison.json
```

Both runs must have the same `task_id`. Matching fingerprints prove the same task inputs were
used. A fingerprint mismatch is a warning, not an error, so maintainers can inspect historical
cross-version changes deliberately. Older results without fingerprints remain readable and are
marked as unverifiable. Output files contain run data and redacted placeholders, never source run
directory paths.

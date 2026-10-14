# Run history

The run directories remain the source of truth. Refresh the disposable SQLite inventory after
grading or importing runs; it does not execute tests or alter existing artifacts.

```bash
repogym runs refresh --runs-dir .repogym/runs
repogym runs list --task python-cache-ttl --max-score 99 --format json
repogym runs list --status timed_out --limit 20 --offset 0
repogym runs list --since 2026-01-01T00:00:00+00:00
repogym runs show RUN_ID
```

Refresh emits versioned JSON with valid summaries and coded diagnostics. Corrupt or unsafe entries
are skipped and cause exit code 40, while valid entries remain searchable. List sorts by UTC
creation time descending, then ID ascending; legacy unknown timestamps sort last and do not match
`--since`. Scores are inclusive. Invalid query ranges return code 10.

`runs show` verifies that the source result still matches its indexed SHA-256; refresh after any
artifact mutation. The index contains no captured output or source paths. It may be rebuilt by
removing only `.repogym/runs/.history.sqlite3`, never the surrounding runs directory. Unknown
future schema versions are rejected. SQLite transactions retain the previous inventory on a
failed update and serialize concurrent refreshes. Artifacts are assumed locally trusted while
being inspected; the index is not an authenticity or hostile-filesystem boundary.

# Pinned task collections

A catalog is a versioned, portable JSON inventory of task IDs, versions, sanitized metadata, and
complete task fingerprints. It records no absolute task root. Discovery validates all direct task
definitions without executing candidate or task code; invalid definitions are never silently skipped.

```bash
repogym catalog create catalog.json --tasks-dir tasks --language python
repogym catalog list catalog.json --query cache --format json
repogym catalog verify catalog.json --tasks-dir tasks
repogym catalog batch catalog.json batch.json --tasks-dir tasks --submissions-dir candidates
repogym batch run batch.json --no-cache
```

`catalog create` also supports `--difficulty easy|medium|hard` and case-insensitive `--query` over
ID/title. `catalog list` searches saved metadata offline. `catalog verify` returns sorted coded
diagnostics for missing, unsafe, invalid, changed, or inconsistent entries. Additional unselected
tasks are allowed, so a filtered catalog remains useful after the task directory grows.

Batch planning expects `candidates/<task-id>/` for every pinned task, verifies the catalog again,
and emits relative forward-slash paths and `task_fingerprint` fields. JSON is also valid YAML for
the existing batch loader. The manifest and inputs must share a drive on Windows. Existing batch
manifests without fingerprints continue working; pinned jobs compare the complete task fingerprint
before calling the grader and return invalid-task code 10 on drift. Task files must remain stable
during validation/execution under the existing local trust model.

Creation and batch export refuse existing files and publish by atomic hard link. Errors use code
10; `catalog verify` still emits machine-readable issues on drift. Catalog hashes bind content,
not authorship: review task code and execution backend policy before running someone else's tasks.

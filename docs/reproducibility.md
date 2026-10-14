# Reproducibility

## Structured run evidence

New grade runs persist `evidence.json` with schema version 2. Command, aggregate and per-test,
environment, and artifact records share one contract and deterministic semantic ordering.
Artifact records contain the SHA-256 and UTF-8 byte length of the sanitized persisted content, so
they can be checked without revealing the original workspace path. Pytest case IDs use
`classname::name`, are sorted, and receive deterministic suffixes for duplicate identities.
Observation time and test duration are measurements, not identity keys. Schema-1 and older runs
are upgraded in memory without rewriting their files; missing case data is marked `legacy_run`.

## Current guarantees

Task catalogs curate a fixed input set. Generated batch jobs carry optional expected task
fingerprints and reject drift before grading. See [Pinned task collections](task-catalogs.md).

RepoGym fingerprints the complete task input surface, validates the bundled reference solution,
and stores the fingerprint alongside structured execution evidence. A generic `python` or
`python.exe` test command is resolved to the interpreter running RepoGym, which prevents an
ambient `PATH` entry from changing the evaluator runtime. Reports redact local paths before they
are persisted or rendered.

## Runtime environment identity

Environment schema version 1 is a fixed, non-sensitive compatibility surface: Python
implementation/version, OS family/release, architecture, RepoGym version, direct runtime
dependency versions, and executor identity. Canonical sorted JSON produces the SHA-256 environment
fingerprint. Repeated collection with the same inputs is stable, while Python, platform,
dependency, tool, or executor changes are readable field-level differences in `compare`.

The collector never reads environment variable values, executable or home paths, usernames,
hostnames, process IDs, or arbitrary installed distributions. New grades store the snapshot in
`result.json`, `metadata.json`, and `evidence.json`. Old artifacts use `legacy_run`; loaders
must not describe a historical run using the current reader's environment.

Package format version 1 makes the same input surface portable. Its sorted manifest records the
task ID and version, task fingerprint, exporter environment summary, and each file's normalized
path, byte length, and SHA-256 digest. ZIP timestamps and permissions are fixed, so repeated
exports in the same environment are byte-for-byte stable. Import recomputes every digest and the
task fingerprint before publishing the task. See [Task bundles](task-bundles.md).

`task_fingerprint()` computes a lowercase SHA-256 digest from the complete task input surface:

- `task.yaml`;
- `prompt.md` and the configured description file;
- every regular file below `starter/`;
- every regular file below `tests/public/` and `tests/private/`;
- `reference/solution.patch`.

Each entry contributes its normalized `/`-separated relative path and exact bytes, both prefixed
with their lengths. Entries are sorted by normalized path. Absolute paths, mtimes, directory
enumeration order, caches, and generated run artifacts do not participate. Missing required
inputs and symbolic links are errors rather than silently producing a partial identity.

The full digest appears in `verify` and `doctor` output and in both `metadata.json` and
`result.json` for grading runs. A comparison with unequal digests remains readable but carries a
prominent warning; a comparison with different task IDs is rejected.

Incremental execution adds a broader cache key around the task fingerprint. It also includes the
candidate file manifest, resolved command, executor backend and output limits, Python version and
implementation, OS and machine identity, and RepoGym version. The canonical JSON input is hashed
with SHA-256; only the digest is persisted in the cache manifest. A hit replays sanitized evidence
into a new run directory and records the original source run ID rather than claiming re-execution.

Batch manifest order is not an execution input. RepoGym sorts unique job IDs before grading and
persists them in that order; duplicate task/submission pairs are allowed, with the first sorted job
populating the cache and later matches replaying it under distinct run IDs. `batch report` consumes
only the saved `batch.json`, so rendering never changes task state or reruns a candidate.

# Reproducibility

## Structured run evidence

New grade runs persist `evidence.json` with schema version 1. Command, test, environment, and
artifact records share one contract and deterministic semantic ordering. Artifact records contain
the SHA-256 and UTF-8 byte length of the sanitized persisted content, so they can be checked
without revealing the original workspace path. Observation time is informative run metadata and
is not used as an identity or comparison key. Older runs are upgraded in memory when evidence is
loaded; their files are not rewritten.

## Current guarantees

RepoGym fingerprints the complete task input surface, validates the bundled reference solution,
and stores the fingerprint alongside structured execution evidence. A generic `python` or
`python.exe` test command is resolved to the interpreter running RepoGym, which prevents an
ambient `PATH` entry from changing the evaluator runtime. Reports redact local paths before they
are persisted or rendered.

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

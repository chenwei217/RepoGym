# Reproducibility

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

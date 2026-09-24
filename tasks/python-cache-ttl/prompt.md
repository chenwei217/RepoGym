# Correct TTL expiration in the in-memory cache

The small cache in `cachelib/cache.py` does not consistently honor its documented TTL
contract.

Update the implementation so that:

- values are available before their deadline;
- expired values behave exactly like missing values and are removed lazily;
- a TTL of zero means “do not cache”;
- overwriting a key replaces both its value and expiration deadline;
- existing deletion and missing-key behavior remain intact.

Keep the public API unchanged. You may edit files under `cachelib/`; do not change project
configuration or RepoGym internals.


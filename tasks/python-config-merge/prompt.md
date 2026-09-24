# Repair immutable configuration merging

`configmerge.merge_config` combines a base configuration with an override, but it violates
the API contract for nested values and can mutate data owned by callers.

Implement these semantics:

- mappings merge recursively;
- scalar values and lists in the override replace base values;
- an override value of `None` deletes that key;
- neither input, nor any nested object reachable from either input, may be mutated or shared
  with the returned configuration.

The function accepts ordinary dictionaries containing JSON-like values. Keep its public API
unchanged and limit changes to the permitted source tree.


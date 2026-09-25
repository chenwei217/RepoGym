# Task authoring

## Schema and task versions

New `task.yaml` files start with `schema_version: 1`. This integer identifies the structure of
the YAML document. The separate `version` field identifies the task content and should change
when prompts, inputs, tests, or scoring expectations change.

For compatibility, an omitted `schema_version` or an explicit value of `0` is migrated in
memory to version 1. Loading never rewrites the source file. Unknown versions and non-integer
values fail before field validation with a stable version error, preventing a newer schema from
being silently interpreted using older rules.

## Start with an observable contract

Describe inputs, outputs, error behavior, and boundary semantics before writing tests. Avoid
phrases such as “works correctly” unless the following text makes correctness measurable. A
candidate should not need to infer requirements from the reference patch.

Public tests communicate representative behavior and provide fast feedback. Private tests
protect against narrow solutions by checking additional boundaries and regressions. Private
tests must enforce the same contract as the prompt; secrecy is not permission to add new
requirements.

## Acceptance criteria

Translate each requirement into at least one behavioral assertion. Prefer calls through the
public API over assertions about helper names, control flow, or internal storage. Include normal
operation, exact boundaries, repeated operations, missing values, and mutation/aliasing where
relevant. Avoid clocks, networks, random data, and host-specific paths unless they are injected
or fixed.

Set `expected.failing_tests_before` to the exact number of failures in the starter and
`expected.passing_tests_after` to the total after applying the reference patch. A useful task
fails for the intended reason before the fix, not because it cannot import or install.

## Authoring loop

1. Create `task.yaml`, `prompt.md`, `starter/`, both test directories, and
   `reference/solution.patch`.
2. Run `repogym validate tasks/<id>` to catch schema, path, and layout errors.
3. Run `repogym doctor tasks/<id>` to check the command, dependencies, discovery, temporary
   storage, and deterministic fingerprint without executing candidate code.
4. Run `repogym verify tasks/<id>` to execute the starter, apply the patch, and execute again.
5. Grade both a known-correct and a deliberately incomplete submission.
6. Compare those runs and confirm every deduction is explainable from the published rules.

Use regression tests for behavior that should remain stable and edge tests for equality
boundaries, empty inputs, replacement, deletion, and nested mutable data. Do not assert a
specific algorithm when several implementations satisfy the contract.

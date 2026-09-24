# Scoring

Every dimension has the maximum weight declared in `task.yaml`; validation requires the four
weights to sum to 100. Each dimension and the final sum are rounded to two decimal places and
the total is clamped to `[0, 100]`.

## Correctness

`correctness = weight × passed_all_tests / expected.passing_tests_after`. Using the verified
expected total prevents collection errors, early process exits, or timeouts from shrinking the
denominator. An execution with no parseable passing tests earns zero for this dimension.

## Regression safety

RepoGym executes the configured test command a second time with `tests/public` appended.
`regression_safety = weight × passed_public_tests / total_public_tests`. This makes the public
suite the explicit regression contract.

## Code quality

Only changed Python files are checked. Half of the dimension is awarded when all of them parse
with Python's AST parser; half is awarded when `ruff check --quiet` succeeds. If no Python file
changed, the full dimension is awarded because there is no candidate Python delta to inspect.
Missing or timed-out Ruff execution earns no Ruff half.

## Scope control

If any changed path matches `forbidden_paths`, the score is zero. Otherwise:

`scope_control = weight × (1 - outside_allowed_count / changed_count)`.

No changes receive full scope credit. Glob patterns ending in `/**` match every descendant;
other patterns use case-sensitive shell-style matching. Each forbidden or outside path is also
recorded as a violation.

Timeouts and abnormal test starts still produce a run result. Any test counts observed before a
timeout are parsed; absent counts result in zero correctness and regression credit.

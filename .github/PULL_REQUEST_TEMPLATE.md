## Purpose

Describe the user-visible problem and why this change belongs in RepoGym.

## Observable behavior

Describe the acceptance criteria and compatibility impact.

## Verification

- [ ] Production behavior and error paths have tests.
- [ ] `ruff check .` passes.
- [ ] `ruff format --check .` passes.
- [ ] `mypy src/repogym` passes.
- [ ] `pytest --cov=repogym --cov-report=term-missing` passes with at least 85% coverage.
- [ ] Documentation and CHANGELOG entries match the implementation.
- [ ] No credentials, private task data, local absolute paths, caches, or build products are included.

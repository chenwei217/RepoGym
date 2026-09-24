# Testing and quality gates

Run the full local gate before every change:

```bash
ruff check .
ruff format --check .
mypy src/repogym
pytest
coverage run -m pytest
coverage report --fail-under=85
```

The suite is organized by responsibility: task loading and validation, command parsing and test
execution, reproducibility, submission and patch security, diagnostics, scoring, comparisons,
and end-to-end CLI workflows. The CI matrix runs the same checks on Ubuntu and Windows with
Python 3.11 and 3.12, then verifies both bundled tasks and smoke-tests doctor and comparison.

Some link-related tests are skipped on Windows runners without the privilege required to create a
symbolic link. A skip is reported by pytest and must not be used to avoid testing portable
behavior. Tests use only task fixtures and local subprocesses; after dependencies are installed,
the core suite and bundled-task verification require no network connection.

New production behavior needs a normal-path test, an error-path test, and an integration test
where it crosses a CLI, filesystem, subprocess, or persisted-artifact boundary.

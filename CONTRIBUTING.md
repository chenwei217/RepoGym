# Contributing to RepoGym

Thank you for improving RepoGym. Keep changes focused, add tests for behavioral changes, and
do not weaken task reproducibility or the documented trust boundary.

## Development setup

```bash
python -m pip install -e ".[dev]"
ruff check .
ruff format --check .
mypy src/repogym
pytest --cov=repogym --cov-report=term-missing
```

New tasks should be original, have meaningful public and private tests, declare exact expected
counts, and pass `repogym validate` and `repogym verify`. Prompts should specify observable
behavior without revealing the reference implementation. Update the changelog for user-facing
changes and use conventional, imperative commit subjects where practical.


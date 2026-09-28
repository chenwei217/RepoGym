# Release process

RepoGym releases are immutable annotated Git tags backed by GitHub Release artifacts. Package
versions use semantic versioning and must agree in `pyproject.toml`, `repogym.__version__`, and the
dated CHANGELOG heading.

## Prepare and verify

1. Move completed CHANGELOG entries from `Unreleased` into a dated version section.
2. Update the project and package versions to the same value.
3. Run the complete quality gate:

   ```bash
   ruff check .
   ruff format --check .
   mypy src/repogym
   pytest --cov=repogym --cov-report=term-missing
   ```

The release contract test builds both distributions, validates their metadata, PEP 561 marker, and
contents, then installs the wheel without network access in a clean temporary virtual environment.
Do not tag a commit until main CI passes.

## Publish

Build the artifacts from the exact release commit, create an annotated `vX.Y.Z` tag, push the tag,
and wait for tag CI. Create the GitHub Release from that existing tag and attach the verified wheel
and source archive. PyPI publication is a separate, explicitly authorized operation.

Never move or replace a published tag. Corrections require a new patch release.

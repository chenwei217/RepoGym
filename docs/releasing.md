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

Create an annotated `vX.Y.Z` tag on the prepared release commit and push the tag. The tag starts the
full CI matrix. After CI succeeds, the Automated Release workflow verifies the exact tag/commit and
version mapping, rebuilds in a clean runner, installs the wheel without an index, writes
`SHA256SUMS`, and creates the GitHub Release with the wheel, source archive, and checksums.

The workflow never overwrites an existing release. Artifact attestations run when repository
visibility and the GitHub plan support them. PyPI publication remains a separate operation until a
Trusted Publisher is configured; do not add a long-lived PyPI token.

Never move or replace a published tag. Corrections require a new patch release.

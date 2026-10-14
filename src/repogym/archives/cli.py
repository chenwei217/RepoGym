"""Run archive CLI using the stable automation outcome contract."""

from pathlib import Path
from typing import Annotated, NoReturn

import typer

from repogym.archives import export_run_archive, import_run_archive, verify_run_archive
from repogym.exceptions import RepoGymError
from repogym.exit_codes import ExitCode

app = typer.Typer(help="Export, verify, and import sanitized execution evidence.")


def _error(exc: Exception) -> NoReturn:
    typer.echo(str(exc), err=True)
    raise typer.Exit(int(ExitCode.TASK_INVALID))


@app.command("export")
def export(
    run: Annotated[Path, typer.Argument()], output: Annotated[Path, typer.Argument()]
) -> None:
    """Export a run to a new deterministic archive."""
    try:
        manifest = export_run_archive(run, output)
    except RepoGymError as exc:
        _error(exc)
    typer.echo(manifest.model_dump_json(indent=2))


@app.command("verify")
def verify(archive: Annotated[Path, typer.Argument()]) -> None:
    """Validate archive safety, hashes, and evidence associations without extraction."""
    try:
        manifest = verify_run_archive(archive)
    except RepoGymError as exc:
        _error(exc)
    typer.echo(manifest.model_dump_json(indent=2))


@app.command("import")
def import_command(
    archive: Annotated[Path, typer.Argument()],
    destination: Annotated[Path, typer.Option("--destination")],
) -> None:
    """Verify and atomically import without executing task code."""
    try:
        target = import_run_archive(archive, destination)
    except RepoGymError as exc:
        _error(exc)
    typer.echo(f"Imported run {target.name}")

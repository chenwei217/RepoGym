"""Local catalog curation CLI."""

import json
from pathlib import Path
from typing import Annotated, Literal, NoReturn

import typer
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from repogym.catalog import discover_catalog, load_catalog, plan_batch, save_catalog, select_tasks
from repogym.catalog.manifest import publish_text, verify_catalog
from repogym.catalog.models import CatalogError, TaskCatalog
from repogym.exit_codes import ExitCode

app = typer.Typer(help="Curate and verify fingerprint-pinned local task collections.")


def _error(exc: Exception) -> NoReturn:
    typer.echo(str(exc), err=True)
    raise typer.Exit(int(ExitCode.TASK_INVALID))


@app.command("create")
def create(
    output: Annotated[Path, typer.Argument()],
    tasks_dir: Annotated[Path, typer.Option()] = Path("tasks"),
    language: Annotated[str | None, typer.Option()] = None,
    difficulty: Annotated[Literal["easy", "medium", "hard"] | None, typer.Option()] = None,
    query: Annotated[str, typer.Option()] = "",
) -> None:
    """Validate tasks and write a new portable catalog; fail on invalid definitions."""
    try:
        tasks = select_tasks(
            discover_catalog(tasks_dir), language=language, difficulty=difficulty, query=query
        )
        if not tasks:
            raise CatalogError("No tasks match the selection")
        catalog = TaskCatalog(tasks=tasks)
        save_catalog(catalog, output)
    except CatalogError as exc:
        _error(exc)
    typer.echo(f"Pinned {len(catalog.tasks)} task(s)")


@app.command("list")
def list_catalog(
    catalog_path: Annotated[Path, typer.Argument()],
    language: Annotated[str | None, typer.Option()] = None,
    difficulty: Annotated[Literal["easy", "medium", "hard"] | None, typer.Option()] = None,
    query: Annotated[str, typer.Option()] = "",
    format_name: Annotated[Literal["terminal", "json"], typer.Option("--format")] = "terminal",
) -> None:
    """Filter a saved catalog offline without accessing task directories."""
    try:
        tasks = select_tasks(
            load_catalog(catalog_path), language=language, difficulty=difficulty, query=query
        )
    except CatalogError as exc:
        _error(exc)
    if format_name == "json":
        typer.echo(
            json.dumps(
                {"schema_version": 1, "tasks": [task.model_dump(mode="json") for task in tasks]},
                indent=2,
            )
        )
    else:
        table = Table("Task", "Title", "Language", "Difficulty", "Fingerprint")
        for task in tasks:
            table.add_row(
                task.id,
                escape(task.title),
                escape(task.language),
                task.difficulty,
                task.fingerprint[:12],
            )
        Console().print(table)


@app.command("verify")
def verify(
    catalog_path: Annotated[Path, typer.Argument()],
    tasks_dir: Annotated[Path, typer.Option()] = Path("tasks"),
) -> None:
    """Return versioned drift diagnostics; mismatches use exit code 10."""
    try:
        report = verify_catalog(load_catalog(catalog_path), tasks_dir)
    except CatalogError as exc:
        _error(exc)
    typer.echo(report.model_dump_json(indent=2))
    if not report.valid:
        raise typer.Exit(int(ExitCode.TASK_INVALID))


@app.command("batch")
def batch(
    catalog_path: Annotated[Path, typer.Argument()],
    output: Annotated[Path, typer.Argument()],
    submissions_dir: Annotated[Path, typer.Option()],
    tasks_dir: Annotated[Path, typer.Option()] = Path("tasks"),
) -> None:
    """Export a pinned JSON batch manifest (also valid YAML) without grading."""
    try:
        manifest = plan_batch(load_catalog(catalog_path), tasks_dir, submissions_dir, output)
        publish_text(output, manifest.model_dump_json(indent=2) + "\n")
    except CatalogError as exc:
        _error(exc)
    typer.echo(f"Planned {len(manifest.jobs)} pinned job(s)")

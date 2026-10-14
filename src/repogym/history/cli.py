"""CLI for rebuilding and searching run history."""

import json
from datetime import datetime
from pathlib import Path
from typing import Annotated, Literal, NoReturn

import typer
from rich.console import Console
from rich.table import Table

from repogym.exit_codes import ExitCode
from repogym.history import HistoryError, RunIndex, RunQuery

app = typer.Typer(help="Index and search persisted runs without executing tasks.")


def _error(exc: Exception) -> NoReturn:
    typer.echo(f"Error: {exc}", err=True)
    raise typer.Exit(int(ExitCode.ENVIRONMENT_ERROR))


@app.command("refresh")
def refresh(runs_dir: Annotated[Path, typer.Option()] = Path(".repogym/runs")) -> None:
    """Rebuild history; isolate invalid runs with coded diagnostics."""
    try:
        report = RunIndex(runs_dir).refresh()
    except HistoryError as exc:
        _error(exc)
    typer.echo(report.model_dump_json(indent=2))
    if report.diagnostics:
        raise typer.Exit(int(ExitCode.ENVIRONMENT_ERROR))


@app.command("list")
def list_runs(
    runs_dir: Annotated[Path, typer.Option()] = Path(".repogym/runs"),
    task: Annotated[str | None, typer.Option()] = None,
    status: Annotated[
        Literal["completed", "timed_out", "cancelled", "error"] | None, typer.Option()
    ] = None,
    min_score: Annotated[float, typer.Option(min=0, max=100)] = 0,
    max_score: Annotated[float, typer.Option(min=0, max=100)] = 100,
    since: Annotated[str | None, typer.Option(help="ISO timestamp with timezone.")] = None,
    limit: Annotated[int, typer.Option(min=1, max=1000)] = 50,
    offset: Annotated[int, typer.Option(min=0)] = 0,
    format_name: Annotated[Literal["terminal", "json"], typer.Option("--format")] = "terminal",
) -> None:
    """Search the last refreshed inventory, newest first; unknown times last."""
    try:
        query = RunQuery(
            task_id=task,
            status=status,
            min_score=min_score,
            max_score=max_score,
            since=datetime.fromisoformat(since) if since is not None else None,
            limit=limit,
            offset=offset,
        )
        runs = RunIndex(runs_dir).query(query)
    except ValueError:
        typer.echo("Invalid query: score range or timezone", err=True)
        raise typer.Exit(int(ExitCode.TASK_INVALID)) from None
    except HistoryError as exc:
        _error(exc)
    if format_name == "json":
        typer.echo(
            json.dumps(
                {"schema_version": 1, "runs": [r.model_dump(mode="json") for r in runs]},
                indent=2,
                sort_keys=True,
            )
        )
    else:
        table = Table("Run", "Task", "Status", "Score", "Created (UTC)")
        for run in runs:
            table.add_row(
                run.run_id,
                run.task_id,
                run.status,
                str(run.score),
                str(run.created_at or "unknown"),
            )
        Console().print(table)


@app.command("show")
def show(
    run_id: Annotated[str, typer.Argument()],
    runs_dir: Annotated[Path, typer.Option()] = Path(".repogym/runs"),
) -> None:
    """Inspect only if the source still matches the indexed digest."""
    try:
        result = RunIndex(runs_dir).get(run_id)
    except HistoryError as exc:
        _error(exc)
    typer.echo(result.model_dump_json(indent=2))

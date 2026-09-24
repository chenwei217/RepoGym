"""RepoGym command-line interface."""

from __future__ import annotations

import traceback
from pathlib import Path
from typing import Annotated, Literal

import typer
from rich.console import Console
from rich.table import Table

from repogym import __version__
from repogym.doctor import diagnose_task
from repogym.exceptions import RepoGymError
from repogym.grader import grade_submission
from repogym.loader import load_task
from repogym.reports import generate_report, load_run, render_terminal
from repogym.validator import validate_task
from repogym.verifier import verify_task

app = typer.Typer(help="Build and grade reproducible AI coding tasks.", no_args_is_help=True)
console = Console()
error_console = Console(stderr=True)
_debug = False


@app.callback()
def main(debug: Annotated[bool, typer.Option("--debug", help="Show tracebacks.")] = False) -> None:
    global _debug
    _debug = debug


def _fail(exc: Exception) -> None:
    if _debug:
        traceback.print_exc()
    else:
        error_console.print(f"[red]Error:[/red] {exc}")
    raise typer.Exit(1)


@app.command("list")
def list_tasks(
    tasks_dir: Annotated[Path, typer.Option(help="Directory containing tasks.")] = Path("tasks"),
) -> None:
    """List discoverable tasks."""
    if not tasks_dir.is_dir():
        _fail(RepoGymError(f"Tasks directory does not exist: {tasks_dir}"))
    table = Table("ID", "Title", "Difficulty", "Language")
    found = 0
    for directory in sorted(path for path in tasks_dir.iterdir() if path.is_dir()):
        try:
            task = load_task(directory)
        except RepoGymError:
            continue
        table.add_row(task.id, task.title, task.difficulty, task.language)
        found += 1
    console.print(table)
    console.print(f"{found} task(s)")


@app.command()
def validate(task: Annotated[Path, typer.Argument(help="Task directory.")]) -> None:
    """Validate a task definition and its files."""
    report = validate_task(task)
    for check in report.checks:
        console.print(f"[green]PASS[/green] {check}")
    if report.errors:
        for error in report.errors:
            error_console.print(f"[red]FAIL[/red] {error}")
        raise typer.Exit(1)
    console.print("\n[bold green]Validation passed.[/bold green]")


@app.command()
def doctor(task: Annotated[Path, typer.Argument(help="Task directory.")]) -> None:
    """Diagnose whether a task can run in the current environment."""
    report = diagnose_task(task)
    styles = {"pass": "green", "warning": "yellow", "fail": "red"}
    labels = {"pass": "PASS", "warning": "WARN", "fail": "FAIL"}
    for check in report.checks:
        console.print(
            f"[{styles[check.status]}]{labels[check.status]}[/] {check.name}: {check.message}"
        )
    if not report.healthy:
        raise typer.Exit(1)


@app.command()
def verify(task: Annotated[Path, typer.Argument(help="Task directory.")]) -> None:
    """Prove that the starter fails and the reference patch passes."""
    try:
        report = verify_task(task)
    except RepoGymError as exc:
        _fail(exc)
    initial_failed = report.initial.stdout + report.initial.stderr
    console.print("[green]PASS[/green] Starter produced the expected failures")
    console.print(f"[green]PASS[/green] Reference patch changed: {', '.join(report.patch_files)}")
    console.print("[green]PASS[/green] Reference solution passed all tests")
    console.print(f"\n[bold green]Verification passed for {report.task_id}.[/bold green]")
    if _debug:
        console.print(initial_failed)


@app.command()
def grade(
    task: Annotated[Path, typer.Argument(help="Task directory.")],
    submission: Annotated[Path, typer.Option("--submission", help="Candidate code directory.")],
) -> None:
    """Grade a candidate submission."""
    try:
        run_dir = grade_submission(task, submission)
        result, _, _ = load_run(run_dir)
    except RepoGymError as exc:
        _fail(exc)
    render_terminal(result, console)
    console.print(f"Run artifacts: [bold]{run_dir}[/bold]")


@app.command()
def report(
    run: Annotated[Path, typer.Argument(help="Run directory.")],
    format_name: Annotated[
        Literal["terminal", "json", "html"], typer.Option("--format", help="Report format.")
    ] = "terminal",
    output: Annotated[Path | None, typer.Option("--output", help="Output file.")] = None,
) -> None:
    """Render an existing grade result."""
    if format_name == "html" and output is None:
        _fail(RepoGymError("--output is required for HTML reports"))
    try:
        rendered = generate_report(run, format_name, output, console)
    except RepoGymError as exc:
        _fail(exc)
    if rendered is not None and output is None:
        console.print(rendered, markup=False)
    elif output is not None:
        console.print(f"Report written to {output}")


@app.command()
def version() -> None:
    """Show the installed RepoGym version."""
    console.print(__version__)


if __name__ == "__main__":
    app()

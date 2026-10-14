"""Read-only repeated-run analysis CLI."""

from pathlib import Path
from typing import Annotated, Literal

import typer

from repogym.analytics import AnalysisError, analyze_runs, render_analysis
from repogym.exit_codes import ExitCode


def analyze(
    runs: Annotated[list[Path], typer.Argument(help="Run directories; at most 200.")],
    include_cached: Annotated[
        bool, typer.Option(help="Include replayed outcomes, never timings.")
    ] = False,
    format_name: Annotated[
        Literal["terminal", "json", "html"], typer.Option("--format")
    ] = "terminal",
    output: Annotated[
        Path | None, typer.Option(help="Write the analysis report to a file.")
    ] = None,
) -> None:
    """Summarize repetitions only within equal task/candidate/environment identities."""
    try:
        report = analyze_runs(runs, include_cached=include_cached)
    except AnalysisError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(int(ExitCode.TASK_INVALID)) from exc
    rendered = render_analysis(report, format_name)
    if output is None:
        typer.echo(rendered)
    else:
        output.write_text(rendered, encoding="utf-8")
        typer.echo("Analysis report written")
    if any(issue.code == "invalid_artifact" for issue in report.excluded):
        raise typer.Exit(int(ExitCode.ENVIRONMENT_ERROR))
    if not report.cohorts:
        raise typer.Exit(int(ExitCode.TASK_INVALID))

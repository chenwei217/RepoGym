"""Terminal, JSON, and self-contained HTML reports."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from jinja2 import Environment, PackageLoader
from rich.console import Console
from rich.table import Table

from repogym.exceptions import ReportError
from repogym.models import GradeResult
from repogym.security import redact_sensitive_text, redact_value


def load_run(run_directory: Path) -> tuple[GradeResult, str, str]:
    try:
        raw: Any = json.loads((run_directory / "result.json").read_text(encoding="utf-8"))
        roots = [run_directory.resolve()]
        result = GradeResult.model_validate(redact_value(raw, roots))
        stdout = redact_sensitive_text(
            (run_directory / "stdout.txt").read_text(encoding="utf-8"), roots
        )
        stderr = redact_sensitive_text(
            (run_directory / "stderr.txt").read_text(encoding="utf-8"), roots
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise ReportError(f"Invalid run directory {run_directory}: {exc}") from exc
    return result, stdout, stderr


def render_terminal(result: GradeResult, console: Console) -> None:
    console.print(f"[bold]{result.task_id}[/bold] - score [bold]{result.score:.2f}/100[/bold]")
    table = Table("Dimension", "Score", "Reason")
    for name, dimension in result.dimensions.items():
        table.add_row(name, f"{dimension.score:.2f}/{dimension.max_score}", dimension.reason)
    console.print(table)
    console.print(
        f"Tests: {result.tests.passed} passed, {result.tests.failed} failed; "
        f"status: {result.status}; duration: {result.duration_seconds:.3f}s"
    )
    if result.violations:
        console.print("[yellow]Violations:[/yellow]")
        for violation in result.violations:
            console.print(f"  - {violation}")


def generate_report(
    run_directory: Path,
    format_name: Literal["terminal", "json", "html"],
    output: Path | None = None,
    console: Console | None = None,
) -> str | None:
    result, stdout, stderr = load_run(run_directory)
    if format_name == "terminal":
        render_terminal(result, console or Console())
        return None
    if format_name == "json":
        rendered = json.dumps(result.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n"
    else:
        environment = Environment(
            loader=PackageLoader("repogym", "templates"),
            autoescape=True,
        )
        rendered = environment.get_template("report.html.j2").render(
            result=result, stdout=stdout, stderr=stderr
        )
    if output is not None:
        output.write_text(rendered, encoding="utf-8")
    return rendered

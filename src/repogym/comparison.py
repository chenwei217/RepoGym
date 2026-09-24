"""Deterministic comparison of persisted grading runs."""

from __future__ import annotations

import json
from io import StringIO
from pathlib import Path
from typing import Literal

from pydantic import BaseModel
from rich.console import Console
from rich.table import Table

from repogym.exceptions import ReportError
from repogym.reports import load_run


class MetricComparison(BaseModel):
    run_a: float
    run_b: float
    delta: float


class TestComparison(BaseModel):
    passed: MetricComparison
    failed: MetricComparison
    total: MetricComparison


class StateComparison(BaseModel):
    run_a: str
    run_b: str
    changed: bool


class TimeoutComparison(BaseModel):
    run_a: bool
    run_b: bool
    changed: bool


class RunComparison(BaseModel):
    run_a: str
    run_b: str
    task_id: str
    fingerprint_a: str | None
    fingerprint_b: str | None
    warnings: list[str]
    score: MetricComparison
    dimensions: dict[str, MetricComparison]
    tests: TestComparison
    duration_seconds: MetricComparison
    status: StateComparison
    timed_out: TimeoutComparison
    violations_added: list[str]
    violations_removed: list[str]


def _metric(value_a: float, value_b: float, digits: int = 2) -> MetricComparison:
    return MetricComparison(
        run_a=round(value_a, digits),
        run_b=round(value_b, digits),
        delta=round(value_b - value_a, digits),
    )


def compare_runs(run_a: Path, run_b: Path) -> RunComparison:
    """Compare two immutable result files without depending on wall-clock state."""
    result_a, _, _ = load_run(run_a)
    result_b, _, _ = load_run(run_b)
    if result_a.task_id != result_b.task_id:
        raise ReportError(
            "Cannot compare runs for different tasks: "
            f"{result_a.task_id!r} and {result_b.task_id!r}"
        )
    warnings: list[str] = []
    if result_a.task_fingerprint and result_b.task_fingerprint:
        if result_a.task_fingerprint != result_b.task_fingerprint:
            warnings.append(
                "Task fingerprints differ; scores may represent different task versions."
            )
    else:
        warnings.append("Task fingerprint unavailable for one or both runs.")
    names = sorted(result_a.dimensions.keys() | result_b.dimensions.keys())
    dimensions = {
        name: _metric(
            result_a.dimensions[name].score if name in result_a.dimensions else 0.0,
            result_b.dimensions[name].score if name in result_b.dimensions else 0.0,
        )
        for name in names
    }
    violations_a = set(result_a.violations)
    violations_b = set(result_b.violations)
    timed_out_a = (
        result_a.execution.timed_out
        if result_a.execution is not None
        else result_a.status == "timed_out"
    )
    timed_out_b = (
        result_b.execution.timed_out
        if result_b.execution is not None
        else result_b.status == "timed_out"
    )
    return RunComparison(
        run_a=result_a.run_id,
        run_b=result_b.run_id,
        task_id=result_a.task_id,
        fingerprint_a=result_a.task_fingerprint,
        fingerprint_b=result_b.task_fingerprint,
        warnings=warnings,
        score=_metric(result_a.score, result_b.score),
        dimensions=dimensions,
        tests=TestComparison(
            passed=_metric(result_a.tests.passed, result_b.tests.passed, 0),
            failed=_metric(result_a.tests.failed, result_b.tests.failed, 0),
            total=_metric(result_a.tests.total, result_b.tests.total, 0),
        ),
        duration_seconds=_metric(result_a.duration_seconds, result_b.duration_seconds, 3),
        status=StateComparison(
            run_a=result_a.status,
            run_b=result_b.status,
            changed=result_a.status != result_b.status,
        ),
        timed_out=TimeoutComparison(
            run_a=timed_out_a,
            run_b=timed_out_b,
            changed=timed_out_a != timed_out_b,
        ),
        violations_added=sorted(violations_b - violations_a),
        violations_removed=sorted(violations_a - violations_b),
    )


def render_comparison_terminal(comparison: RunComparison, console: Console) -> None:
    for warning in comparison.warnings:
        console.print(f"[bold yellow]WARNING: {warning}[/bold yellow]")
    console.print(f"[bold]{comparison.task_id}[/bold] ({comparison.run_a}) -> ({comparison.run_b})")
    table = Table("Metric", "Run A", "Run B", "Delta")
    table.add_row(
        "total score",
        f"{comparison.score.run_a:.2f}",
        f"{comparison.score.run_b:.2f}",
        f"{comparison.score.delta:+.2f}",
    )
    for name, metric in comparison.dimensions.items():
        table.add_row(
            name,
            f"{metric.run_a:.2f}",
            f"{metric.run_b:.2f}",
            f"{metric.delta:+.2f}",
        )
    table.add_row(
        "tests passed",
        f"{comparison.tests.passed.run_a:.0f}",
        f"{comparison.tests.passed.run_b:.0f}",
        f"{comparison.tests.passed.delta:+.0f}",
    )
    table.add_row(
        "tests failed",
        f"{comparison.tests.failed.run_a:.0f}",
        f"{comparison.tests.failed.run_b:.0f}",
        f"{comparison.tests.failed.delta:+.0f}",
    )
    table.add_row(
        "tests total",
        f"{comparison.tests.total.run_a:.0f}",
        f"{comparison.tests.total.run_b:.0f}",
        f"{comparison.tests.total.delta:+.0f}",
    )
    table.add_row(
        "duration seconds",
        f"{comparison.duration_seconds.run_a:.3f}",
        f"{comparison.duration_seconds.run_b:.3f}",
        f"{comparison.duration_seconds.delta:+.3f}",
    )
    console.print(table)
    console.print(
        f"Status: {comparison.status.run_a} -> {comparison.status.run_b}; "
        f"timed out: {comparison.timed_out.run_a} -> {comparison.timed_out.run_b}"
    )
    console.print(
        f"Violations added: {len(comparison.violations_added)}; "
        f"removed: {len(comparison.violations_removed)}"
    )
    for violation in comparison.violations_added:
        console.print(f"  [red]+ {violation}[/red]")
    for violation in comparison.violations_removed:
        console.print(f"  [green]- {violation}[/green]")


def generate_comparison(
    run_a: Path,
    run_b: Path,
    format_name: Literal["terminal", "json"] = "terminal",
    console: Console | None = None,
    output: Path | None = None,
) -> str | None:
    comparison = compare_runs(run_a, run_b)
    if format_name == "terminal":
        if output is None:
            render_comparison_terminal(comparison, console or Console())
            return None
        buffer = StringIO()
        recording = Console(file=buffer, width=120, color_system=None)
        render_comparison_terminal(comparison, recording)
        rendered = buffer.getvalue()
    else:
        rendered = (
            json.dumps(comparison.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n"
        )
    if output is not None:
        output.write_text(rendered, encoding="utf-8")
    return rendered

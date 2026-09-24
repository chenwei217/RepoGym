"""Deterministic comparison of persisted grading runs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel
from rich.console import Console
from rich.table import Table

from repogym.reports import load_run


class MetricComparison(BaseModel):
    run_a: float
    run_b: float
    delta: float


class RunComparison(BaseModel):
    run_a: str
    run_b: str
    task_a: str
    task_b: str
    score: MetricComparison
    dimensions: dict[str, MetricComparison]
    tests_passed: MetricComparison
    duration_seconds: MetricComparison
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
    return RunComparison(
        run_a=result_a.run_id,
        run_b=result_b.run_id,
        task_a=result_a.task_id,
        task_b=result_b.task_id,
        score=_metric(result_a.score, result_b.score),
        dimensions=dimensions,
        tests_passed=_metric(result_a.tests.passed, result_b.tests.passed, 0),
        duration_seconds=_metric(result_a.duration_seconds, result_b.duration_seconds, 3),
        violations_added=sorted(violations_b - violations_a),
        violations_removed=sorted(violations_a - violations_b),
    )


def render_comparison_terminal(comparison: RunComparison, console: Console) -> None:
    console.print(
        f"[bold]{comparison.task_a}[/bold] ({comparison.run_a}) -> "
        f"[bold]{comparison.task_b}[/bold] ({comparison.run_b})"
    )
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
        f"{comparison.tests_passed.run_a:.0f}",
        f"{comparison.tests_passed.run_b:.0f}",
        f"{comparison.tests_passed.delta:+.0f}",
    )
    table.add_row(
        "duration seconds",
        f"{comparison.duration_seconds.run_a:.3f}",
        f"{comparison.duration_seconds.run_b:.3f}",
        f"{comparison.duration_seconds.delta:+.3f}",
    )
    console.print(table)
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
) -> str | None:
    comparison = compare_runs(run_a, run_b)
    if format_name == "terminal":
        render_comparison_terminal(comparison, console or Console())
        return None
    return json.dumps(comparison.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n"

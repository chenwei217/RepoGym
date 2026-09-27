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
from repogym.models import GradeResult
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


class TestCaseStateChange(BaseModel):
    id: str
    run_a: str | None
    run_b: str | None


class TestCaseDurationChange(BaseModel):
    id: str
    run_a_seconds: float
    run_b_seconds: float
    delta_seconds: float
    percent_change: float


class TestCaseComparison(BaseModel):
    availability_a: str
    availability_b: str
    warning: str | None = None
    newly_failing: list[TestCaseStateChange]
    restored_to_passing: list[TestCaseStateChange]
    duration_changes: list[TestCaseDurationChange]


class EnvironmentDifference(BaseModel):
    field: str
    run_a: str | None
    run_b: str | None


class EnvironmentComparison(BaseModel):
    availability_a: str
    availability_b: str
    matches: bool | None
    fingerprint_a: str | None
    fingerprint_b: str | None
    warning: str | None = None
    differences: list[EnvironmentDifference]


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
    test_cases: TestCaseComparison
    environment: EnvironmentComparison


def _metric(value_a: float, value_b: float, digits: int = 2) -> MetricComparison:
    return MetricComparison(
        run_a=round(value_a, digits),
        run_b=round(value_b, digits),
        delta=round(value_b - value_a, digits),
    )


def _compare_test_cases(result_a: GradeResult, result_b: GradeResult) -> TestCaseComparison:
    evidence_a = result_a.test_evidence
    evidence_b = result_b.test_evidence
    if evidence_a.availability != "available" or evidence_b.availability != "available":
        reasons = f"A={evidence_a.reason}, B={evidence_b.reason}"
        return TestCaseComparison(
            availability_a=evidence_a.availability,
            availability_b=evidence_b.availability,
            warning=f"Per-test comparison unavailable ({reasons}).",
            newly_failing=[],
            restored_to_passing=[],
            duration_changes=[],
        )
    cases_a = {case.id: case for case in evidence_a.cases}
    cases_b = {case.id: case for case in evidence_b.cases}
    failing = {"failed", "error"}
    newly_failing = [
        TestCaseStateChange(
            id=case_id,
            run_a=cases_a[case_id].status if case_id in cases_a else None,
            run_b=cases_b[case_id].status,
        )
        for case_id in sorted(cases_b)
        if cases_b[case_id].status in failing
        and (case_id not in cases_a or cases_a[case_id].status not in failing)
    ]
    restored = [
        TestCaseStateChange(
            id=case_id,
            run_a=cases_a[case_id].status,
            run_b=cases_b[case_id].status if case_id in cases_b else None,
        )
        for case_id in sorted(cases_a)
        if cases_a[case_id].status in failing
        and case_id in cases_b
        and cases_b[case_id].status == "passed"
    ]
    durations: list[TestCaseDurationChange] = []
    for case_id in sorted(cases_a.keys() & cases_b.keys()):
        before = cases_a[case_id].duration_seconds
        after = cases_b[case_id].duration_seconds
        delta = after - before
        percent = delta / before * 100 if before > 0 else float("inf")
        if abs(delta) >= 0.1 and (before == 0 or abs(percent) >= 50):
            durations.append(
                TestCaseDurationChange(
                    id=case_id,
                    run_a_seconds=round(before, 6),
                    run_b_seconds=round(after, 6),
                    delta_seconds=round(delta, 6),
                    percent_change=round(percent, 2) if before > 0 else 100.0,
                )
            )
    return TestCaseComparison(
        availability_a="available",
        availability_b="available",
        newly_failing=newly_failing,
        restored_to_passing=restored,
        duration_changes=durations,
    )


def _environment_fields(result: GradeResult) -> dict[str, str]:
    snapshot = result.environment.snapshot
    if snapshot is None:
        return {}
    fields = {
        "architecture": snapshot.architecture,
        "executor": snapshot.executor,
        "operating_system": snapshot.operating_system,
        "operating_system_release": snapshot.operating_system_release,
        "python_implementation": snapshot.python_implementation,
        "python_version": snapshot.python_version,
        "repogym_version": snapshot.repogym_version,
    }
    fields.update(
        {f"dependency.{name}": version for name, version in snapshot.dependencies.items()}
    )
    return fields


def _compare_environments(
    result_a: GradeResult,
    result_b: GradeResult,
) -> EnvironmentComparison:
    environment_a = result_a.environment
    environment_b = result_b.environment
    if environment_a.availability != "available" or environment_b.availability != "available":
        reasons = f"A={environment_a.reason}, B={environment_b.reason}"
        return EnvironmentComparison(
            availability_a=environment_a.availability,
            availability_b=environment_b.availability,
            matches=None,
            fingerprint_a=environment_a.fingerprint,
            fingerprint_b=environment_b.fingerprint,
            warning=f"Runtime environment comparison unavailable ({reasons}).",
            differences=[],
        )
    fields_a = _environment_fields(result_a)
    fields_b = _environment_fields(result_b)
    differences = [
        EnvironmentDifference(
            field=name,
            run_a=fields_a.get(name),
            run_b=fields_b.get(name),
        )
        for name in sorted(fields_a.keys() | fields_b.keys())
        if fields_a.get(name) != fields_b.get(name)
    ]
    matches = environment_a.fingerprint == environment_b.fingerprint
    return EnvironmentComparison(
        availability_a="available",
        availability_b="available",
        matches=matches,
        fingerprint_a=environment_a.fingerprint,
        fingerprint_b=environment_b.fingerprint,
        warning=(
            None if matches else "Runtime environments differ; result changes may not be task-only."
        ),
        differences=differences,
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
    environment = _compare_environments(result_a, result_b)
    if environment.matches is False and environment.warning is not None:
        warnings.append(environment.warning)
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
        test_cases=_compare_test_cases(result_a, result_b),
        environment=environment,
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
    if comparison.test_cases.warning:
        console.print(f"[yellow]{comparison.test_cases.warning}[/yellow]")
    if comparison.test_cases.newly_failing:
        console.print("[red]Newly failing tests:[/red]")
        for change in comparison.test_cases.newly_failing:
            console.print(f"  - {change.id}: {change.run_a or 'missing'} -> {change.run_b}")
    if comparison.test_cases.restored_to_passing:
        console.print("[green]Tests restored to passing:[/green]")
        for change in comparison.test_cases.restored_to_passing:
            console.print(f"  - {change.id}: {change.run_a} -> {change.run_b}")
    if comparison.test_cases.duration_changes:
        console.print("[yellow]Significant test duration changes:[/yellow]")
        for duration_change in comparison.test_cases.duration_changes:
            console.print(
                f"  - {duration_change.id}: {duration_change.run_a_seconds:.3f}s -> "
                f"{duration_change.run_b_seconds:.3f}s "
                f"({duration_change.delta_seconds:+.3f}s)"
            )
    if comparison.environment.warning and comparison.environment.matches is not False:
        console.print(f"[yellow]{comparison.environment.warning}[/yellow]")
    if comparison.environment.matches is True:
        console.print(
            f"Runtime environment: match ({(comparison.environment.fingerprint_a or '')[:12]})"
        )
    elif comparison.environment.matches is False:
        console.print("[yellow]Runtime environment differences:[/yellow]")
        for difference in comparison.environment.differences:
            console.print(
                f"  - {difference.field}: "
                f"{difference.run_a or 'missing'} -> {difference.run_b or 'missing'}"
            )


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

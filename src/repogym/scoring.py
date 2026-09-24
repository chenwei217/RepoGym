"""Transparent deterministic scoring rules."""

from __future__ import annotations

import ast
from pathlib import Path

from repogym.executors.base import Executor
from repogym.models import DimensionResult, ExecutionResult, TaskSpec, TestCounts
from repogym.security import path_matches


def _weighted_ratio(weight: int, passed: int, total: int) -> float:
    return round(weight * (passed / total if total else 0.0), 2)


def score_correctness(task: TaskSpec, counts: TestCounts) -> DimensionResult:
    score = _weighted_ratio(task.scoring.correctness.weight, counts.passed, counts.total)
    return DimensionResult(
        score=score,
        max_score=task.scoring.correctness.weight,
        reason=f"{counts.passed}/{counts.total} tests passed.",
    )


def score_regression(task: TaskSpec, counts: TestCounts) -> DimensionResult:
    score = _weighted_ratio(task.scoring.regression_safety.weight, counts.passed, counts.total)
    return DimensionResult(
        score=score,
        max_score=task.scoring.regression_safety.weight,
        reason=f"{counts.passed}/{counts.total} public regression tests passed.",
    )


def score_scope(task: TaskSpec, changed: list[str]) -> tuple[DimensionResult, list[str]]:
    forbidden = [
        path
        for path in changed
        if any(path_matches(path, pattern) for pattern in task.constraints.forbidden_paths)
    ]
    outside = [
        path
        for path in changed
        if not any(path_matches(path, pattern) for pattern in task.constraints.allowed_paths)
    ]
    violations = [f"Forbidden path modified: {path}" for path in forbidden]
    violations.extend(
        f"Path outside allowed scope: {path}" for path in outside if path not in forbidden
    )
    weight = task.scoring.scope_control.weight
    if forbidden:
        score = 0.0
    elif not changed:
        score = float(weight)
    else:
        score = round(weight * (1 - len(outside) / len(changed)), 2)
    reason = (
        "All changes are in scope." if not violations else f"{len(violations)} scope violation(s)."
    )
    return DimensionResult(score=score, max_score=weight, reason=reason), violations


def score_quality(
    task: TaskSpec,
    workspace: Path,
    changed: list[str],
    executor: Executor,
) -> DimensionResult:
    weight = task.scoring.code_quality.weight
    python_files = [
        path for path in changed if path.endswith(".py") and (workspace / path).is_file()
    ]
    if not python_files:
        return DimensionResult(
            score=float(weight), max_score=weight, reason="No changed Python files."
        )
    syntax_ok = True
    for relative in python_files:
        try:
            ast.parse((workspace / relative).read_text(encoding="utf-8"), filename=relative)
        except (SyntaxError, UnicodeError):
            syntax_ok = False
            break
    syntax_points = weight / 2 if syntax_ok else 0.0
    lint: ExecutionResult = executor.execute(
        ["ruff", "check", "--quiet", *python_files], workspace, task.execution.timeout_seconds
    )
    lint_ok = not lint.timed_out and lint.return_code == 0
    lint_points = weight / 2 if lint_ok else 0.0
    reason = (
        f"Syntax {'passed' if syntax_ok else 'failed'}; ruff {'passed' if lint_ok else 'failed'}."
    )
    return DimensionResult(
        score=round(syntax_points + lint_points, 2), max_score=weight, reason=reason
    )

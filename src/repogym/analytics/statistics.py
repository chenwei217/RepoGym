"""Deterministic descriptive statistics; no inference from missing outcomes."""

import math
from collections import Counter, defaultdict
from collections.abc import Iterable
from statistics import fmean, median
from typing import Literal

from repogym.analytics.models import CaseStability, MetricStats
from repogym.models import GradeResult, TestCaseResult


def summarize(values: Iterable[float]) -> MetricStats | None:
    ordered = sorted(values)
    if not ordered:
        return None
    if any(not math.isfinite(value) for value in ordered):
        raise ValueError("Statistics require finite observations")
    return MetricStats(
        count=len(ordered),
        minimum=round(ordered[0], 6),
        maximum=round(ordered[-1], 6),
        mean=round(fmean(ordered), 6),
        median=round(float(median(ordered)), 6),
        p95=round(ordered[math.ceil(0.95 * len(ordered)) - 1], 6),
    )


def measured_execution(result: GradeResult) -> bool:
    return result.status == "completed" and (result.cache is None or not result.cache.hit)


def case_statistics(runs: list[GradeResult]) -> list[CaseStability]:
    cases: dict[str, list[TestCaseResult]] = defaultdict(list)
    timings: dict[str, list[float]] = defaultdict(list)
    for run in runs:
        for case in run.test_evidence.cases:
            cases[case.id].append(case)
            if case.status != "skipped" and measured_execution(run):
                timings[case.id].append(case.duration_seconds)
    results: list[CaseStability] = []
    for case_id, observations in sorted(cases.items()):
        counts = Counter(case.status for case in observations)
        outcomes = {case.status for case in observations if case.status != "skipped"}
        observed = len(observations) - counts["skipped"]
        classification: Literal["stable", "variable", "insufficient"] = (
            "insufficient" if observed < 2 else "variable" if len(outcomes) > 1 else "stable"
        )
        results.append(
            CaseStability(
                id=case_id,
                observed=len(observations),
                missing=len(runs) - len(observations),
                passed=counts["passed"],
                failed=counts["failed"],
                error=counts["error"],
                skipped=counts["skipped"],
                classification=classification,
                duration_seconds=summarize(timings[case_id]),
            )
        )
    return results

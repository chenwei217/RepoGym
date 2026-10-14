from collections.abc import Callable
from pathlib import Path

import pytest

from repogym.analytics import analyze_runs
from repogym.analytics.statistics import summarize


def _cases(status: str, *, case_id: str = "tests::case", duration: float = 1.0) -> dict:
    return {
        "schema_version": 1,
        "availability": "available",
        "source": "pytest_junit",
        "reason": "collected",
        "cases": [{"id": case_id, "status": status, "duration_seconds": duration}],
    }


def test_quantiles_and_empty_or_invalid_samples() -> None:
    stats = summarize(range(1, 21))
    assert stats is not None
    assert (stats.minimum, stats.maximum, stats.median, stats.p95, stats.mean) == (
        1,
        20,
        10.5,
        19,
        10.5,
    )
    assert summarize([]) is None
    with pytest.raises(ValueError, match="finite"):
        summarize([float("inf")])


def test_case_variation_missing_and_skipped_outcomes(
    analysis_factory: Callable[..., Path],
) -> None:
    failed = analysis_factory("run-a", score=50, test_evidence=_cases("failed", duration=2))
    passed = analysis_factory("run-b", test_evidence=_cases("passed", duration=1))
    missing = analysis_factory("run-c")
    skipped = analysis_factory("run-d", test_evidence=_cases("skipped", duration=0))
    group = analyze_runs([skipped, failed, missing, passed]).cohorts[0]
    case = group.cases[0]
    assert case.classification == "variable"
    assert (case.passed, case.failed, case.skipped, case.missing) == (1, 1, 1, 1)
    assert case.duration_seconds is not None and case.duration_seconds.median == 1.5
    assert "per_test_evidence_unavailable" in group.warnings
    assert analyze_runs([passed]).cohorts[0].cases[0].classification == "insufficient"


def test_timeouts_and_cached_measurements_never_enter_duration_samples(
    analysis_factory: Callable[..., Path],
) -> None:
    normal = analysis_factory("run-a", duration_seconds=2, test_evidence=_cases("passed"))
    timeout = analysis_factory("run-b", status="timed_out", duration_seconds=99)
    cached = analysis_factory(
        "run-c",
        duration_seconds=1000,
        cache={"key": "c" * 64, "hit": True},
        test_evidence=_cases("passed", duration=1000),
    )
    group = analyze_runs([normal, timeout, cached], include_cached=True).cohorts[0]
    assert group.duration_seconds is not None
    assert (group.duration_seconds.count, group.duration_seconds.median) == (1, 2)
    assert group.cases[0].classification == "stable"
    assert group.cases[0].duration_seconds is not None
    assert group.cases[0].duration_seconds.count == 1


def test_nonfinite_per_case_measurements_are_rejected(
    analysis_factory: Callable[..., Path],
) -> None:
    run = analysis_factory(test_evidence=_cases("passed", duration=float("inf")))
    assert analyze_runs([run]).excluded[0].code == "invalid_artifact"

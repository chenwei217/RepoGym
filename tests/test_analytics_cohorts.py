import json
import shutil
from collections.abc import Callable
from pathlib import Path

import pytest

from repogym.analytics import AnalysisError, analyze_runs, render_analysis


def test_grouping_uses_task_candidate_and_environment_identities(
    analysis_factory: Callable[..., Path],
) -> None:
    a = analysis_factory("run-a")
    b = analysis_factory("run-b", score=50)
    c = analysis_factory("run-c", candidate_fingerprint="c" * 64)
    d = analysis_factory("run-d", python_version="3.12.0")
    e = analysis_factory("run-e", task_fingerprint="d" * 64)
    report = analyze_runs([e, c, b, d, a])
    assert sorted(group.run_count for group in report.cohorts) == [1, 1, 1, 2]
    combined = next(group for group in report.cohorts if group.run_count == 2)
    assert combined.run_ids == ["run-a", "run-b"]
    assert combined.perfect_score_rate == 0.5
    assert render_analysis(report, "json") == render_analysis(analyze_runs([a, b, c, d, e]), "json")


def test_legacy_missing_identities_and_cache_replays_are_explicit(
    analysis_factory: Callable[..., Path],
) -> None:
    paths = [
        analysis_factory("run-a", candidate_fingerprint=None),
        analysis_factory("run-b", task_fingerprint=None),
        analysis_factory(
            "run-c", environment={"availability": "unavailable", "reason": "legacy_run"}
        ),
        analysis_factory("run-d", cache={"key": "f" * 64, "hit": True}),
    ]
    report = analyze_runs(paths)
    assert not report.cohorts
    assert {issue.code for issue in report.excluded} == {
        "candidate_identity_unavailable",
        "task_identity_unavailable",
        "environment_unavailable",
        "cache_replay",
    }
    included = analyze_runs([paths[-1]], include_cached=True).cohorts[0]
    assert included.run_count == 1
    assert included.duration_seconds is None


def test_duplicates_and_conflicting_run_ids_are_order_independent(
    analysis_factory: Callable[..., Path],
    tmp_path: Path,
) -> None:
    run = analysis_factory()
    duplicate = analyze_runs([run, run])
    assert duplicate.cohorts[0].run_count == 1
    assert duplicate.excluded[0].code == "duplicate_run"
    copied = tmp_path / "other" / run.name
    shutil.copytree(run, copied)
    raw = json.loads((copied / "result.json").read_text(encoding="utf-8"))
    raw["score"] = 10
    (copied / "result.json").write_text(json.dumps(raw), encoding="utf-8")
    first = analyze_runs([run, copied])
    assert first == analyze_runs([copied, run])
    assert not first.cohorts
    assert first.excluded[0].code == "conflicting_run_id"


def test_invalid_bounded_inputs_never_read_stdout(
    analysis_factory: Callable[..., Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = analysis_factory()
    (run / "stdout.txt").unlink()
    assert analyze_runs([run]).cohorts
    bad = tmp_path / "bad"
    bad.mkdir()
    (bad / "result.json").write_text("not json", encoding="utf-8")
    report = analyze_runs([run, bad])
    assert report.excluded[0].code == "invalid_artifact"
    with pytest.raises(AnalysisError, match="between"):
        analyze_runs([])
    monkeypatch.setattr("repogym.analytics.cohorts.MAX_RUNS", 1)
    with pytest.raises(AnalysisError, match="between"):
        analyze_runs([run, run])
    monkeypatch.setattr("repogym.analytics.cohorts.MAX_INPUT_BYTES", 8)
    with pytest.raises(AnalysisError, match="byte limit"):
        analyze_runs([run])

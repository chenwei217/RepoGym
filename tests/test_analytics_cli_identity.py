import json
from collections.abc import Callable
from pathlib import Path

from typer.testing import CliRunner

from repogym.analytics import analyze_runs, render_analysis
from repogym.cache import build_cache_key
from repogym.cli import app
from repogym.evidence import load_evidence
from repogym.grader import grade_submission
from repogym.loader import load_task
from repogym.models import ExecutionResult
from repogym.reports import load_run
from repogym.reproducibility import candidate_fingerprint


def test_cli_formats_privacy_and_exit_codes(
    analysis_factory: Callable[..., Path],
    tmp_path: Path,
) -> None:
    run = analysis_factory(
        test_evidence={
            "availability": "available",
            "source": "pytest_junit",
            "reason": "collected",
            "cases": [
                {
                    "id": "tests::<script>api_key=synthetic-value</script>",
                    "status": "passed",
                    "duration_seconds": 1,
                }
            ],
        }
    )
    runner = CliRunner()
    report = analyze_runs([run])
    html = render_analysis(report, "html")
    assert "<script>" not in html and "&lt;script&gt;" in html
    assert "synthetic-value" not in html
    output = tmp_path / "analysis.html"
    for format_name in ("terminal", "json", "html"):
        args = ["analyze", str(run), "--format", format_name]
        rendered = runner.invoke(app, args)
        assert rendered.exit_code == 0, rendered.output
        assert "synthetic-value" not in rendered.stdout
        if format_name == "json":
            assert json.loads(rendered.stdout)["schema_version"] == 1
    saved = runner.invoke(app, ["analyze", str(run), "--format", "html", "--output", str(output)])
    assert saved.exit_code == 0 and output.read_text(encoding="utf-8") == html
    duplicate = runner.invoke(app, ["analyze", str(run), str(run), "--format", "json"])
    assert duplicate.exit_code == 0
    assert json.loads(duplicate.stdout)["cohorts"][0]["run_count"] == 1
    missing = runner.invoke(app, ["analyze", str(tmp_path / "missing"), "--format", "json"])
    assert missing.exit_code == 40
    assert json.loads(missing.stdout)["excluded"][0]["code"] == "invalid_artifact"
    (run / "result.json").write_text('{"invalid": true}', encoding="utf-8")
    assert runner.invoke(app, ["analyze", str(run)]).exit_code == 40


def test_candidate_identity_is_persisted_stable_and_changes_with_content(
    valid_task: Path,
    tmp_path: Path,
) -> None:
    class FixtureExecutor:
        def execute(self, command: list[str], cwd: Path, timeout_seconds: int) -> ExecutionResult:
            return ExecutionResult(
                command=command, return_code=0, stdout="2 passed", stderr="", duration_seconds=0.1
            )

    submission = tmp_path / "candidate"
    (submission / "src").mkdir(parents=True)
    code = submission / "src" / "answer.py"
    code.write_text("VALUE = 1\n", encoding="utf-8")
    root = tmp_path / "runs"
    cache = tmp_path / "cache"
    first = grade_submission(valid_task, submission, root, FixtureExecutor(), cache_root=cache)
    second = grade_submission(valid_task, submission, root, FixtureExecutor(), cache_root=cache)
    a, b = load_run(first)[0], load_run(second)[0]
    assert (
        a.candidate_fingerprint is not None and a.candidate_fingerprint == b.candidate_fingerprint
    )
    assert b.cache is not None and b.cache.hit
    metadata = json.loads((first / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["candidate_fingerprint"] == a.candidate_fingerprint
    identity = next(r for r in load_evidence(first).records if r.source == "candidate_manifest")
    assert identity.details["sha256"] == a.candidate_fingerprint
    code.write_text("VALUE = 2\n", encoding="utf-8")
    third = grade_submission(valid_task, submission, root, FixtureExecutor(), cache_root=cache)
    assert load_run(third)[0].candidate_fingerprint != a.candidate_fingerprint
    assert candidate_fingerprint({"b": "2", "a": "1"}) == candidate_fingerprint(
        {"a": "1", "b": "2"}
    )
    assert str(tmp_path) not in json.dumps(metadata)


def test_cache_identity_capability_and_no_eligible_cli(
    valid_task: Path,
    tmp_path: Path,
    run_factory: Callable[..., Path],
    monkeypatch,
) -> None:
    task = load_task(valid_task)
    key = build_cache_key(task, "a" * 64, valid_task / "starter", "fixture")
    monkeypatch.setattr("repogym.cache.CANDIDATE_IDENTITY_VERSION", 99)
    assert key != build_cache_key(task, "a" * 64, valid_task / "starter", "fixture")
    legacy = run_factory()
    result = CliRunner().invoke(app, ["analyze", str(legacy), "--format", "json"])
    assert result.exit_code == 10
    assert json.loads(result.stdout)["excluded"][0]["code"] == "candidate_identity_unavailable"

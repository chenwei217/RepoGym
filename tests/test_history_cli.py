import json
from collections.abc import Callable
from pathlib import Path

from typer.testing import CliRunner

from repogym.cli import app
from repogym.exit_codes import ExitCode


def test_refresh_query_show_and_terminal(run_factory: Callable[..., Path]) -> None:
    run = run_factory()
    runner = CliRunner()
    args = ["--runs-dir", str(run.parent)]
    refresh = runner.invoke(app, ["runs", "refresh", *args])
    assert refresh.exit_code == 0, refresh.output
    assert json.loads(refresh.stdout)["runs"][0]["run_id"] == run.name
    queried = runner.invoke(app, ["runs", "list", *args, "--format", "json"])
    assert queried.exit_code == 0, queried.output
    assert json.loads(queried.stdout)["schema_version"] == 1
    assert "sample-task" in runner.invoke(app, ["runs", "list", *args]).stdout
    shown = runner.invoke(app, ["runs", "show", run.name, *args])
    assert shown.exit_code == 0
    assert json.loads(shown.stdout)["score"] == 100
    dated = runner.invoke(
        app, ["runs", "list", *args, "--format", "json", "--since", "2026-01-01T08:00:00+08:00"]
    )
    assert dated.exit_code == 0, dated.output
    assert len(json.loads(dated.stdout)["runs"]) == 1
    future = runner.invoke(
        app, ["runs", "list", *args, "--format", "json", "--since", "2026-01-02T00:00:00Z"]
    )
    assert json.loads(future.stdout)["runs"] == []


def test_cli_errors_are_stable(run_factory: Callable[..., Path], tmp_path: Path) -> None:
    runner = CliRunner()
    missing = runner.invoke(app, ["runs", "refresh", "--runs-dir", str(tmp_path / "missing")])
    assert missing.exit_code == ExitCode.ENVIRONMENT_ERROR
    run = run_factory()
    (run.parent / "broken").mkdir()
    args = ["--runs-dir", str(run.parent)]
    refresh = runner.invoke(app, ["runs", "refresh", *args])
    assert refresh.exit_code == ExitCode.ENVIRONMENT_ERROR
    assert json.loads(refresh.stdout)["diagnostics"][0]["code"] == "invalid_run"
    assert runner.invoke(app, ["runs", "show", "missing", *args]).exit_code == 40
    invalid = runner.invoke(app, ["runs", "list", *args, "--min-score", "90", "--max-score", "10"])
    assert invalid.exit_code == ExitCode.TASK_INVALID
    for value in ("bad", "2026-01-01T00:00:00"):
        result = runner.invoke(app, ["runs", "list", *args, "--since", value])
        assert result.exit_code == ExitCode.TASK_INVALID

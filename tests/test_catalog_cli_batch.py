import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from repogym.batch import load_batch, load_batch_manifest, run_batch
from repogym.catalog import discover_catalog, plan_batch
from repogym.catalog.models import CatalogError
from repogym.cli import app


def test_cli_curation_and_pinned_batch(valid_task: Path, tmp_path: Path) -> None:
    runner = CliRunner()
    catalog = tmp_path / "catalog.json"
    args = ["--tasks-dir", str(valid_task.parent)]
    created = runner.invoke(app, ["catalog", "create", str(catalog), *args])
    assert created.exit_code == 0, created.output
    listed = runner.invoke(app, ["catalog", "list", str(catalog), "--format", "json"])
    assert json.loads(listed.stdout)["tasks"][0]["id"] == "sample-task"
    assert "Sample task" in runner.invoke(app, ["catalog", "list", str(catalog)]).stdout
    assert runner.invoke(app, ["catalog", "verify", str(catalog), *args]).exit_code == 0
    submissions = tmp_path / "candidate roots"
    (submissions / "sample-task").mkdir(parents=True)
    plans = tmp_path / "plans"
    plans.mkdir()
    output = plans / "batch.json"
    planned = runner.invoke(
        app,
        [
            "catalog",
            "batch",
            str(catalog),
            str(output),
            *args,
            "--submissions-dir",
            str(submissions),
        ],
    )
    assert planned.exit_code == 0, planned.output
    job = load_batch_manifest(output).jobs[0]
    assert not Path(job.task).is_absolute()
    assert "\\" not in job.task
    assert (plans / job.task).resolve() == valid_task.resolve()
    assert job.task_fingerprint is not None
    batch = run_batch(output, tmp_path / "batches", tmp_path / "runs", cache_root=None)
    assert load_batch(batch).exit_code == 0


def test_changed_pinned_task_never_launches_grader(
    valid_task: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    catalog = discover_catalog(valid_task.parent)
    submissions = tmp_path / "submissions"
    (submissions / "sample-task").mkdir(parents=True)
    output = tmp_path / "batch.json"
    manifest = plan_batch(catalog, valid_task.parent, submissions, output)
    output.write_text(manifest.model_dump_json(), encoding="utf-8")
    (valid_task / "prompt.md").write_text("Task changed after batch planning", encoding="utf-8")
    called = False

    def forbidden(*args: object, **kwargs: object) -> None:
        nonlocal called
        called = True
        raise AssertionError("grader must not run")

    monkeypatch.setattr("repogym.batch.grade_submission", forbidden)
    batch = load_batch(run_batch(output, tmp_path / "batches", tmp_path / "runs", None))
    assert not called
    assert batch.jobs[0].status == "task_invalid"
    assert "fingerprint mismatch" in (batch.jobs[0].error or "")


def test_author_cli_errors_and_drift(valid_task: Path, tmp_path: Path) -> None:
    runner = CliRunner()
    catalog = tmp_path / "catalog.json"
    args = ["--tasks-dir", str(valid_task.parent)]
    assert (
        runner.invoke(
            app, ["catalog", "create", str(catalog), *args, "--language", "rust"]
        ).exit_code
        == 10
    )
    assert not catalog.exists()
    assert runner.invoke(app, ["catalog", "create", str(catalog), *args]).exit_code == 0
    assert runner.invoke(app, ["catalog", "create", str(catalog), *args]).exit_code == 10
    assert runner.invoke(app, ["catalog", "list", str(tmp_path / "missing")]).exit_code == 10
    assert (
        runner.invoke(app, ["catalog", "verify", str(tmp_path / "missing"), *args]).exit_code == 10
    )
    assert (
        runner.invoke(
            app,
            [
                "catalog",
                "batch",
                str(catalog),
                str(tmp_path / "batch.json"),
                *args,
                "--submissions-dir",
                str(tmp_path / "missing"),
            ],
        ).exit_code
        == 10
    )
    (valid_task / "prompt.md").write_text("Changed", encoding="utf-8")
    drift = runner.invoke(app, ["catalog", "verify", str(catalog), *args])
    assert drift.exit_code == 10
    assert json.loads(drift.stdout)["issues"][0]["code"] == "fingerprint_mismatch"


def test_missing_submissions_drift_and_cross_drive(
    valid_task: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    catalog = discover_catalog(valid_task.parent)
    missing_candidates = tmp_path / "empty-candidates"
    missing_candidates.mkdir()
    with pytest.raises(CatalogError, match="submission"):
        plan_batch(catalog, valid_task.parent, missing_candidates, tmp_path / "batch.json")
    (tmp_path / "sample-task").rename(tmp_path / "moved-task")
    with pytest.raises(CatalogError, match="drift"):
        plan_batch(catalog, valid_task.parent, tmp_path, tmp_path / "batch.json")
    (tmp_path / "moved-task").rename(valid_task)
    submissions = tmp_path / "submissions"
    (submissions / "sample-task").mkdir(parents=True)

    def cross_drive(*args: object) -> str:
        raise ValueError("different drives")

    monkeypatch.setattr("repogym.catalog.selection.os.path.relpath", cross_drive)
    with pytest.raises(CatalogError, match="drive"):
        plan_batch(catalog, valid_task.parent, submissions, tmp_path / "batch.json")

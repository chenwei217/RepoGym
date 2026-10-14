import json
import shutil
from collections.abc import Callable
from pathlib import Path
from threading import Barrier

import pytest
from typer.testing import CliRunner

from repogym.batch import generate_batch_report, load_batch, run_batch
from repogym.cli import app
from repogym.exceptions import BatchError, ReportError, ValidationError


def _manifest(path: Path, jobs: list[dict[str, str]]) -> Path:
    path.write_text(json.dumps({"schema_version": 1, "jobs": jobs}), encoding="utf-8")
    return path


def test_parallel_failure_isolation_and_replay_order(
    tmp_path: Path,
    run_factory: Callable[..., Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gate = Barrier(2)

    def grade(task: Path, submission: Path, **kwargs: object) -> Path:
        if submission.name in {"error", "low"}:
            gate.wait(timeout=10)
        if submission.name == "error":
            raise ValidationError("invalid fixture task")
        return run_factory("run-" + submission.name, score=50 if submission.name == "low" else 100)

    monkeypatch.setattr("repogym.batch.grade_submission", grade)
    manifest = _manifest(
        tmp_path / "batch.json",
        [
            {"id": "z", "task": "task", "submission": "good"},
            {"id": "a", "task": "task", "submission": "error"},
            {"id": "m", "task": "task", "submission": "low"},
        ],
    )
    directory = run_batch(manifest, tmp_path / "batches", max_workers=2, cache_root=None)
    batch = load_batch(directory)
    assert [job.id for job in batch.jobs] == ["a", "m", "z"]
    assert [job.status for job in batch.jobs] == ["task_invalid", "score_not_passed", "success"]
    assert batch.exit_code == 10
    replay = generate_batch_report(directory, "json")
    assert replay is not None and [job["id"] for job in json.loads(replay)["jobs"]] == [
        "a",
        "m",
        "z",
    ]
    policy = json.loads((directory / "schedule.json").read_text(encoding="utf-8"))
    assert policy["max_workers"] == 2 and policy["group_count"] == 3


def test_duplicate_pairs_have_stable_cache_ownership(valid_task: Path, tmp_path: Path) -> None:
    submission = tmp_path / "candidate"
    submission.mkdir()
    manifest = _manifest(
        tmp_path / "batch.json",
        [
            {"id": job, "task": str(valid_task), "submission": str(submission)}
            for job in ("z", "a", "m")
        ],
    )
    directory = run_batch(
        manifest, tmp_path / "batches", tmp_path / "runs", tmp_path / "cache", max_workers=3
    )
    jobs = load_batch(directory).jobs
    assert [job.id for job in jobs] == ["a", "m", "z"]
    assert [job.cache_hit for job in jobs] == [False, True, True]
    assert all(job.exit_code == 0 for job in jobs)
    policy = json.loads((directory / "schedule.json").read_text(encoding="utf-8"))
    assert policy["group_count"] == 1


def test_distinct_paths_with_identical_contents_share_atomic_cache(
    valid_task: Path,
    tmp_path: Path,
) -> None:
    clone = tmp_path / "alias" / valid_task.name
    shutil.copytree(valid_task, clone)
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    manifest = _manifest(
        tmp_path / "batch.json",
        [
            {"id": "a", "task": str(valid_task), "submission": str(candidate)},
            {"id": "b", "task": str(clone), "submission": str(candidate)},
        ],
    )
    directory = run_batch(
        manifest, tmp_path / "batches", tmp_path / "runs", tmp_path / "cache", max_workers=2
    )
    jobs = load_batch(directory).jobs
    assert all(job.exit_code == 0 for job in jobs)
    assert sum(job.cache_hit is True for job in jobs) == 1
    assert len({job.run_id for job in jobs}) == 2


def test_cli_workers_limits_and_interrupt_mapping(
    tmp_path: Path,
    run_factory: Callable[..., Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = _manifest(
        tmp_path / "batch.json",
        [{"id": job, "task": "task", "submission": job} for job in ("b", "a")],
    )
    monkeypatch.setattr(
        "repogym.batch.grade_submission",
        lambda task, submission, **kwargs: run_factory("run-" + submission.name),
    )
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "batch",
            "run",
            str(manifest),
            "--workers",
            "2",
            "--format",
            "json",
            "--batches-dir",
            str(tmp_path / "batches"),
            "--no-cache",
        ],
    )
    assert result.exit_code == 0, result.output
    assert [job["id"] for job in json.loads(result.stdout)["jobs"]] == ["a", "b"]
    assert runner.invoke(app, ["batch", "run", str(manifest), "--workers", "0"]).exit_code == 2
    with pytest.raises(BatchError, match="workers"):
        run_batch(manifest, max_workers=0)

    def interrupt(*args: object, **kwargs: object) -> Path:
        raise KeyboardInterrupt

    monkeypatch.setattr("repogym.cli.run_batch", interrupt)
    assert runner.invoke(app, ["batch", "run", str(manifest), "--workers", "2"]).exit_code == 20


def test_bad_path_resolution_does_not_abort_other_jobs(
    tmp_path: Path,
    run_factory: Callable[..., Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import repogym.batch as module

    original = module._resolve_job_path

    def resolve(base: Path, configured: str) -> Path:
        if configured == "broken":
            raise ReportError("Cannot resolve batch input path")
        return original(base, configured)

    monkeypatch.setattr(module, "_resolve_job_path", resolve)
    monkeypatch.setattr(
        module,
        "grade_submission",
        lambda task, submission, **kwargs: run_factory("run-" + submission.name),
    )
    manifest = _manifest(
        tmp_path / "batch.json",
        [
            {"id": "a", "task": "broken", "submission": "candidate"},
            {"id": "b", "task": "valid", "submission": "candidate"},
        ],
    )
    batch = load_batch(run_batch(manifest, tmp_path / "batches", max_workers=2, cache_root=None))
    assert [job.status for job in batch.jobs] == ["environment_error", "success"]

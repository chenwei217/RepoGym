from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from repogym.cli import app
from repogym.exceptions import ExecutionError, ExecutorUnavailableError
from repogym.executors import DockerExecutor, LocalExecutor
from repogym.exit_codes import ExitCode
from repogym.grader import grade_submission
from repogym.models import ExecutionResult, ExecutorCapabilities
from repogym.reports import load_run

ROOT = Path(__file__).parents[1]


class RecordingRunner:
    def __init__(self, *, stopped: str | None = None) -> None:
        self.commands: list[list[str]] = []
        self.stopped = stopped

    def execute(
        self,
        command: list[str],
        cwd: Path,
        timeout_seconds: int,
        cancellation_token: object | None = None,
    ) -> ExecutionResult:
        self.commands.append(command)
        if self.stopped is not None:
            cidfile = Path(command[command.index("--cidfile") + 1])
            cidfile.write_text("safe-container-id", encoding="utf-8")
        return ExecutionResult(
            command=command,
            return_code=None if self.stopped else 0,
            stdout="ok",
            stderr="",
            duration_seconds=0.01,
            timed_out=self.stopped == "timeout",
            cancelled=self.stopped == "cancelled",
        )


def available_capabilities() -> ExecutorCapabilities:
    return ExecutorCapabilities(
        backend="docker",
        available=True,
        availability_reason="test daemon",
        filesystem_isolation=True,
        network_control=True,
        cpu_limit=True,
        memory_limit=True,
        process_limit=True,
    )


def test_local_executor_declares_non_isolated_capabilities() -> None:
    executor = LocalExecutor()
    assert executor.capabilities().model_dump() == {
        "backend": "local",
        "available": True,
        "availability_reason": "Local subprocess execution is available.",
        "filesystem_isolation": False,
        "network_control": False,
        "cpu_limit": False,
        "memory_limit": False,
        "process_limit": False,
    }
    assert executor.policy().filesystem_mode == "host"
    assert executor.policy().network_mode == "host"


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"image": "bad image"}, "image reference"),
        ({"image": "python:3.12", "cpu_limit": 0}, "must be positive"),
        ({"image": "python:3.12", "memory_limit_bytes": 0}, "must be positive"),
        ({"image": "python:3.12", "process_limit": 0}, "must be positive"),
    ],
)
def test_docker_executor_rejects_unsafe_policy(kwargs: dict[str, object], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        DockerExecutor(**kwargs)  # type: ignore[arg-type]


def test_docker_capabilities_distinguish_missing_cli_and_daemon(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executor = DockerExecutor("python:3.12-slim")
    monkeypatch.setattr("repogym.executors.docker.shutil.which", lambda _command: None)
    missing = executor.capabilities()
    assert not missing.available
    assert "CLI not found" in missing.availability_reason

    monkeypatch.setattr("repogym.executors.docker.shutil.which", lambda _command: "docker")
    monkeypatch.setattr(
        "repogym.executors.docker.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 1, "", "daemon stopped"),
    )
    stopped = executor.capabilities()
    assert not stopped.available
    assert stopped.availability_reason == "Docker daemon unavailable: daemon stopped"


def test_docker_command_is_bounded_non_networked_and_maps_workspace(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    cwd = workspace / "project"
    cwd.mkdir(parents=True)
    junit = workspace / "results.xml"
    executor = DockerExecutor(
        "python:3.12-slim",
        cpu_limit=1.5,
        memory_limit_bytes=64 * 1024 * 1024,
        process_limit=32,
    )
    command, mount_root = executor.build_command(
        [sys.executable, "-m", "pytest", f"--junitxml={junit}"],
        cwd,
        tmp_path / "container.cid",
    )
    assert mount_root == workspace
    assert command[:3] == ["docker", "run", "--rm"]
    assert "--read-only" in command
    assert command[command.index("--network") :][:2] == ["--network", "none"]
    assert command[command.index("--cpus") :][:2] == ["--cpus", "1.5"]
    assert ["--memory", str(64 * 1024 * 1024)] == command[command.index("--memory") :][:2]
    assert command[command.index("--pids-limit") :][:2] == ["--pids-limit", "32"]
    assert command[-5:] == [
        "python:3.12-slim",
        "python",
        "-m",
        "pytest",
        "--junitxml=/workspace/results.xml",
    ]


def test_docker_command_rejects_external_absolute_paths(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    external = tmp_path.parent / "outside.txt"
    executor = DockerExecutor("python:3.12-slim")
    with pytest.raises(ExecutionError, match="outside the workspace"):
        executor.build_command(["tool", str(external)], workspace, tmp_path / "container.cid")


def test_docker_network_access_requires_explicit_policy(tmp_path: Path) -> None:
    executor = DockerExecutor("python:3.12-slim", network_disabled=False)
    command, _ = executor.build_command(["python", "-V"], tmp_path, tmp_path / "container.cid")
    assert command[command.index("--network") :][:2] == ["--network", "bridge"]
    assert executor.policy().network_mode == "bridge"


def test_unavailable_docker_never_invokes_or_falls_back(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    runner = RecordingRunner()
    executor = DockerExecutor("python:3.12-slim", runner=runner)
    monkeypatch.setattr(
        executor,
        "capabilities",
        lambda: available_capabilities().model_copy(
            update={"available": False, "availability_reason": "daemon unavailable"}
        ),
    )
    with pytest.raises(ExecutorUnavailableError, match="daemon unavailable"):
        executor.execute(["python", "-V"], tmp_path, 10)
    assert runner.commands == []


@pytest.mark.parametrize("stopped", ["timeout", "cancelled"])
def test_docker_stopped_runs_force_remove_container(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, stopped: str
) -> None:
    runner = RecordingRunner(stopped=stopped)
    executor = DockerExecutor("python:3.12-slim", runner=runner)
    monkeypatch.setattr(executor, "capabilities", available_capabilities)
    cleanup: list[list[str]] = []

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        cleanup.append(command)
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr("repogym.executors.docker.subprocess.run", fake_run)
    result = executor.execute(["python", "-V"], tmp_path, 10)
    assert result.timed_out is (stopped == "timeout")
    assert result.cancelled is (stopped == "cancelled")
    assert cleanup == [["docker", "rm", "--force", "safe-container-id"]]


def test_docker_policy_is_persisted_without_host_identity(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    executor = DockerExecutor(
        "python:3.12-slim",
        network_disabled=True,
        cpu_limit=2,
        memory_limit_bytes=128 * 1024 * 1024,
        process_limit=64,
    )
    monkeypatch.setattr(executor, "execute", LocalExecutor().execute)
    run_dir = grade_submission(
        ROOT / "tasks" / "python-cache-ttl",
        ROOT / "examples" / "submissions" / "cache-ttl-fixed",
        tmp_path / "runs",
        executor=executor,
    )
    result, _, _ = load_run(run_dir)
    assert result.score == 100
    assert result.execution is not None
    assert result.execution.executor_policy == executor.policy()
    serialized = json.dumps(result.model_dump(mode="json"))
    assert str(tmp_path) not in serialized
    assert os.environ.get("USERNAME", "value-not-present") not in serialized


def test_executor_info_reports_failure_without_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("repogym.executors.docker.shutil.which", lambda _command: None)
    result = CliRunner().invoke(app, ["executor-info", "--backend", "docker"])
    assert result.exit_code == int(ExitCode.ENVIRONMENT_ERROR)
    assert "Docker CLI not found" in result.output
    assert "will not fall back" in result.output


def test_grade_rejects_unavailable_explicit_docker_without_running(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("repogym.executors.docker.shutil.which", lambda _command: None)
    result = CliRunner().invoke(
        app,
        [
            "grade",
            "missing-task",
            "--submission",
            "missing-submission",
            "--executor",
            "docker",
            "--docker-image",
            "python:3.12-slim",
        ],
    )
    assert result.exit_code == int(ExitCode.ENVIRONMENT_ERROR)
    assert "Docker CLI not found" in result.output
    assert "Task directory" not in result.output


@pytest.mark.skipif(
    not os.environ.get("REPOGYM_TEST_DOCKER_IMAGE"),
    reason="set REPOGYM_TEST_DOCKER_IMAGE to test a locally available image",
)
def test_docker_integration_with_explicit_preloaded_image(tmp_path: Path) -> None:
    image = os.environ["REPOGYM_TEST_DOCKER_IMAGE"]
    result = DockerExecutor(image).execute(["python", "-c", "print('container-ok')"], tmp_path, 20)
    assert result.return_code == 0
    assert result.stdout.strip() == "container-ok"

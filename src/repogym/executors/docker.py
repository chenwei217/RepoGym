"""Explicit Docker/OCI executor with bounded resource and network policy."""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path, PurePosixPath

from repogym.exceptions import ExecutionError, ExecutorUnavailableError
from repogym.executors.base import CancellationToken, Executor
from repogym.executors.local import (
    DEFAULT_OUTPUT_LIMIT_BYTES,
    LocalExecutor,
)
from repogym.models import ExecutionResult, ExecutorCapabilities, ExecutorPolicyEvidence
from repogym.security import redact_sensitive_text

_IMAGE_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@-]*$")
_CONTAINER_WORKSPACE = PurePosixPath("/workspace")


class DockerExecutor:
    """Run commands through Docker only when explicitly instantiated."""

    def __init__(
        self,
        image: str,
        *,
        docker_command: str = "docker",
        network_disabled: bool = True,
        cpu_limit: float = 1.0,
        memory_limit_bytes: int = 512 * 1024 * 1024,
        process_limit: int = 128,
        max_stdout_bytes: int = DEFAULT_OUTPUT_LIMIT_BYTES,
        max_stderr_bytes: int = DEFAULT_OUTPUT_LIMIT_BYTES,
        runner: Executor | None = None,
    ) -> None:
        if not _IMAGE_PATTERN.fullmatch(image):
            raise ValueError("Docker image must be a non-empty image reference without whitespace")
        if cpu_limit <= 0 or memory_limit_bytes <= 0 or process_limit <= 0:
            raise ValueError("Docker CPU, memory, and process limits must be positive")
        self.image = image
        self.docker_command = docker_command
        self.network_disabled = network_disabled
        self.cpu_limit = cpu_limit
        self.memory_limit_bytes = memory_limit_bytes
        self.process_limit = process_limit
        self.max_stdout_bytes = max_stdout_bytes
        self.max_stderr_bytes = max_stderr_bytes
        self._runner = runner or LocalExecutor(max_stdout_bytes, max_stderr_bytes)

    def capabilities(self) -> ExecutorCapabilities:
        executable = shutil.which(self.docker_command)
        if executable is None:
            return ExecutorCapabilities(
                backend="docker",
                available=False,
                availability_reason=f"Docker CLI not found: {self.docker_command}",
                filesystem_isolation=True,
                network_control=True,
                cpu_limit=True,
                memory_limit=True,
                process_limit=True,
            )
        try:
            probe = subprocess.run(
                [executable, "version", "--format", "{{.Server.Version}}"],
                capture_output=True,
                check=False,
                encoding="utf-8",
                errors="replace",
                shell=False,
                timeout=5,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            reason = f"Docker daemon probe failed: {redact_sensitive_text(str(exc))}"
            available = False
        else:
            available = probe.returncode == 0
            if available:
                version = probe.stdout.strip() or "unknown"
                reason = f"Docker daemon available (server {version})."
            else:
                detail = (probe.stderr or probe.stdout).strip().splitlines()
                reason = "Docker daemon unavailable: " + redact_sensitive_text(
                    detail[0] if detail else "version probe failed"
                )
        return ExecutorCapabilities(
            backend="docker",
            available=available,
            availability_reason=reason[:500],
            filesystem_isolation=True,
            network_control=True,
            cpu_limit=True,
            memory_limit=True,
            process_limit=True,
        )

    def policy(self) -> ExecutorPolicyEvidence:
        return ExecutorPolicyEvidence(
            backend="docker",
            filesystem_mode="container_bind",
            network_mode="none" if self.network_disabled else "bridge",
            cpu_limit=self.cpu_limit,
            memory_limit_bytes=self.memory_limit_bytes,
            process_limit=self.process_limit,
            image=self.image,
        )

    @staticmethod
    def _absolute_argument(argument: str) -> tuple[str, Path] | None:
        prefix, separator, value = argument.partition("=")
        candidate = Path(value if separator else argument)
        if not candidate.is_absolute():
            return None
        return (prefix + "=" if separator else ""), candidate

    def _mount_root(self, command: list[str], cwd: Path) -> Path:
        root = cwd.resolve()
        for argument in command:
            prefix, separator, value = argument.partition("=")
            if prefix != "--junitxml" or not separator:
                continue
            output = Path(value).resolve()
            for candidate in (root, *root.parents):
                try:
                    output.relative_to(candidate)
                except ValueError:
                    continue
                root = candidate
                break
            else:
                raise ExecutionError("JUnit output must share the container workspace")
            if root == Path(root.anchor):
                raise ExecutionError("Refusing to bind a filesystem root into the container")
        if "," in str(root):
            raise ExecutionError("Docker workspace paths containing commas are unsupported")
        return root

    def _container_argument(
        self,
        argument: str,
        index: int,
        mount_root: Path,
    ) -> str:
        absolute = self._absolute_argument(argument)
        if absolute is None:
            return argument
        prefix, path = absolute
        if index == 0 and path.resolve() == Path(sys.executable).resolve():
            return "python"
        try:
            relative = path.resolve().relative_to(mount_root)
        except ValueError as exc:
            raise ExecutionError(
                "Container command references an absolute path outside the workspace"
            ) from exc
        container_path = _CONTAINER_WORKSPACE.joinpath(*relative.parts).as_posix()
        return prefix + container_path

    def build_command(self, command: list[str], cwd: Path, cidfile: Path) -> tuple[list[str], Path]:
        """Build Docker argv without invoking a shell or the Docker daemon."""
        if not command:
            raise ExecutionError("Container command must not be empty")
        mount_root = self._mount_root(command, cwd)
        relative_cwd = cwd.resolve().relative_to(mount_root)
        container_cwd = _CONTAINER_WORKSPACE.joinpath(*relative_cwd.parts).as_posix()
        inner = [
            self._container_argument(argument, index, mount_root)
            for index, argument in enumerate(command)
        ]
        docker = [
            self.docker_command,
            "run",
            "--rm",
            "--init",
            "--cidfile",
            str(cidfile),
            "--read-only",
            "--security-opt",
            "no-new-privileges",
            "--tmpfs",
            "/tmp:rw,noexec,nosuid,size=67108864",
            "--mount",
            f"type=bind,source={mount_root},target={_CONTAINER_WORKSPACE}",
            "--workdir",
            container_cwd,
            "--cpus",
            str(self.cpu_limit),
            "--memory",
            str(self.memory_limit_bytes),
            "--pids-limit",
            str(self.process_limit),
        ]
        docker.extend(["--network", "none" if self.network_disabled else "bridge"])
        docker.extend([self.image, *inner])
        return docker, mount_root

    def _force_remove(self, cidfile: Path) -> list[str]:
        if not cidfile.is_file():
            return ["Docker container ID was unavailable during cleanup."]
        try:
            container_id = cidfile.read_text(encoding="utf-8").strip()
            if not container_id:
                return ["Docker container ID was empty during cleanup."]
            cleanup = subprocess.run(
                [self.docker_command, "rm", "--force", container_id],
                capture_output=True,
                check=False,
                encoding="utf-8",
                errors="replace",
                shell=False,
                timeout=10,
            )
        except (OSError, UnicodeError, subprocess.TimeoutExpired) as exc:
            return [f"Docker container cleanup failed: {redact_sensitive_text(str(exc))}"]
        if cleanup.returncode != 0:
            detail = (cleanup.stderr or cleanup.stdout).strip()
            safe_detail = redact_sensitive_text(detail or "unknown error")
            return [f"Docker container cleanup failed: {safe_detail}"]
        return []

    def execute(
        self,
        command: list[str],
        cwd: Path,
        timeout_seconds: int,
        cancellation_token: CancellationToken | None = None,
    ) -> ExecutionResult:
        capabilities = self.capabilities()
        if not capabilities.available:
            raise ExecutorUnavailableError(capabilities.availability_reason)
        with tempfile.TemporaryDirectory(prefix="repogym-docker-") as temporary:
            cidfile = Path(temporary) / "container.cid"
            docker_command, mount_root = self.build_command(command, cwd, cidfile)
            result = self._runner.execute(
                docker_command,
                mount_root,
                timeout_seconds,
                cancellation_token=cancellation_token,
            )
            if result.timed_out or result.cancelled:
                diagnostics = self._force_remove(cidfile)
                result.termination_diagnostics.extend(diagnostics)
                if diagnostics:
                    separator = "\n" if result.stderr and not result.stderr.endswith("\n") else ""
                    result.stderr += separator + "\n".join(diagnostics)
            return result

"""Submission grading and run artifact persistence."""

from __future__ import annotations

import json
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from repogym.cache import ExecutionCache, build_cache_key
from repogym.evidence import build_evidence
from repogym.exceptions import SecurityError, ValidationError
from repogym.executors.base import CancellationToken, Executor
from repogym.executors.local import LocalExecutor
from repogym.models import (
    CacheEvidence,
    DimensionResult,
    ExecutionEvidence,
    GradeResult,
    TaskSpec,
    TestCaseEvidence,
    TestCounts,
)
from repogym.reproducibility import task_fingerprint
from repogym.scoring import score_correctness, score_quality, score_regression, score_scope
from repogym.security import (
    audit_submission,
    changed_paths,
    copy_tree_safe,
    file_manifest,
    redact_known_paths,
    redact_value,
    sanitize_command,
)
from repogym.testing import inject_tests, parse_test_counts, run_tests
from repogym.validator import validate_task


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _cancelled_dimensions(task: TaskSpec) -> dict[str, DimensionResult]:
    def dimension(max_score: int) -> DimensionResult:
        return DimensionResult(score=0, max_score=max_score, reason="Execution cancelled.")

    return {
        "correctness": dimension(task.scoring.correctness.weight),
        "regression_safety": dimension(task.scoring.regression_safety.weight),
        "code_quality": dimension(task.scoring.code_quality.weight),
        "scope_control": dimension(task.scoring.scope_control.weight),
    }


def _new_run_id() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]


def _executor_cache_identity(executor: Executor) -> str:
    kind = f"{type(executor).__module__}.{type(executor).__qualname__}"
    if isinstance(executor, LocalExecutor):
        return f"{kind}:stdout={executor.max_stdout_bytes}:stderr={executor.max_stderr_bytes}"
    return kind


def grade_submission(
    task_directory: Path,
    submission: Path,
    output_root: Path = Path(".repogym/runs"),
    executor: Executor | None = None,
    cancellation_token: CancellationToken | None = None,
    cache_root: Path | None = None,
) -> Path:
    validation = validate_task(task_directory)
    if not validation.valid or validation.task is None:
        raise ValidationError("Task validation failed:\n  - " + "\n  - ".join(validation.errors))
    if not submission.is_dir():
        raise SecurityError(f"Submission directory does not exist: {submission}")
    task = validation.task
    audit = audit_submission(submission, task)
    if not audit.accepted:
        raise SecurityError("Submission audit failed:\n  - " + "\n  - ".join(audit.violations))
    fingerprint = task_fingerprint(task_directory, task)
    runner = executor or LocalExecutor()
    if cache_root is None:
        return _grade_validated(
            task_directory,
            submission,
            output_root,
            runner,
            cancellation_token,
            task,
            fingerprint,
            _new_run_id(),
        )
    key = build_cache_key(task, fingerprint, submission, _executor_cache_identity(runner))
    cache = ExecutionCache(cache_root)
    lock_timeout = max(30, task.execution.timeout_seconds * 3 + 30)
    with cache.lock(key, timeout_seconds=lock_timeout):
        run_id = _new_run_id()
        restored = cache.restore(key, output_root, run_id)
        if restored is not None:
            return restored
        run_dir = _grade_validated(
            task_directory,
            submission,
            output_root,
            runner,
            cancellation_token,
            task,
            fingerprint,
            run_id,
            key,
        )
        persisted = GradeResult.model_validate_json(
            (run_dir / "result.json").read_text(encoding="utf-8")
        )
        if persisted.status == "completed":
            cache.store(key, run_dir)
        return run_dir


def _grade_validated(
    task_directory: Path,
    submission: Path,
    output_root: Path,
    runner: Executor,
    cancellation_token: CancellationToken | None,
    task: TaskSpec,
    fingerprint: str,
    run_id: str,
    cache_key: str | None = None,
) -> Path:
    run_dir = output_root.resolve() / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    created_at = datetime.now(UTC)

    with tempfile.TemporaryDirectory(prefix="repogym-grade-") as temporary:
        workspace = Path(temporary) / "workspace"
        copy_tree_safe(task_directory.resolve() / "starter", workspace)
        original = file_manifest(workspace)
        copy_tree_safe(submission.resolve(), workspace)
        submitted = file_manifest(workspace)
        changed = changed_paths(original, submitted)
        inject_tests(task_directory.resolve(), workspace)
        all_result = run_tests(task, workspace, runner, cancellation_token=cancellation_token)
        all_counts = parse_test_counts(all_result)
        expected_total = task.expected.passing_tests_after
        all_counts.passed = min(all_counts.passed, expected_total)
        all_counts.total = expected_total
        all_counts.failed = expected_total - all_counts.passed
        scope, violations = score_scope(task, changed)
        cancelled = all_result.cancelled
        public_result = None
        quality = None
        if not cancelled:
            public_result = run_tests(task, workspace, runner, "tests/public", cancellation_token)
            cancelled = public_result.cancelled
        if not cancelled:
            quality = score_quality(task, workspace, changed, runner, cancellation_token)
            cancelled = cancellation_token is not None and cancellation_token.cancelled
        if cancelled:
            dimensions = _cancelled_dimensions(task)
            all_counts = TestCounts(passed=0, failed=expected_total, total=expected_total)
            status: Literal["completed", "timed_out", "cancelled", "error"] = "cancelled"
        else:
            assert public_result is not None
            assert quality is not None
            public_counts = parse_test_counts(public_result)
            dimensions = {
                "correctness": score_correctness(task, all_counts),
                "regression_safety": score_regression(task, public_counts),
                "code_quality": quality,
                "scope_control": scope,
            }
            status = "timed_out" if all_result.timed_out else "completed"
            if all_result.return_code is None and not all_result.timed_out:
                status = "error"
        score = round(sum(item.score for item in dimensions.values()), 2)
        sensitive_roots = [workspace.resolve(), task_directory.resolve(), submission.resolve()]
        evidence = ExecutionEvidence(
            argv=sanitize_command(all_result.command, sensitive_roots),
            exit_code=all_result.return_code,
            timed_out=all_result.timed_out,
            cancelled=cancelled,
            duration_seconds=round(all_result.duration_seconds, 3),
            working_directory="<WORKSPACE>",
            stdout_file="stdout.txt",
            stderr_file="stderr.txt",
            test_statistics_source=(
                "pytest_junit"
                if all_result.test_evidence is not None
                and all_result.test_evidence.availability == "available"
                else "pytest_summary"
            ),
            termination_diagnostics=all_result.termination_diagnostics,
            stdout_bytes=all_result.stdout_bytes,
            stderr_bytes=all_result.stderr_bytes,
            stdout_truncated=all_result.stdout_truncated,
            stderr_truncated=all_result.stderr_truncated,
        )
        cache_evidence = CacheEvidence(key=cache_key, hit=False) if cache_key is not None else None
        result = GradeResult(
            task_id=task.id,
            task_fingerprint=fingerprint,
            run_id=run_id,
            status=status,
            score=max(0.0, min(100.0, score)),
            dimensions=dimensions,
            tests=all_counts,
            violations=violations,
            duration_seconds=round(all_result.duration_seconds, 3),
            execution=evidence,
            cache=cache_evidence,
            test_evidence=(
                all_result.test_evidence
                if all_result.test_evidence is not None
                else TestCaseEvidence.unavailable("collector_unavailable")
            ),
        )
        safe_stdout = redact_known_paths(all_result.stdout, sensitive_roots)
        safe_stderr = redact_known_paths(all_result.stderr, sensitive_roots)
        result = GradeResult.model_validate(
            redact_value(result.model_dump(mode="json"), sensitive_roots)
        )
        (run_dir / "stdout.txt").write_text(safe_stdout, encoding="utf-8")
        (run_dir / "stderr.txt").write_text(safe_stderr, encoding="utf-8")
        evidence_document = build_evidence(result, created_at, safe_stdout, safe_stderr)
        _write_json(run_dir / "evidence.json", evidence_document.model_dump(mode="json"))
        _write_json(run_dir / "changed_files.json", changed)
        metadata = {
            "schema_version": 1,
            "created_at": created_at.isoformat(),
            "task_fingerprint": fingerprint,
            "command": sanitize_command(all_result.command, sensitive_roots),
            "return_code": all_result.return_code,
            "timed_out": all_result.timed_out,
            "execution": evidence.model_dump(mode="json"),
        }
        if cache_evidence is not None:
            metadata["cache"] = cache_evidence.model_dump(mode="json")
        _write_json(run_dir / "metadata.json", redact_value(metadata, sensitive_roots))
        _write_json(
            run_dir / "result.json",
            redact_value(result.model_dump(mode="json"), sensitive_roots),
        )
    return run_dir

"""Submission grading and run artifact persistence."""

from __future__ import annotations

import json
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from repogym.exceptions import SecurityError, ValidationError
from repogym.executors.base import Executor
from repogym.executors.local import LocalExecutor
from repogym.models import ExecutionEvidence, GradeResult
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


def grade_submission(
    task_directory: Path,
    submission: Path,
    output_root: Path = Path(".repogym/runs"),
    executor: Executor | None = None,
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
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    run_dir = output_root.resolve() / run_id
    run_dir.mkdir(parents=True, exist_ok=False)

    with tempfile.TemporaryDirectory(prefix="repogym-grade-") as temporary:
        workspace = Path(temporary) / "workspace"
        copy_tree_safe(task_directory.resolve() / "starter", workspace)
        original = file_manifest(workspace)
        copy_tree_safe(submission.resolve(), workspace)
        submitted = file_manifest(workspace)
        changed = changed_paths(original, submitted)
        inject_tests(task_directory.resolve(), workspace)
        all_result = run_tests(task, workspace, runner)
        public_result = run_tests(task, workspace, runner, "tests/public")
        all_counts = parse_test_counts(all_result)
        expected_total = task.expected.passing_tests_after
        all_counts.passed = min(all_counts.passed, expected_total)
        all_counts.total = expected_total
        all_counts.failed = expected_total - all_counts.passed
        public_counts = parse_test_counts(public_result)
        dimensions = {
            "correctness": score_correctness(task, all_counts),
            "regression_safety": score_regression(task, public_counts),
            "code_quality": score_quality(task, workspace, changed, runner),
        }
        scope, violations = score_scope(task, changed)
        dimensions["scope_control"] = scope
        status: Literal["completed", "timed_out", "error"] = (
            "timed_out" if all_result.timed_out else "completed"
        )
        if all_result.return_code is None and not all_result.timed_out:
            status = "error"
        score = round(sum(item.score for item in dimensions.values()), 2)
        sensitive_roots = [workspace.resolve(), task_directory.resolve(), submission.resolve()]
        evidence = ExecutionEvidence(
            argv=sanitize_command(all_result.command, sensitive_roots),
            exit_code=all_result.return_code,
            timed_out=all_result.timed_out,
            duration_seconds=round(all_result.duration_seconds, 3),
            working_directory="<WORKSPACE>",
            stdout_file="stdout.txt",
            stderr_file="stderr.txt",
            test_statistics_source="pytest_summary",
            termination_diagnostics=all_result.termination_diagnostics,
        )
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
        )
        safe_stdout = redact_known_paths(all_result.stdout, sensitive_roots)
        safe_stderr = redact_known_paths(all_result.stderr, sensitive_roots)
        (run_dir / "stdout.txt").write_text(safe_stdout, encoding="utf-8")
        (run_dir / "stderr.txt").write_text(safe_stderr, encoding="utf-8")
        _write_json(run_dir / "changed_files.json", changed)
        metadata = {
            "schema_version": 1,
            "created_at": datetime.now(UTC).isoformat(),
            "task_fingerprint": fingerprint,
            "command": sanitize_command(all_result.command, sensitive_roots),
            "return_code": all_result.return_code,
            "timed_out": all_result.timed_out,
            "execution": evidence.model_dump(mode="json"),
        }
        _write_json(run_dir / "metadata.json", redact_value(metadata, sensitive_roots))
        _write_json(
            run_dir / "result.json",
            redact_value(result.model_dump(mode="json"), sensitive_roots),
        )
    return run_dir

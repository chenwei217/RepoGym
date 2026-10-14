"""Helpers shared by verification and grading."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

# Element is imported only for typing; runtime parsing uses defusedxml below.
from xml.etree.ElementTree import Element  # nosec B405

from defusedxml import ElementTree as ET
from defusedxml.common import DefusedXmlException

from repogym.commands import resolve_command
from repogym.executors.base import CancellationToken, Executor
from repogym.models import (
    ExecutionResult,
    TaskSpec,
    TestCaseEvidence,
    TestCaseResult,
    TestCounts,
)
from repogym.security import copy_tree_safe, redact_sensitive_text, safe_join

COUNT_PATTERNS = {
    "passed": re.compile(r"(\d+) passed"),
    "failed": re.compile(r"(\d+) failed"),
    "errors": re.compile(r"(\d+) errors?"),
}
_LONG_OPAQUE_VALUE = re.compile(
    r"(?<![\w])(?=[A-Za-z0-9._-]{24,}(?![\w]))[A-Za-z0-9._-]*[0-9][A-Za-z0-9._-]*"
)
_FAILURE_SUMMARY_LIMIT = 500
_JUNIT_NAME = ".repogym-pytest-results.xml"


def inject_tests(task_directory: Path, workspace: Path) -> None:
    copy_tree_safe(task_directory / "tests" / "public", workspace / "tests" / "public")
    copy_tree_safe(task_directory / "tests" / "private", workspace / "tests" / "private")


def parse_test_counts(result: ExecutionResult) -> TestCounts:
    evidence = result.test_evidence
    if evidence is not None and evidence.availability == "available":
        passed = sum(case.status == "passed" for case in evidence.cases)
        failed = sum(case.status in {"failed", "error"} for case in evidence.cases)
        return TestCounts(passed=passed, failed=failed, total=len(evidence.cases))
    combined = f"{result.stdout}\n{result.stderr}"
    values: dict[str, int] = {}
    for name, pattern in COUNT_PATTERNS.items():
        matches = pattern.findall(combined)
        values[name] = int(matches[-1]) if matches else 0
    failed = values["failed"] + values["errors"]
    return TestCounts(passed=values["passed"], failed=failed, total=values["passed"] + failed)


def _is_pytest_command(command: list[str]) -> bool:
    executable = Path(command[0]).name.casefold()
    if executable in {"pytest", "pytest.exe", "py.test", "py.test.exe"}:
        return True
    return len(command) >= 3 and command[1:3] == ["-m", "pytest"]


def _safe_failure_summary(text: str, roots: list[Path]) -> str:
    summary = " ".join(text.split())
    summary = redact_sensitive_text(summary, roots)
    summary = _LONG_OPAQUE_VALUE.sub("<REDACTED>", summary)
    if len(summary) > _FAILURE_SUMMARY_LIMIT:
        summary = summary[: _FAILURE_SUMMARY_LIMIT - 3] + "..."
    return summary


def _test_case_id(element: Element, roots: list[Path]) -> str:
    classname = element.attrib.get("classname") or element.attrib.get("file") or "pytest"
    name = element.attrib.get("name") or "unnamed"
    return redact_sensitive_text(f"{classname}::{name}", roots).replace("\\", "/")


def parse_pytest_junit(path: Path, workspace: Path) -> TestCaseEvidence:
    """Parse pytest JUnit output without retaining raw per-test captured output."""
    if not path.is_file():
        return TestCaseEvidence.unavailable("structured_output_missing")
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError, DefusedXmlException):
        return TestCaseEvidence.unavailable("structured_output_invalid")
    if root is None:
        return TestCaseEvidence.unavailable("structured_output_invalid")
    pending: list[
        tuple[
            str,
            Literal["passed", "failed", "error", "skipped"],
            float,
            str | None,
            list[Literal["stdout.txt", "stderr.txt"]],
        ]
    ] = []
    roots = [workspace.resolve()]
    for element in root.iter("testcase"):
        status: Literal["passed", "failed", "error", "skipped"] = "passed"
        outcome = element.find("failure")
        if outcome is not None:
            status = "failed"
        else:
            outcome = element.find("error")
            if outcome is not None:
                status = "error"
            elif element.find("skipped") is not None:
                status = "skipped"
        try:
            duration = max(float(element.attrib.get("time", "0")), 0.0)
        except ValueError:
            duration = 0.0
        summary = None
        if outcome is not None:
            raw_summary = outcome.attrib.get("message") or outcome.text or status
            summary = _safe_failure_summary(raw_summary, roots)
        refs: list[Literal["stdout.txt", "stderr.txt"]] = (
            ["stdout.txt", "stderr.txt"] if status in {"failed", "error"} else []
        )
        pending.append((_test_case_id(element, roots), status, duration, summary, refs))
    pending.sort(key=lambda item: (item[0], item[1], item[2], item[3] or ""))
    totals: dict[str, int] = {}
    cases: list[TestCaseResult] = []
    for base_id, status, duration, summary, refs in pending:
        totals[base_id] = totals.get(base_id, 0) + 1
        suffix = f"#{totals[base_id]}" if totals[base_id] > 1 else ""
        cases.append(
            TestCaseResult(
                id=base_id + suffix,
                status=status,
                duration_seconds=round(duration, 6),
                failure_summary=summary,
                output_refs=refs,
            )
        )
    cases.sort(key=lambda case: case.id)
    return TestCaseEvidence(
        availability="available",
        source="pytest_junit",
        reason="collected",
        cases=cases,
    )


def run_tests(
    task: TaskSpec,
    workspace: Path,
    executor: Executor,
    selection: str | None = None,
    cancellation_token: CancellationToken | None = None,
) -> ExecutionResult:
    command = resolve_command(task.execution.test_command)
    if selection is not None:
        command.append(selection)
    cwd = safe_join(workspace, task.execution.working_directory)
    structured_path = workspace / _JUNIT_NAME
    collect_structured = _is_pytest_command(command)
    if collect_structured:
        command.append(f"--junitxml={structured_path}")
    if cancellation_token is None:
        result = executor.execute(command, cwd, task.execution.timeout_seconds)
    else:
        result = executor.execute(
            command,
            cwd,
            task.execution.timeout_seconds,
            cancellation_token=cancellation_token,
        )
    if result.timed_out:
        result.test_evidence = TestCaseEvidence.unavailable("execution_timed_out")
    elif result.cancelled:
        result.test_evidence = TestCaseEvidence.unavailable("execution_cancelled")
    elif not collect_structured:
        result.test_evidence = TestCaseEvidence.unavailable("unsupported_test_command")
    else:
        result.test_evidence = parse_pytest_junit(structured_path, workspace)
    return result

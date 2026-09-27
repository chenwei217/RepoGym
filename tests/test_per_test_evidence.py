from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path

from rich.console import Console

from repogym.grader import grade_submission
from repogym.loader import load_task
from repogym.models import (
    DimensionResult,
    ExecutionResult,
    GradeResult,
)
from repogym.models import (
    TestCaseEvidence as CaseEvidence,
)
from repogym.models import (
    TestCaseResult as CaseResult,
)
from repogym.models import (
    TestCounts as Counts,
)
from repogym.reports import generate_report, load_run, render_junit, render_terminal
from repogym.testing import parse_pytest_junit, parse_test_counts, run_tests

ROOT = Path(__file__).parents[1]


def _available_evidence() -> CaseEvidence:
    return CaseEvidence(
        availability="available",
        source="pytest_junit",
        reason="collected",
        cases=[
            CaseResult(
                id="tests.test_api::test_error",
                status="error",
                duration_seconds=0.04,
                failure_summary="setup failed",
                output_refs=["stdout.txt", "stderr.txt"],
            ),
            CaseResult(
                id="tests.test_api::test_failure",
                status="failed",
                duration_seconds=0.03,
                failure_summary="<unsafe & failure>",
                output_refs=["stdout.txt", "stderr.txt"],
            ),
            CaseResult(
                id="tests.test_api::test_pass",
                status="passed",
                duration_seconds=0.01,
            ),
            CaseResult(
                id="tests.test_api::test_skip",
                status="skipped",
                duration_seconds=0.02,
            ),
        ],
    )


def _result(evidence: CaseEvidence) -> GradeResult:
    return GradeResult(
        task_id="sample-task",
        run_id="run-1",
        status="completed",
        score=50,
        dimensions={"correctness": DimensionResult(score=30, max_score=60, reason="fixture")},
        tests=Counts(passed=1, failed=2, total=4),
        violations=[],
        duration_seconds=0.2,
        test_evidence=evidence,
    )


def _write_run(path: Path, result: GradeResult) -> Path:
    path.mkdir()
    (path / "result.json").write_text(result.model_dump_json(), encoding="utf-8")
    (path / "stdout.txt").write_text("", encoding="utf-8")
    (path / "stderr.txt").write_text("", encoding="utf-8")
    return path


def test_parse_pytest_junit_is_sorted_bounded_and_sanitized(tmp_path: Path) -> None:
    private_path = tmp_path / "private" / "test_secret.py"
    secret = "not-a-real-credential-123456789"
    report = tmp_path / "pytest.xml"
    report.write_text(
        f"""<testsuites><testsuite>
        <testcase classname="tests.test_api" name="test_skip" time="0.02">
          <skipped />
        </testcase>
        <testcase classname="tests.test_api" name="test_failure" time="0.03">
          <failure message="at {private_path} api_key={secret}">{"x" * 700}</failure>
          <system-out>raw secret output</system-out>
        </testcase>
        <testcase classname="tests.test_api" name="test_pass" time="bad" />
        <testcase classname="tests.test_api" name="test_failure" time="-1">
          <error message="duplicate" />
        </testcase>
        </testsuite></testsuites>""",
        encoding="utf-8",
    )

    evidence = parse_pytest_junit(report, tmp_path)

    assert evidence.availability == "available"
    assert [case.id for case in evidence.cases] == [
        "tests.test_api::test_failure",
        "tests.test_api::test_failure#2",
        "tests.test_api::test_pass",
        "tests.test_api::test_skip",
    ]
    assert [case.status for case in evidence.cases] == [
        "error",
        "failed",
        "passed",
        "skipped",
    ]
    encoded = evidence.model_dump_json()
    assert str(tmp_path) not in encoded
    assert secret not in encoded
    assert "raw secret output" not in encoded
    assert all(len(case.failure_summary or "") <= 500 for case in evidence.cases)
    assert evidence.cases[0].duration_seconds == 0


def test_parse_pytest_junit_reports_missing_and_invalid_artifacts(tmp_path: Path) -> None:
    assert parse_pytest_junit(tmp_path / "missing.xml", tmp_path).reason == (
        "structured_output_missing"
    )
    invalid = tmp_path / "invalid.xml"
    invalid.write_text("<broken", encoding="utf-8")
    assert parse_pytest_junit(invalid, tmp_path).reason == "structured_output_invalid"


def test_structured_counts_include_errors_but_not_skips() -> None:
    result = ExecutionResult(
        command=["pytest"],
        return_code=1,
        stdout="misleading 99 passed",
        stderr="",
        duration_seconds=0.1,
        test_evidence=_available_evidence(),
    )

    assert parse_test_counts(result) == Counts(passed=1, failed=2, total=4)


def test_terminal_html_json_and_junit_render_real_test_cases(tmp_path: Path) -> None:
    result = _result(_available_evidence())
    console = Console(record=True, width=160)
    render_terminal(result, console)
    assert "tests.test_api::test_failure" in console.export_text()

    run = _write_run(tmp_path / "run", result)
    json_report = generate_report(run, "json")
    html_report = generate_report(run, "html")
    junit_report = render_junit(result)
    assert json_report is not None and "tests.test_api::test_failure" in json_report
    assert html_report is not None and "tests.test_api::test_pass" in html_report
    assert "&lt;unsafe &amp; failure&gt;" in html_report

    suite = ET.fromstring(junit_report)
    assert suite.attrib["tests"] == "4"
    assert suite.attrib["failures"] == "1"
    assert suite.attrib["errors"] == "1"
    assert suite.attrib["skipped"] == "1"
    cases = suite.findall("testcase")
    assert [case.attrib["name"] for case in cases] == [
        "test_error",
        "test_failure",
        "test_pass",
        "test_skip",
    ]
    assert cases[0].find("error") is not None
    assert cases[1].find("failure") is not None
    assert cases[3].find("skipped") is not None


def test_load_run_marks_old_artifacts_as_legacy(tmp_path: Path) -> None:
    raw = _result(_available_evidence()).model_dump(mode="json")
    raw.pop("test_evidence")
    run = tmp_path / "old-run"
    run.mkdir()
    (run / "result.json").write_text(json.dumps(raw), encoding="utf-8")
    (run / "stdout.txt").write_text("", encoding="utf-8")
    (run / "stderr.txt").write_text("", encoding="utf-8")

    loaded, _, _ = load_run(run)

    assert loaded.test_evidence.availability == "unavailable"
    assert loaded.test_evidence.reason == "legacy_run"


def test_repeated_grades_have_stable_test_ids(tmp_path: Path) -> None:
    run_a = grade_submission(
        ROOT / "tasks" / "python-cache-ttl",
        ROOT / "examples" / "submissions" / "cache-ttl-fixed",
        tmp_path / "runs-a",
    )
    run_b = grade_submission(
        ROOT / "tasks" / "python-cache-ttl",
        ROOT / "examples" / "submissions" / "cache-ttl-fixed",
        tmp_path / "runs-b",
    )

    result_a, _, _ = load_run(run_a)
    result_b, _, _ = load_run(run_b)
    ids_a = [case.id for case in result_a.test_evidence.cases]
    ids_b = [case.id for case in result_b.test_evidence.cases]

    assert result_a.test_evidence.availability == "available"
    assert result_b.test_evidence.availability == "available"
    assert ids_a == ids_b == sorted(ids_a)
    assert len(ids_a) == 8


class _TimeoutExecutor:
    def execute(
        self,
        command: list[str],
        cwd: Path,
        timeout_seconds: int,
    ) -> ExecutionResult:
        return ExecutionResult(
            command=command,
            return_code=None,
            stdout="",
            stderr="",
            duration_seconds=float(timeout_seconds),
            timed_out=True,
        )


def test_timed_out_pytest_marks_per_test_results_unavailable(
    valid_task: Path, tmp_path: Path
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    result = run_tests(load_task(valid_task), workspace, _TimeoutExecutor())

    assert result.test_evidence is not None
    assert result.test_evidence.availability == "unavailable"
    assert result.test_evidence.reason == "execution_timed_out"

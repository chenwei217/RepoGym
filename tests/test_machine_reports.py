from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path

from typer.testing import CliRunner

from repogym.cli import app
from repogym.models import DimensionResult, GradeResult
from repogym.models import TestCounts as Counts
from repogym.reports import generate_report, render_junit, render_sarif


def _result(*, tests: Counts, violations: list[str] | None = None) -> GradeResult:
    return GradeResult(
        task_id="report-contract<&",
        task_fingerprint="a" * 64,
        run_id="run-1",
        status="completed",
        score=75,
        dimensions={"correctness": DimensionResult(score=45, max_score=60, reason="stable")},
        tests=tests,
        violations=violations or [],
        duration_seconds=1.2346,
    )


def _write_run(path: Path, result: GradeResult) -> Path:
    path.mkdir()
    (path / "result.json").write_text(result.model_dump_json(), encoding="utf-8")
    (path / "stdout.txt").write_text("", encoding="utf-8")
    (path / "stderr.txt").write_text("", encoding="utf-8")
    return path


def test_junit_contract_includes_failures_skips_time_and_escaping() -> None:
    rendered = render_junit(_result(tests=Counts(passed=2, failed=1, total=4)))
    suite = ET.fromstring(rendered)

    assert suite.attrib == {
        "name": "report-contract<&",
        "tests": "4",
        "failures": "1",
        "errors": "0",
        "skipped": "1",
        "time": "1.235",
    }
    cases = suite.findall("testcase")
    assert [case.attrib["name"] for case in cases] == [
        "passed-1",
        "passed-2",
        "failed-1",
        "skipped-1",
    ]
    assert cases[2].find("failure") is not None
    assert cases[3].find("skipped") is not None
    assert "report-contract&lt;&amp;" in rendered


def test_junit_empty_result_is_valid() -> None:
    suite = ET.fromstring(render_junit(_result(tests=Counts())))

    assert suite.attrib["tests"] == "0"
    assert suite.findall("testcase") == []


def test_sarif_contract_is_sorted_located_and_deterministic() -> None:
    result = _result(
        tests=Counts(passed=1, total=1),
        violations=[
            "Path outside allowed scope: docs/note.md:9",
            r"Forbidden path modified: config\secret.toml",
        ],
    )

    first = render_sarif(result)
    assert first == render_sarif(result)
    document = json.loads(first)
    assert document["version"] == "2.1.0"
    assert document["$schema"].endswith("sarif-2.1.0.json")
    driver = document["runs"][0]["tool"]["driver"]
    assert driver["name"] == "RepoGym"
    assert [rule["id"] for rule in driver["rules"]] == [
        "repogym/forbidden-path",
        "repogym/scope",
    ]
    results = document["runs"][0]["results"]
    assert [item["ruleId"] for item in results] == [
        "repogym/forbidden-path",
        "repogym/scope",
    ]
    first_location = results[0]["locations"][0]["physicalLocation"]
    assert first_location["artifactLocation"]["uri"] == "config/secret.toml"
    second_location = results[1]["locations"][0]["physicalLocation"]
    assert second_location["artifactLocation"]["uri"] == "docs/note.md"
    assert second_location["region"] == {"startLine": 9}


def test_sarif_empty_result_and_direct_rendering_redact_paths() -> None:
    empty = json.loads(render_sarif(_result(tests=Counts())))
    assert empty["runs"][0]["results"] == []

    private = r"C:\Users\alice\private.py"
    rendered = render_sarif(
        _result(
            tests=Counts(),
            violations=[f"Forbidden path modified: {private}"],
        )
    )
    assert private not in rendered
    assert "<ABSOLUTE_PATH>" in rendered


def test_generate_and_cli_write_machine_reports(tmp_path: Path) -> None:
    run = _write_run(
        tmp_path / "run",
        _result(tests=Counts(passed=1, failed=1, total=2)),
    )
    junit_path = tmp_path / "report.xml"
    sarif_path = tmp_path / "report.sarif"

    junit = generate_report(run, "junit", junit_path)
    sarif = generate_report(run, "sarif", sarif_path)
    assert junit_path.read_text(encoding="utf-8") == junit
    assert sarif_path.read_text(encoding="utf-8") == sarif

    runner = CliRunner()
    stdout_report = runner.invoke(app, ["report", str(run), "--format", "junit"])
    file_report = runner.invoke(
        app,
        ["report", str(run), "--format", "sarif", "--output", str(sarif_path)],
    )
    assert stdout_report.exit_code == 0
    assert "<testsuite" in stdout_report.stdout
    assert file_report.exit_code == 0
    assert "Report written" in file_report.stdout

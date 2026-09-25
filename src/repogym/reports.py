"""Terminal, JSON, and self-contained HTML reports."""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Literal

from jinja2 import Environment, PackageLoader
from rich.console import Console
from rich.table import Table

from repogym.exceptions import ReportError
from repogym.models import GradeResult
from repogym.security import redact_sensitive_text, redact_value


def load_run(run_directory: Path) -> tuple[GradeResult, str, str]:
    try:
        raw: Any = json.loads((run_directory / "result.json").read_text(encoding="utf-8"))
        roots = [run_directory.resolve()]
        result = GradeResult.model_validate(redact_value(raw, roots))
        stdout = redact_sensitive_text(
            (run_directory / "stdout.txt").read_text(encoding="utf-8"), roots
        )
        stderr = redact_sensitive_text(
            (run_directory / "stderr.txt").read_text(encoding="utf-8"), roots
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise ReportError(f"Invalid run directory {run_directory}: {exc}") from exc
    return result, stdout, stderr


def render_terminal(result: GradeResult, console: Console) -> None:
    console.print(f"[bold]{result.task_id}[/bold] - score [bold]{result.score:.2f}/100[/bold]")
    table = Table("Dimension", "Score", "Reason")
    for name, dimension in result.dimensions.items():
        table.add_row(name, f"{dimension.score:.2f}/{dimension.max_score}", dimension.reason)
    console.print(table)
    console.print(
        f"Tests: {result.tests.passed} passed, {result.tests.failed} failed; "
        f"status: {result.status}; duration: {result.duration_seconds:.3f}s"
    )
    if result.cache is not None:
        state = "hit" if result.cache.hit else "miss"
        console.print(f"Cache: {state} ({result.cache.key[:12]})")
    if result.violations:
        console.print("[yellow]Violations:[/yellow]")
        for violation in result.violations:
            console.print(f"  - {violation}")


def render_junit(result: GradeResult) -> str:
    """Render aggregate test counts as deterministic JUnit XML."""
    skipped = max(result.tests.total - result.tests.passed - result.tests.failed, 0)
    suite = ET.Element(
        "testsuite",
        {
            "name": result.task_id,
            "tests": str(result.tests.total),
            "failures": str(result.tests.failed),
            "errors": "0",
            "skipped": str(skipped),
            "time": f"{result.duration_seconds:.3f}",
        },
    )
    for index in range(result.tests.passed):
        ET.SubElement(
            suite,
            "testcase",
            {"classname": result.task_id, "name": f"passed-{index + 1}"},
        )
    for index in range(result.tests.failed):
        case = ET.SubElement(
            suite,
            "testcase",
            {"classname": result.task_id, "name": f"failed-{index + 1}"},
        )
        failure = ET.SubElement(case, "failure", {"message": "Task test failed"})
        failure.text = "See the sanitized stdout and stderr run artifacts."
    for index in range(skipped):
        case = ET.SubElement(
            suite,
            "testcase",
            {"classname": result.task_id, "name": f"skipped-{index + 1}"},
        )
        ET.SubElement(case, "skipped", {"message": "No outcome was recorded"})
    ET.indent(suite, space="  ")
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        + ET.tostring(suite, encoding="unicode", short_empty_elements=True)
        + "\n"
    )


def _violation_location(message: str) -> tuple[str, int | None] | None:
    match = re.search(r"(?:modified|scope):\s+([^:\n]+?)(?::(\d+))?$", message)
    if match is None:
        return None
    path = match.group(1).replace("\\", "/")
    return path, int(match.group(2)) if match.group(2) else None


def render_sarif(result: GradeResult) -> str:
    """Render scope violations as a deterministic SARIF 2.1.0 log."""
    results: list[dict[str, object]] = []
    violations = sorted(redact_sensitive_text(item) for item in result.violations)
    for violation in violations:
        rule_id = "repogym/forbidden-path" if violation.startswith("Forbidden") else "repogym/scope"
        item: dict[str, object] = {
            "ruleId": rule_id,
            "level": "error" if rule_id.endswith("forbidden-path") else "warning",
            "message": {"text": violation},
        }
        location = _violation_location(violation)
        if location is not None:
            path, line = location
            physical: dict[str, object] = {"artifactLocation": {"uri": path}}
            if line is not None:
                physical["region"] = {"startLine": line}
            item["locations"] = [{"physicalLocation": physical}]
        results.append(item)
    log = {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "RepoGym",
                        "informationUri": "https://github.com/chenwei217/RepoGym",
                        "rules": [
                            {"id": "repogym/forbidden-path", "name": "ForbiddenPath"},
                            {"id": "repogym/scope", "name": "ScopeControl"},
                        ],
                    }
                },
                "results": results,
            }
        ],
    }
    return json.dumps(log, indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def generate_report(
    run_directory: Path,
    format_name: Literal["terminal", "json", "html", "junit", "sarif"],
    output: Path | None = None,
    console: Console | None = None,
) -> str | None:
    result, stdout, stderr = load_run(run_directory)
    if format_name == "terminal":
        render_terminal(result, console or Console())
        return None
    if format_name == "json":
        rendered = json.dumps(result.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n"
    elif format_name == "html":
        environment = Environment(
            loader=PackageLoader("repogym", "templates"),
            autoescape=True,
        )
        rendered = environment.get_template("report.html.j2").render(
            result=result, stdout=stdout, stderr=stderr
        )
    elif format_name == "junit":
        rendered = render_junit(result)
    else:
        rendered = render_sarif(result)
    if output is not None:
        output.write_text(rendered, encoding="utf-8")
    return rendered

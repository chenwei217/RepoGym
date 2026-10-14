"""Terminal, JSON and escaped self-contained HTML analysis reports."""

import json
from io import StringIO
from typing import Literal

from jinja2 import Environment
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from repogym.analytics.models import AnalysisReport

_HTML = """<!doctype html>
<html lang="en"><meta charset="utf-8"><title>RepoGym repeat-run analysis</title>
<style>body{font:16px system-ui;max-width:1100px;margin:2rem auto;padding:1rem}
table{border-collapse:collapse}td,th{padding:.5rem;border:1px solid #aaa;text-align:left}</style>
<h1>Repeat-run analysis</h1>
<p>Observed variation is not proof of randomness. Cohorts have equal recorded task, candidate and
environment identities. Cache and incomplete executions never contribute duration samples.</p>
{% for group in report.cohorts %}<h2>{{ group.task_id }}</h2>
<p>{{ group.run_count }} runs; perfect score rate {{ group.perfect_score_rate }};
candidate {{ group.candidate_fingerprint }}; environment {{ group.environment_fingerprint }}</p>
{% if group.duration_seconds %}<p>Median {{ group.duration_seconds.median }}s;
p95 {{ group.duration_seconds.p95 }}s</p>{% endif %}
<table><tr><th>Test</th><th>Classification</th><th>Passed</th><th>Failed/error</th>
<th>Skipped</th><th>Missing</th></tr>{% for case in group.cases %}<tr>
<td>{{ case.id }}</td><td>{{ case.classification }}</td><td>{{ case.passed }}</td>
<td>{{ case.failed + case.error }}</td><td>{{ case.skipped }}</td><td>{{ case.missing }}</td>
</tr>{% endfor %}</table>{% for warning in group.warnings %}<p>{{ warning }}</p>{% endfor %}
{% endfor %}<h2>Excluded observations</h2>{% for issue in report.excluded %}
<p>{{ issue.run_id }}: {{ issue.code }}</p>{% endfor %}</html>"""


def render_analysis(
    report: AnalysisReport, format_name: Literal["terminal", "json", "html"]
) -> str:
    if format_name == "json":
        return (
            json.dumps(report.model_dump(mode="json"), sort_keys=True, indent=2, ensure_ascii=False)
            + "\n"
        )
    if format_name == "html":
        return Environment(autoescape=True).from_string(_HTML).render(report=report)
    stream = StringIO()
    console = Console(file=stream, width=120, color_system=None)
    for cohort in report.cohorts:
        console.print(
            f"{escape(cohort.task_id)}: {cohort.run_count} run(s), "
            f"perfect score rate {cohort.perfect_score_rate:.1%}"
        )
        if cohort.duration_seconds is not None:
            console.print(
                f"Duration median {cohort.duration_seconds.median:.6f}s; "
                f"p95 {cohort.duration_seconds.p95:.6f}s"
            )
        table = Table("Test", "State", "Passed", "Failed/error", "Skipped", "Missing")
        for case in cohort.cases:
            table.add_row(
                escape(case.id),
                case.classification,
                str(case.passed),
                str(case.failed + case.error),
                str(case.skipped),
                str(case.missing),
            )
        console.print(table)
        for warning in cohort.warnings:
            console.print(warning)
    for issue in report.excluded:
        console.print(f"Excluded {escape(issue.run_id)}: {issue.code}")
    return stream.getvalue()

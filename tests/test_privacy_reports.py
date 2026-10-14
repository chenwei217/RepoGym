from collections.abc import Callable
from pathlib import Path

from rich.console import Console

from repogym.grader import grade_submission
from repogym.models import ExecutionResult
from repogym.reports import generate_report, load_run


def test_legacy_reports_filter_raw_output_and_nested_values(
    run_factory: Callable[..., Path],
) -> None:
    marker = "fixture" + "credential42"
    run = run_factory(
        violations=[f"api_key={marker}"],
        dimensions={"correctness": {"score": 0, "max_score": 100, "reason": f"Bearer {marker}"}},
    )
    (run / "stdout.txt").write_text(f"password='{marker}'", encoding="utf-8")
    (run / "stderr.txt").write_text(f"Authorization: Basic {marker}", encoding="utf-8")
    result, stdout, stderr = load_run(run)
    assert marker not in result.model_dump_json() + stdout + stderr
    for format_name in ("json", "html", "junit", "sarif"):
        rendered = generate_report(run, format_name)
        assert rendered is not None
        assert marker not in rendered
    console = Console(record=True)
    generate_report(run, "terminal", console=console)
    assert marker not in console.export_text()


def test_new_grade_never_persists_recognized_credentials(valid_task: Path, tmp_path: Path) -> None:
    marker = "fixture" + "credential42"

    class DiagnosticExecutor:
        def execute(self, command: list[str], cwd: Path, timeout_seconds: int) -> ExecutionResult:
            return ExecutionResult(
                command=command,
                return_code=0,
                stdout=f"2 passed\napi_key={marker}",
                stderr=f"Bearer {marker}",
                duration_seconds=0.1,
            )

    submission = tmp_path / "submission"
    submission.mkdir()
    run = grade_submission(valid_task, submission, tmp_path / "output", DiagnosticExecutor())
    for artifact in run.iterdir():
        assert marker not in artifact.read_text(encoding="utf-8")

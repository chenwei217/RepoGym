from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

import repogym.authoring as authoring_module
from repogym.authoring import lint_task, scaffold_task
from repogym.cli import app
from repogym.exceptions import AuthoringError
from repogym.validator import ValidationReport, validate_task

ROOT = Path(__file__).parents[1]


def test_scaffold_creates_a_structurally_valid_cross_platform_task(tmp_path: Path) -> None:
    tasks = tmp_path / "tasks with spaces"

    task = scaffold_task(tasks, "sample-windows-path", "Sample task")

    assert task == tasks.resolve() / "sample-windows-path"
    assert validate_task(task).valid
    assert (task / "task.yaml").is_file()
    assert (task / "prompt.md").is_file()
    assert (task / "starter" / "sample_windows_path" / "solution.py").is_file()
    assert (task / "tests" / "public" / "test_solution.py").is_file()
    assert (task / "tests" / "private" / "test_solution.py").is_file()
    assert (task / "reference" / "solution.patch").is_file()
    report = lint_task(task)
    assert report.valid
    assert [item.code for item in report.diagnostics] == [
        "placeholder-description",
        "placeholder-reference",
        "placeholder-tests",
    ]


def test_non_interactive_cli_creates_and_immediately_validates(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        app,
        [
            "init-task",
            "cli-task",
            "--title",
            "CLI task",
            "--tasks-dir",
            str(tmp_path),
            "--non-interactive",
        ],
    )

    assert result.exit_code == 0
    assert "Created" in result.stdout
    assert "WARN (placeholder-description)" in result.stdout
    assert "Replace the TODO prompt" in result.stdout
    assert validate_task(tmp_path / "cli-task").valid


def test_interactive_cli_prompts_for_missing_values(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        app,
        ["init-task", "--tasks-dir", str(tmp_path)],
        input="interactive-task\nInteractive task\n",
    )

    assert result.exit_code == 0
    assert "Task ID" in result.stdout
    assert "Task title" in result.stdout
    assert (tmp_path / "interactive-task" / "task.yaml").is_file()


def test_non_interactive_cli_requires_id_and_title(tmp_path: Path) -> None:
    missing_id = CliRunner().invoke(
        app,
        [
            "init-task",
            "--title",
            "Missing ID",
            "--tasks-dir",
            str(tmp_path),
            "--non-interactive",
        ],
    )
    missing_title = CliRunner().invoke(
        app,
        [
            "init-task",
            "missing-title",
            "--tasks-dir",
            str(tmp_path),
            "--non-interactive",
        ],
    )

    assert missing_id.exit_code == 10
    assert missing_title.exit_code == 10
    assert "--non-interactive requires" in missing_id.stderr
    assert "--non-interactive requires" in missing_title.stderr


@pytest.mark.parametrize(
    "task_id",
    ["Uppercase", "two--hyphens", "../escape", "nested/task", r"nested\task"],
)
def test_scaffold_rejects_invalid_ids_and_path_escape(tmp_path: Path, task_id: str) -> None:
    with pytest.raises(AuthoringError, match="Invalid task id"):
        scaffold_task(tmp_path / "tasks", task_id, "Unsafe")

    assert not (tmp_path / "escape").exists()
    assert not (tmp_path / "tasks" / "nested").exists()


def test_scaffold_never_overwrites_existing_directory(tmp_path: Path) -> None:
    tasks = tmp_path / "tasks"
    existing = tasks / "existing-task"
    existing.mkdir(parents=True)
    marker = existing / "keep.txt"
    marker.write_text("user data", encoding="utf-8")

    with pytest.raises(AuthoringError, match="already exists"):
        scaffold_task(tasks, "existing-task", "Existing")

    assert marker.read_text(encoding="utf-8") == "user data"


def test_scaffold_handles_a_concurrent_target_without_overwriting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tasks = tmp_path / "tasks"
    real_rename = authoring_module.os.rename

    def conflicting_rename(source: Path, target: Path) -> None:
        target.mkdir()
        (target / "keep.txt").write_text("concurrent data", encoding="utf-8")
        raise FileExistsError(target)

    monkeypatch.setattr(authoring_module.os, "rename", conflicting_rename)
    with pytest.raises(AuthoringError, match="already exists"):
        scaffold_task(tasks, "racing-task", "Racing")
    monkeypatch.setattr(authoring_module.os, "rename", real_rename)

    assert (tasks / "racing-task" / "keep.txt").read_text(encoding="utf-8") == ("concurrent data")
    assert [path.name for path in tasks.iterdir()] == ["racing-task"]


def test_scaffold_cleans_staging_directory_after_validation_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tasks = tmp_path / "tasks"
    monkeypatch.setattr(
        authoring_module,
        "validate_task",
        lambda path: ValidationReport(None, [], ["fixture failure"]),
    )

    with pytest.raises(AuthoringError, match="fixture failure"):
        scaffold_task(tasks, "broken-task", "Broken")

    assert list(tasks.iterdir()) == []


def test_lint_reports_empty_reference_and_expected_count_conflicts(
    tmp_path: Path,
) -> None:
    task = scaffold_task(tmp_path, "lint-errors", "Lint errors")
    (task / "reference" / "solution.patch").write_text("", encoding="utf-8")
    config = task / "task.yaml"
    config.write_text(
        config.read_text(encoding="utf-8").replace(
            "passing_tests_after: 2", "passing_tests_after: 1"
        ),
        encoding="utf-8",
    )

    report = lint_task(task)

    assert not report.valid
    assert [item.code for item in report.diagnostics if item.status == "error"] == [
        "empty-reference",
        "failure-count-conflict",
        "test-count-mismatch",
    ]


def test_lint_reuses_validation_for_empty_test_files(tmp_path: Path) -> None:
    task = scaffold_task(tmp_path, "empty-tests", "Empty tests")
    (task / "tests" / "public" / "test_solution.py").write_text("", encoding="utf-8")

    report = lint_task(task)

    assert not report.valid
    assert "No public test files matching test_*.py" in report.validation.errors


def test_lint_reports_risky_commands_and_scope(tmp_path: Path) -> None:
    task = scaffold_task(tmp_path, "risky-task", "Risky")
    config = task / "task.yaml"
    text = config.read_text(encoding="utf-8")
    text = text.replace("python -m pytest -q", "bash -c /tmp/run-tests --maxfail=1")
    text = text.replace("- risky_task/**\n  - tests/**", "- '**'")
    config.write_text(text, encoding="utf-8")

    report = lint_task(task)
    codes = [item.code for item in report.diagnostics]

    assert "absolute-command-path" in codes
    assert "incomplete-test-run" in codes
    assert "shell-command" in codes
    assert "unbounded-scope" in codes


def test_lint_cli_returns_stable_error_for_empty_description(tmp_path: Path) -> None:
    task = scaffold_task(tmp_path, "empty-description", "Empty")
    (task / "prompt.md").write_text("", encoding="utf-8")

    result = CliRunner().invoke(app, ["lint-task", str(task)])

    assert result.exit_code == 10
    assert "FAIL (empty-description) Task description is empty." in result.stderr


def test_lint_cli_reports_success_with_template_warnings(tmp_path: Path) -> None:
    task = scaffold_task(tmp_path, "warning-task", "Warnings")

    result = CliRunner().invoke(app, ["lint-task", str(task)])

    assert result.exit_code == 0
    assert "Author lint completed with 3 warning(s)." in result.stdout


@pytest.mark.parametrize("task_name", ["python-cache-ttl", "python-config-merge"])
def test_existing_tasks_pass_author_lint(task_name: str) -> None:
    report = lint_task(ROOT / "tasks" / task_name)

    assert report.valid
    assert report.diagnostics == []

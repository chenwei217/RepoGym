from __future__ import annotations

import re
import shlex
from pathlib import Path

import pytest
import yaml

from repogym.ci_smoke import SmokeError, run_smoke
from repogym.exit_codes import ExitCode

ROOT = Path(__file__).parents[1]
_BASH_BLOCK = re.compile(r"```bash\s*\n(?P<commands>.*?)```", re.DOTALL)
_ACTION_SHA = re.compile(r"^[^@]+@[0-9a-f]{40}$")


def _assert_checkout_path_matches(commands: str) -> None:
    lines = [line.strip() for line in commands.splitlines() if line.strip()]
    clone_index = next(
        (index for index, line in enumerate(lines) if line.startswith("git clone ")),
        None,
    )
    if clone_index is None:
        raise AssertionError("Quick Start must contain a git clone command")
    clone = shlex.split(lines[clone_index], posix=True)
    if len(clone) not in {3, 4}:
        raise AssertionError("git clone must use a URL and optional target directory")
    if clone_index + 1 >= len(lines):
        raise AssertionError("git clone must be followed by cd")
    change_directory = shlex.split(lines[clone_index + 1], posix=True)
    if len(change_directory) != 2 or change_directory[0] != "cd":
        raise AssertionError("git clone must be followed by cd")
    default_directory = Path(clone[2].removesuffix("/").removesuffix(".git")).name
    checkout_directory = clone[3] if len(clone) == 4 else default_directory
    if change_directory[1] != checkout_directory:
        raise AssertionError(
            "checkout directory mismatch: "
            f"clone creates {checkout_directory!r}, cd uses {change_directory[1]!r}"
        )


def test_readme_quick_start_uses_exact_checkout_directory() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    quick_start = readme.split("## Quick start", maxsplit=1)[1].split("\n## ", maxsplit=1)[0]
    blocks = [match.group("commands") for match in _BASH_BLOCK.finditer(quick_start)]
    clone_block = next(block for block in blocks if "git clone " in block)
    _assert_checkout_path_matches(clone_block)


def test_checkout_path_check_rejects_case_mismatch() -> None:
    commands = "git clone https://example.test/Owner/RepoGym.git\ncd repogym\n"
    with pytest.raises(AssertionError, match="checkout directory mismatch"):
        _assert_checkout_path_matches(commands)


def test_ci_has_least_privilege_pinned_actions_and_supported_python_matrix() -> None:
    workflow = yaml.load(
        (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8"),
        Loader=yaml.BaseLoader,
    )
    assert workflow["permissions"] == {"contents": "read"}
    assert workflow["concurrency"]["cancel-in-progress"] == "true"
    test_job = workflow["jobs"]["test"]
    assert test_job["strategy"]["matrix"]["python-version"] == [
        "3.11",
        "3.12",
        "3.13",
        "3.14",
    ]
    assert test_job["strategy"]["matrix"]["os"] == ["ubuntu-24.04", "windows-latest"]
    assert workflow["jobs"]["security"]["runs-on"] == "ubuntu-24.04"

    action_steps = [
        step["uses"] for job in workflow["jobs"].values() for step in job["steps"] if "uses" in step
    ]
    assert action_steps
    assert all(_ACTION_SHA.fullmatch(action) for action in action_steps)
    security_commands = [step.get("run", "") for step in workflow["jobs"]["security"]["steps"]]
    assert any(command.startswith("bandit ") for command in security_commands)
    assert any(command.startswith("pip-audit ") for command in security_commands)


def test_repository_maintenance_forms_and_dependabot_are_parseable() -> None:
    dependabot = yaml.safe_load((ROOT / ".github" / "dependabot.yml").read_text(encoding="utf-8"))
    assert {update["package-ecosystem"] for update in dependabot["updates"]} == {
        "github-actions",
        "pip",
    }
    issue_templates = ROOT / ".github" / "ISSUE_TEMPLATE"
    for template in (issue_templates / "bug_report.yml", issue_templates / "feature_request.yml"):
        form = yaml.safe_load(template.read_text(encoding="utf-8"))
        assert form["name"]
        assert form["description"]
        assert form["body"]
    issue_config = yaml.safe_load((issue_templates / "config.yml").read_text(encoding="utf-8"))
    security_link = issue_config["contact_links"][0]
    assert security_link["url"].startswith("https://github.com/")
    assert "/security/advisories/new" not in security_link["url"]


def test_release_workflow_is_ci_gated_pinned_and_fail_closed() -> None:
    workflow = yaml.load(
        (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8"),
        Loader=yaml.BaseLoader,
    )
    assert workflow["on"]["workflow_run"] == {
        "workflows": ["CI"],
        "types": ["completed"],
    }
    job = workflow["jobs"]["release"]
    assert job["runs-on"] == "ubuntu-24.04"
    condition = job["if"]
    assert "conclusion == 'success'" in condition
    assert "event == 'push'" in condition
    assert "startsWith" in condition
    assert job["permissions"] == {
        "attestations": "write",
        "contents": "write",
        "id-token": "write",
    }
    action_steps = [step for step in job["steps"] if "uses" in step]
    assert all(_ACTION_SHA.fullmatch(step["uses"]) for step in action_steps)

    commands = "\n".join(step.get("run", "") for step in job["steps"])
    assert "git rev-list -n 1" in commands
    assert 'test "${RELEASE_TAG}" = "v${PROJECT_VERSION}"' in commands
    assert "pip install --no-index --no-deps" in commands
    assert "sha256sum" in commands
    assert 'gh release create "${RELEASE_TAG}"' in commands
    assert "--verify-tag" in commands
    attestation = next(step for step in action_steps if "attest-build-provenance" in step["uses"])
    assert attestation["if"] == "github.event.repository.visibility == 'public'"


def test_comparison_smoke_accepts_expected_score_code(tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    calls: list[list[str]] = []

    def execute(command: list[str]) -> int:
        calls.append(command)
        if "grade" in command:
            runs.mkdir(exist_ok=True)
            submission = command[-1]
            (runs / Path(submission).name).mkdir()
            return ExitCode.SCORE_NOT_PASSED if submission.endswith("broken") else ExitCode.SUCCESS
        return ExitCode.SUCCESS

    run_smoke(runs, execute)

    assert [command[3] for command in calls] == ["grade", "grade", "compare", "compare"]
    assert calls[-1][-2:] == ["--output", ".repogym/comparison.json"]


def test_comparison_smoke_rejects_unexpected_grade_code(tmp_path: Path) -> None:
    with pytest.raises(SmokeError, match="expected 30"):
        run_smoke(tmp_path / "runs", lambda _command: ExitCode.EXECUTION_FAILED)

from __future__ import annotations

import subprocess
import sys
import tarfile
import tomllib
import venv
import zipfile
from pathlib import Path

from repogym import __version__

ROOT = Path(__file__).parents[1]


def _project_version() -> str:
    document = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return str(document["project"]["version"])


def test_release_version_sources_and_changelog_agree() -> None:
    version = _project_version()
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert __version__ == version
    assert changelog.index("## [Unreleased]") < changelog.index(f"## [{version}] - ")
    assert (ROOT / "docs" / "releases" / f"v{version}.md").is_file()


def test_release_builds_installable_wheel_and_complete_sdist(tmp_path: Path) -> None:
    output = tmp_path / "dist"
    subprocess.run(
        [sys.executable, "-m", "build", "--no-isolation", "--outdir", str(output)],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    version = _project_version()
    wheels = list(output.glob("repogym-*.whl"))
    source_archives = list(output.glob("repogym-*.tar.gz"))
    assert [path.name for path in wheels] == [f"repogym-{version}-py3-none-any.whl"]
    assert [path.name for path in source_archives] == [f"repogym-{version}.tar.gz"]

    with zipfile.ZipFile(wheels[0]) as wheel:
        names = set(wheel.namelist())
        metadata = wheel.read(f"repogym-{version}.dist-info/METADATA").decode("utf-8")
        entry_points = wheel.read(f"repogym-{version}.dist-info/entry_points.txt").decode("utf-8")
    assert "repogym/__init__.py" in names
    assert f"Version: {version}\n" in metadata
    assert "repogym = repogym.cli:app" in entry_points

    archive_root = f"repogym-{version}"
    with tarfile.open(source_archives[0], "r:gz") as source:
        members = {member.name for member in source.getmembers()}
    assert f"{archive_root}/pyproject.toml" in members
    assert f"{archive_root}/README.md" in members
    assert f"{archive_root}/LICENSE" in members
    assert f"{archive_root}/src/repogym/cli.py" in members

    environment = tmp_path / "venv"
    venv.EnvBuilder(with_pip=True).create(environment)
    executable = environment / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    subprocess.run(
        [
            str(executable),
            "-m",
            "pip",
            "install",
            "--no-index",
            "--no-deps",
            str(wheels[0]),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    installed = subprocess.run(
        [str(executable), "-c", "import repogym; print(repogym.__version__)"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert installed.stdout.strip() == version

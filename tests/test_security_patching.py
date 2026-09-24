from __future__ import annotations

import os
from pathlib import Path

import pytest

from repogym.exceptions import PatchError, SecurityError
from repogym.patching import apply_patch, parse_patch
from repogym.security import (
    changed_paths,
    copy_tree_safe,
    file_manifest,
    redact_known_paths,
    safe_join,
    sanitize_command,
    validate_relative_path,
)


@pytest.mark.parametrize("path", ["../secret", "/root/file", "C:\\Windows\\file"])
def test_rejects_unsafe_relative_paths(path: str) -> None:
    with pytest.raises(SecurityError):
        validate_relative_path(path, "field")


def test_safe_join_stays_under_root(tmp_path: Path) -> None:
    assert safe_join(tmp_path, "a/b.txt") == (tmp_path / "a" / "b.txt").resolve()


def test_safe_copy_and_manifest(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "a.txt").write_text("one", encoding="utf-8")
    target = tmp_path / "target"
    copy_tree_safe(source, target)
    before = file_manifest(target)
    (target / "a.txt").write_text("two", encoding="utf-8")
    (target / "b.txt").write_text("new", encoding="utf-8")
    assert changed_paths(before, file_manifest(target)) == ["a.txt", "b.txt"]


@pytest.mark.skipif(os.name == "nt", reason="Creating symlinks may require Windows privileges")
def test_copy_rejects_symlink(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "real").write_text("x", encoding="utf-8")
    (source / "link").symlink_to(source / "real")
    with pytest.raises(SecurityError, match="Symbolic"):
        copy_tree_safe(source, tmp_path / "target")


def test_copy_rejects_missing_source(tmp_path: Path) -> None:
    with pytest.raises(SecurityError, match="does not exist"):
        copy_tree_safe(tmp_path / "missing", tmp_path / "target")


def test_applies_unified_patch(tmp_path: Path) -> None:
    (tmp_path / "value.py").write_text("before = 1\nafter = 2\n", encoding="utf-8")
    patch = (
        "--- a/value.py\n+++ b/value.py\n@@ -1,2 +1,2 @@\n-before = 1\n+before = 3\n after = 2\n"
    )
    assert apply_patch(tmp_path, patch) == ["value.py"]
    assert (tmp_path / "value.py").read_text(encoding="utf-8") == "before = 3\nafter = 2\n"


@pytest.mark.parametrize(
    "patch, message",
    [
        ("nothing", "not a unified diff"),
        ("--- a/x\n+++ b/y\n@@ -1 +1 @@\n-a\n+b\n", "Renames"),
        ("--- /dev/null\n+++ b/x\n@@ -0 +1 @@\n+x\n", "Creating"),
    ],
)
def test_rejects_unsupported_patches(patch: str, message: str) -> None:
    with pytest.raises(PatchError, match=message):
        parse_patch(patch)


def test_patch_rejects_context_mismatch(tmp_path: Path) -> None:
    (tmp_path / "x").write_text("actual\n", encoding="utf-8")
    with pytest.raises(PatchError, match="context mismatch"):
        apply_patch(tmp_path, "--- a/x\n+++ b/x\n@@ -1 +1 @@\n-wrong\n+new\n")


def test_sanitizes_absolute_command_arguments() -> None:
    command = sanitize_command(
        ["python", "C:\\Users\\person\\tests.py", "--config=/home/person/config.toml"]
    )
    assert command == [
        "python",
        "<absolute-path>/tests.py",
        "--config=<absolute-path>/config.toml",
    ]


def test_redacts_known_paths_from_output(tmp_path: Path) -> None:
    local_file = tmp_path / "workspace" / "test.py"
    output = f"failure in {local_file}"
    assert str(tmp_path) not in redact_known_paths(output, [tmp_path])

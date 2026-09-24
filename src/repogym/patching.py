"""Small, strict unified-diff applier for reference solutions."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from repogym.exceptions import PatchError, SecurityError
from repogym.security import safe_join

HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


@dataclass
class FilePatch:
    path: str
    hunks: list[list[str]]


def _clean_header_path(value: str) -> str:
    path = value.split("\t", 1)[0].strip()
    if path == "/dev/null":
        raise PatchError("Creating or deleting files is not supported in reference patches")
    if path.startswith(("a/", "b/")):
        path = path[2:]
    return path


def parse_patch(text: str) -> list[FilePatch]:
    lines = text.splitlines(keepends=True)
    patches: list[FilePatch] = []
    index = 0
    while index < len(lines):
        if not lines[index].startswith("--- "):
            index += 1
            continue
        old_path = _clean_header_path(lines[index][4:])
        index += 1
        if index >= len(lines) or not lines[index].startswith("+++ "):
            raise PatchError(f"Missing +++ header after {old_path}")
        new_path = _clean_header_path(lines[index][4:])
        if old_path != new_path:
            raise PatchError("Renames are not supported in reference patches")
        index += 1
        hunks: list[list[str]] = []
        while index < len(lines) and not lines[index].startswith("--- "):
            if lines[index].startswith("@@ "):
                hunk = [lines[index]]
                index += 1
                while index < len(lines) and not lines[index].startswith(("@@ ", "--- ")):
                    if lines[index].startswith((" ", "+", "-", "\\")):
                        hunk.append(lines[index])
                    index += 1
                hunks.append(hunk)
            else:
                index += 1
        if not hunks:
            raise PatchError(f"No hunks found for {old_path}")
        patches.append(FilePatch(new_path, hunks))
    if not patches:
        raise PatchError("Reference solution is not a unified diff")
    return patches


def patch_paths(text: str) -> list[str]:
    return [patch.path for patch in parse_patch(text)]


def apply_patch(workspace: Path, text: str) -> list[str]:
    changed: list[str] = []
    for file_patch in parse_patch(text):
        try:
            target = safe_join(workspace, file_patch.path)
        except SecurityError as exc:
            raise PatchError(str(exc)) from exc
        if not target.is_file():
            raise PatchError(f"Patch target does not exist: {file_patch.path}")
        original = target.read_text(encoding="utf-8").splitlines(keepends=True)
        output: list[str] = []
        source_index = 0
        for hunk in file_patch.hunks:
            match = HUNK.match(hunk[0].rstrip("\r\n"))
            if match is None:
                raise PatchError(f"Invalid hunk header in {file_patch.path}: {hunk[0].strip()}")
            old_start = int(match.group(1)) - 1
            if old_start < source_index or old_start > len(original):
                raise PatchError(f"Invalid hunk position in {file_patch.path}")
            output.extend(original[source_index:old_start])
            cursor = old_start
            for line in hunk[1:]:
                marker, content = line[:1], line[1:]
                if marker == "\\":
                    continue
                if marker in {" ", "-"}:
                    if cursor >= len(original) or original[cursor].rstrip("\r\n") != content.rstrip(
                        "\r\n"
                    ):
                        raise PatchError(f"Patch context mismatch in {file_patch.path}")
                    if marker == " ":
                        output.append(original[cursor])
                    cursor += 1
                elif marker == "+":
                    output.append(content)
            source_index = cursor
        output.extend(original[source_index:])
        target.write_text("".join(output), encoding="utf-8", newline="")
        changed.append(file_patch.path)
    return changed

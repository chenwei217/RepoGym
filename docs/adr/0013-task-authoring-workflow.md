# 0013: Atomic task scaffolding and author lint

Status: Accepted

## Problem and context

Authors currently copy a task tree and hand-edit YAML. It is easy to omit private tests, mismatch
expected counts, leave a blank reference patch, configure a shell-mediated command, or create a
directory whose name disagrees with the task ID.

## Current behavior

`validate` checks the machine contract: schema, layout, safe relative paths, discovered tests,
working directory, and constraint overlap. It intentionally does not distinguish incomplete
author placeholders from a runnable finished task, and no command creates the required tree.

## Alternatives considered

- Expand `validate` with opinionated warnings. That would change an established machine-facing
  contract and make existing automation noisy.
- Ship a directory users copy manually. This cannot validate parameters or publish atomically.
- Add a scaffold command plus an author-focused lint layer that reuses `validate_task`.

## Decision

`repogym init-task` accepts a strict task ID, title, and task-root directory. Interactive mode
prompts for missing ID/title; `--non-interactive` rejects missing values. It builds a complete
schema-v1 Python task under a same-filesystem staging directory, invokes existing validation, and
atomically renames the validated tree. Existing targets are never overwritten.

`repogym lint-task` reports validation failures plus stable coded diagnostics for empty or
placeholder descriptions/reference patches, test-count conflicts, shell launchers, absolute
command paths, early-stop pytest options, and an unrestricted allowed-path pattern. Warnings do
not fail the command; errors use the existing invalid-task exit code.

## External behavior

The scaffold contains starter code, public and private tests, `task.yaml`, `prompt.md`, and a
reference patch placeholder. It passes structural validation but intentionally fails author lint
with TODO warnings until the author supplies a real prompt, tests, and unified diff.

## Compatibility and security risks

Existing task schemas and validation semantics are unchanged. IDs cannot contain separators or
parent traversal, and publication occurs only below the explicitly selected task root. Atomic
publication avoids half-created tasks after write or validation failures. The command never
overwrites an existing directory.

## Verification

Tests cover interactive and non-interactive creation, Windows-compatible path handling, immediate
validation, duplicate and invalid IDs, traversal attempts, stable lint diagnostics, empty files,
conflicting counts, risky commands, placeholder warnings, atomic cleanup, and both bundled tasks.

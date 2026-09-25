# ADR 0002: Versioned TaskSpec migrations

## Problem and context

`task.yaml` had a task content version but no format version. A future structural change could
therefore be misread by an older RepoGym release or require a breaking flag day for every task.

## Current behavior

The loader passed YAML mappings directly to the current strict Pydantic model. Unknown fields
failed validation, but there was no way to distinguish an unsupported future schema from a typo.

## Alternatives considered

- Treat the package version as the schema version. This couples task compatibility to releases.
- Require every existing task to be rewritten before it can load. This breaks portable archives
  and third-party task collections unnecessarily.
- Add an integer schema version and migrate legacy mappings before model validation.

## Decision

Schema version 1 is the current format. An absent version and explicit version 0 identify the
legacy shape and are copied and normalized to version 1 in memory. The source file is never
rewritten. Unknown versions and non-integer version values are rejected before Pydantic field
validation. The task's existing string `version` continues to describe task content.

## External behavior and compatibility risk

Existing unversioned tasks retain their behavior. New examples declare version 1 explicitly.
Future schemas must add a deliberate migration step before the current model is changed. The
main risk is that a task previously using an extra `schema_version` field as accidental metadata
will now receive a targeted compatibility error instead of a generic unknown-field error.

## Verification

Tests cover current, omitted, explicit legacy, unknown, non-integer, boolean, and idempotently
migrated inputs. Both bundled tasks are validated and verified after their declarations change.

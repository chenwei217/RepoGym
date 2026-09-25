# 0009: Versioned plugin contracts

Status: Accepted

## Problem and context

RepoGym needs third-party task loaders, execution backends, and reporters without making internal
Pydantic models or orchestration details an accidental compatibility promise. Import failures,
incompatible versions, and duplicate plugin names must not stop built-in commands.

## Current behavior

Before this decision, only the internal `Executor` protocol was replaceable through the Python
API. There was no package discovery, compatibility negotiation, loader extension, reporter
extension, conflict policy, or way to inspect broken installations.

## Alternatives considered

- Import configured module paths directly. This has no standard package discovery or conflict
  metadata and makes configuration errors fatal at use time.
- Publish the complete internal object graph as the plugin API. This is convenient initially but
  tightly couples plugins to persistence models and prevents internal evolution.
- Discover a versioned registration containing narrow protocols and stable boundary DTOs.

## Decision

Use the `repogym.plugins` Python entry-point group. An entry point loads one immutable
`PluginRegistration` with API version 1 and at least one loader, executor, or reporter. Extensions
exchange standard-library values and plugin DTOs; core adapters validate task mappings, convert
execution responses, and sanitize report data.

Discovery is sorted by entry-point name and target. The first compatible registration for a
plugin name wins; later duplicates become conflict diagnostics. Import exceptions, malformed
registrations, and unsupported API versions are retained as diagnostics and discovery continues.
Built-in commands do not perform discovery. `repogym plugins` is an observational command and
returns successfully even when installed plugins are rejected.

## External behavior

Plugin packages can register task loaders, executor backends, and reporters against API version
1. Operators can inspect loaded and rejected entries with `repogym plugins`. Python callers use
the registry plus explicit adapters; installing a plugin does not silently replace core behavior.

## Compatibility and security risks

Future incompatible contracts require a new integer API version and explicit adapters rather
than guessing compatibility. Runtime protocol checks prove attribute presence, while adapter
validation remains responsible for returned values. Entry-point loading executes package import
code in the RepoGym process, so plugins are trusted code and must be reviewed before installation.

## Verification

Tests cover deterministic discovery, supported and unsupported versions, duplicate names,
malformed registrations, import exceptions, all three adapters, cancellation propagation,
response validation, path redaction, CLI diagnostics, and isolation from built-in commands. The
minimal reporter under `examples/plugins` demonstrates the packaging contract.

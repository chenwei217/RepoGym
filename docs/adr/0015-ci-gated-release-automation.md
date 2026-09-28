# ADR 0015: CI-gated release automation

## Problem

The first GitHub Release was assembled locally after CI. Although its wheel and source archive were
tested, future releases could diverge from the tagged commit or be published before the tag matrix
finishes.

## Options considered

1. Keep a documented manual process.
2. Publish directly when a tag is pushed, in parallel with CI.
3. React to the completed CI workflow, prove that an immutable version tag points to the tested
   commit, rebuild on a clean runner, and only then publish.

## Decision

Use option 3. The release workflow accepts only successful push-triggered CI runs whose head name
starts with `v`. It fetches an exact same-name tag, checks its commit, compares the tag with project
metadata, requires versioned release notes and a dated changelog section, builds both distributions,
installs the wheel without an index, and attaches SHA-256 checksums. Actions use immutable commit
SHAs and job permissions are explicit.

Artifact attestations run when the repository is public because GitHub availability for private
repositories depends on the account plan. PyPI publishing remains separate until a Trusted
Publisher is configured; no long-lived package token is introduced.

## Compatibility and risk

Existing tags and releases are unchanged. The workflow affects only future successful tag CI runs.
A branch named like a version cannot publish because the corresponding Git tag must exist and point
to the exact tested commit. Existing releases are not overwritten, so reruns fail closed.

## Acceptance

- Workflow contract tests verify trigger, success/event/tag gates, least privilege, pinned actions,
  exact tag/commit and version checks, offline wheel installation, checksums, and immutable release
  creation.
- The existing release contract test validates wheel/sdist metadata, contents, and installation.

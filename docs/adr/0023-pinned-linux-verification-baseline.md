# 0023: Explicit Linux verification baseline

## Problem and evidence

CI, security, and release jobs use `ubuntu-latest`. GitHub warns that this alias will migrate to
Ubuntu 26, while the successful run inspected on 2026-10-14 identifies its image as Ubuntu 24.04.
An automatic major-image change would alter the verification/build baseline without a review.

## Alternatives and decision

Keeping the moving alias is convenient but makes failures harder to attribute. Self-hosted images
need operational maintenance outside this repository. Pin Linux jobs to the currently verified
`ubuntu-24.04` label and add it to existing CI contract assertions. Windows and Python coverage
remain unchanged. A future Linux major upgrade should be an explicit, tested change.

## Compatibility and verification

This fixes the OS release family, not an immutable VM image: hosted image patches and permitted
dependency updates still arrive. It changes no RepoGym command or persisted schema. Run full
local checks and require all Ubuntu/Windows × Python 3.11–3.14 jobs and the security audit to pass.

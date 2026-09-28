# 0014: Optional container isolation executor

## Problem and current behavior

`LocalExecutor` deliberately runs trusted code with the caller's host privileges. The executor
protocol previously exposed only execution, so callers could not inspect whether a backend
controls filesystem, network, CPU, memory, or process count. Operators also had no built-in,
explicit container path and could accidentally assume local timeout cleanup was a sandbox.

## Options considered

1. Make every run use Docker. This breaks installations without Docker and silently changes the
   task runtime.
2. Fall back to local execution when Docker is unavailable. This violates the requested security
   boundary precisely when isolation matters.
3. Add declared capabilities and an explicitly selected Docker/OCI adapter, failing closed when
   its CLI or daemon is unavailable.

## Decision and trade-offs

Choose option 3. `Executor` exposes capability and effective-policy models. `LocalExecutor`
truthfully declares host filesystem/network access and no OS resource enforcement. The optional
`DockerExecutor` constructs argv directly with no shell, a read-only container root, one writable
workspace bind, disabled networking by default, `no-new-privileges`, and CPU, memory, and PID
limits. Docker must be explicitly selected with an image. Availability is probed before use and
failure never selects the local backend.

RepoGym delegates isolation enforcement to the installed Docker-compatible daemon. It does not
download, approve, or attest images; configure daemon policy and images independently. The
workspace bind remains writable because tests must exercise candidate code.

## External behavior and compatibility

Existing API and CLI calls continue to construct `LocalExecutor`. `verify` and `grade` accept
explicit Docker policy options, while `executor-info` reports availability and policy without
running task code. New runs persist an optional executor-policy object; old run artifacts remain
valid because that field is optional. Legacy custom executors receive conservative `unknown`
policy evidence through compatibility adapters.

## Risks and verification

Docker CLI syntax differs across alternative OCI frontends, images may lack task dependencies,
and a compromised daemon remains outside RepoGym's trust boundary. Tests therefore cover command
construction, Windows path mapping, invalid and escaping paths, missing CLI/daemon diagnostics,
no-fallback behavior, stopped-container cleanup, policy persistence, and default-local behavior.
A real-container integration test runs only when `REPOGYM_TEST_DOCKER_IMAGE` names a preloaded
image. Cross-platform CI does not require Docker.

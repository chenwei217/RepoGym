# Execution backends

RepoGym uses `LocalExecutor` unless a caller explicitly selects another backend. Inspect the
declarations before choosing one:

```bash
repogym executor-info --backend local
repogym executor-info --backend docker --docker-image python:3.12-slim
```

The command reports availability plus filesystem, network, CPU, memory, and process-limit
capabilities. JSON is available with `--format json`. An unavailable Docker CLI or daemon exits
with environment code 40 and never falls back to local execution.

## Local execution

Local execution is portable and remains the default. It uses direct argv (`shell=False`), bounded
output capture, timeout/cancellation, and process-tree cleanup. It is not a sandbox: candidate
code retains the current user's host filesystem, network, credentials, and operating-system
resource access.

## Docker/OCI execution

Select Docker only with an explicit image and a locally available Docker-compatible daemon:

```bash
repogym verify tasks/python-cache-ttl \
  --executor docker --docker-image my-repogym-python:3.12

repogym grade tasks/python-cache-ttl \
  --submission candidate \
  --executor docker --docker-image my-repogym-python:3.12 \
  --docker-cpus 1 --docker-memory-mb 512 --docker-pids-limit 128
```

The image must already provide the task's interpreter and test dependencies. RepoGym does not
pull, build, trust, or attest it. The default policy disables network access, makes the container
root read-only, mounts a temporary workspace at `/workspace`, adds `no-new-privileges`, supplies
a bounded `/tmp`, and limits CPU, memory, and PIDs. `--docker-allow-network` is an explicit opt-in.

The workspace bind is writable and Docker daemon security remains an operator responsibility.
Use least-privilege daemon configuration, trusted images without secrets, and additional platform
controls for hostile workloads. A selected but unavailable backend fails closed.

Python callers can instantiate `DockerExecutor` directly. `capabilities()` describes enforceable
controls; `policy()` returns the exact non-secret policy persisted with new grading evidence.
Timeout and cancellation stop the Docker client process tree and then force-remove the recorded
container ID.

## Plugin executors

Plugin executor adapters declare their backend identity but use conservative unknown isolation
policy unless the core contract is extended in a future plugin API version. Plugin code remains
trusted in-process code; protocol compatibility is not isolation.

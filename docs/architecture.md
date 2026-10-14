# Architecture

RepoGym uses a linear pipeline with small modules and explicit data models.

`analytics` reads bounded result-only observations, groups equal task/candidate/environment
identities, excludes ambiguous/replayed samples, computes descriptive statistics, and renders
terminal/JSON/escaped HTML. Grading fingerprints the prepared file manifest before test injection;
cache compatibility and archive validation preserve this optional identity without assuming it
for historical data. See [Repeated-run analysis](repeat-run-analysis.md).

`catalog` discovers and validates direct tasks, persists path-free pinned metadata, diagnoses
drift, and plans relative batch manifests. Optional batch job fingerprints are checked before
grading. Discovery, serialization, selection, and CLI are separate from execution backends.

`archives` transfers execution evidence independently of task bundles. A flat versioned manifest
binds artifacts to a run/task identity; import validates bytes, model associations, and privacy
before exclusive atomic publication. Existing report and history APIs consume imported runs.

`history` adds a derived SQLite inventory over persisted runs: bounded scanning, allowlisted
versioned summaries, transactional rebuilds, filtered queries, and source-digest checks. Grading
does not depend on the index. See [Run history](run-history.md).

1. `loader` migrates versioned task mappings and parses them into strict Pydantic models.
2. `validator` checks layout, safe relative paths, test discovery, and constraint overlap.
   `authoring` builds tasks in same-filesystem staging directories, validates before atomic
   publication, and layers author completeness/reproducibility diagnostics over the validator.
3. `doctor` inspects the local Python runtime, command, dependencies, working directory, and
   discovered tests without executing candidate code. It uses the same resolved command as the
   execution path and reports the executable it actually checked.
4. `reproducibility` hashes every task input, including the reference patch, into a stable
   SHA-256 identity.
5. `security` audits submission trees before copying, records content hashes, and applies the
   shared redaction policy used by persistence and reporting.
6. `Executor` abstracts execution and declares isolation capabilities/effective policy.
   `LocalExecutor` owns and cleans the exact host process tree; optional `DockerExecutor` builds
   a bounded, non-networked container command and force-removes stopped containers.
7. `verifier` compares the starter failure count with metadata, applies a strict unified diff,
   and proves the reference result.
8. `grader` overlays a candidate, runs all and public tests, then persists artifacts and a
   versioned, deterministically ordered evidence document.
9. `scoring` computes independent deterministic dimensions.
10. `cache` keys completed grades by all task, submission, executor, runtime, and tool-version
    inputs, serializes same-key work, and atomically publishes validated artifacts.
11. `reports` rehydrates `result.json` and renders terminal, JSON, escaped HTML, JUnit XML, or
    SARIF 2.1.0.
12. `comparison` computes stable A-to-B deltas without re-executing either run.
13. `bundles` exports the fingerprint input surface and verifies it before atomic import.
14. `plugins` discovers versioned third-party registrations and adapts their stable boundary DTOs
    to task, executor, and report internals without implicit activation.
15. `batch` orders manifest jobs, reuses grading and cache services, isolates per-job outcomes,
    atomically persists their snapshots, and replays four aggregate report formats.

The public Python surface is intentionally small: `load_task`, `validate_task`, `verify_task`,
`grade_submission`, report generation, comparison, and the explicit plugin registry/adapters are
the supported orchestration entry points. The Typer CLI is a thin adapter over those services.
Executor implementations conform to the `Executor` protocol. `LocalExecutor` remains the default;
`DockerExecutor` is a core opt-in adapter and is never an automatic fallback.

The Docker adapter maps the temporary task workspace to `/workspace`, translates the active host
Python marker to the image's `python`, and keeps the container root read-only. Its direct Docker
argv applies `no-new-privileges`, a bounded temporary filesystem, disabled networking by default,
and positive CPU, memory, and PID limits. `executor-info` probes both CLI and daemon. Selected
backend failure is an environment error rather than permission to execute locally. The image and
daemon remain external trust/configuration boundaries.

Plugin API version 1 uses one `repogym.plugins` entry-point group. A registration may provide a
task loader, executor backend, reporter, or any combination. Plugin-facing DTOs carry standard
types instead of internal persistence models. Loader output re-enters schema migration and strict
validation; executor output is converted at an adapter; reporter input and output cross the
shared redaction boundary. Discovery is deterministic and accumulates failures, incompatibilities,
and duplicate-name conflicts instead of raising. Core commands never discover or activate
plugins implicitly.

Batch schema version 1 separates orchestration from individual grading. Paths resolve relative to
the manifest, but the persisted model stores job IDs and sanitized result snapshots rather than
source paths. Lexical result ordering makes manifest order irrelevant. A single worker remains the
default; opt-in bounded workers serialize identical resolved task/submission pairs and execute
independent groups concurrently. A shared token cancels queued and active grading, and a versioned
schedule sidecar records the worker policy. Each job maps to the existing exit-code contract;
a fixed severity table produces the aggregate code. Report
replay reads only `batch.json`. JUnit models each job as one testcase with underlying counts in
properties, while SARIF merges violations and explicit non-success outcomes.

The CLI translates domain outcomes into a versioned automation contract: invalid input, execution
failure, a completed score below 100, environment/I/O failure, and an unexpected internal error
have distinct codes. A top-level group boundary catches only unwrapped filesystem and unexpected
exceptions; command-specific domain failures retain their more precise category. Framework usage
errors keep Typer's code 2.

CLI grading enables schema-v1 caching while the Python API remains opt-in through `cache_root`.
The key is canonical JSON over task fingerprint, candidate file hashes, resolved command, executor
identity and output limits, Python/OS identity, and RepoGym version. A per-key exclusive lock
spans lookup and execution. Completed misses publish a hash manifest and sanitized artifacts by
same-filesystem atomic rename; incomplete executions never publish. Hits validate exact membership
and hashes, then materialize a distinct run ID with cache-hit and source-run provenance. Invalid
entries are removed under the same lock and recomputed.

The configured test command remains generic. Recognized pytest commands receive a RepoGym-owned
JUnit output argument; the adapter parses that standard artifact into sorted per-test evidence
and derives aggregate counts from it. Non-pytest and legacy runs retain the terminal-summary
fallback with an explicit unavailable reason. Public tests are run separately for regression scoring. Submission
deletions are not represented by an overlay directory in the MVP; submissions add or replace
files. Reference patches deliberately support modifications only—file creation, deletion, and
rename are excluded to keep the bundled applier small and auditable.

Command resolution tokenizes the configured string once. An exact first token of `python` or
`python.exe` is replaced with `sys.executable` before both doctor diagnostics and execution, so
the two paths cannot select different Python installations through `PATH`. Absolute Python
paths, alternate interpreter names, and all other commands retain their configured first token.
The resolved argument vector is executed directly and never through a shell.

`CancellationToken` is a thread-safe one-way signal in the public executor protocol. A token set
before launch produces a cancelled result without starting a process. During execution the local
backend polls the token and timeout deadline, giving a completed process precedence when both are
observed together, then routes cancellation and timeout through the same terminate/wait/kill
cleanup. Verification reports cancellation as a domain error; grading persists a zero-score
cancelled result and does not launch remaining test or quality commands.

`result.json` records the task fingerprint plus sanitized argv, exit code, timeout state,
duration, `<WORKSPACE>` working directory, output filenames, termination diagnostics, and the
test-statistics source. New evidence also records the selected backend's non-secret filesystem,
network, CPU, memory, PID, and image policy. It embeds environment schema v1, collected once before execution,
with a canonical digest over an allowlisted Python/OS/dependency/tool/executor snapshot. Output
evidence includes original byte counts and per-stream truncation
flags. The executor retains bounded beginnings and endings while continuously draining the child
pipes, preventing pipe deadlocks and unbounded capture memory without losing the final pytest
summary. `metadata.json` contains the same structured evidence with creation time and schema
version. Old results using `execution.command` remain readable. Neither file stores the original
task or submission absolute path. Loading an existing run applies redaction again before
terminal, JSON, HTML, JUnit, SARIF, or comparison rendering.

JUnit renders persisted pytest case identities, statuses, and durations. It retains the earlier
aggregate adapter with stable synthetic names only for legacy or unsupported runs without
per-test evidence. Terminal, JSON, and HTML consume the same sorted model. SARIF maps
deterministic, sorted scope violations to versioned rule IDs and attaches relative artifact and
line locations when present. Both machine serializers consume the sanitized `GradeResult`;
SARIF defensively redacts violation strings again when called directly.

`evidence.json` schema v2 unifies command, aggregate and per-test, runtime-environment, and
output-artifact records. Each record carries its task, source, observation time, status, summary,
and typed details. Ordering uses kind, source, and summary rather than insertion order. Runtime
evidence is restricted to Python implementation/version and OS family; failure summaries are
bounded and credential/path-redacted, and raw JUnit captured output is not persisted. Environment
records consume the persisted run snapshot; they never inspect the machine loading an old
artifact. Schema-1 documents migrate in memory. Runs without the file are adapted from their
existing result, metadata, and output artifacts.

The fingerprint incorporates length-prefixed normalized relative paths and file bytes in lexical
path order. Required inputs are `task.yaml`, prompt/description, `starter/`, public tests, private
tests, and `reference/solution.patch`. Missing inputs are an error. Length prefixes prevent
ambiguous concatenation, ordering makes the digest stable, and byte-level hashing makes
line-ending or encoding changes visible.

## Current architectural boundaries

Task definitions and run artifacts are versioned independently. `TaskSpec.schema_version`
selects the YAML format and its migration path, while `TaskSpec.version` describes the task
contract. Unversioned and explicit v0 definitions normalize in memory to v1; unknown future
versions are rejected. Result loading separately adapts the original execution-evidence field
name. Task inputs can also be exported as package format version 1. Import accepts exactly the
members declared by the manifest and publishes a task only after archive safety, content
integrity, TaskSpec validation, and full fingerprint verification succeed.

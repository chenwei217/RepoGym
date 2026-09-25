# RepoGym

RepoGym turns real software issues into reproducible, testable, and quantitatively scored AI
coding tasks.

AI coding evaluations are most useful when the task contract, starting state, hidden checks,
and scoring formula can be inspected and replayed. RepoGym packages those pieces in a small,
versioned directory and produces durable run artifacts instead of a single opaque pass/fail.

## Features

- Strict Pydantic validation for task metadata and path constraints
- Public and private pytest suites with reference-solution verification
- SHA-256 task fingerprints over every versioned task input, including the reference patch
- Environment diagnostics for commands, dependencies, working directories, and test discovery
- Temporary workspaces and a replaceable executor interface
- Generic `python` task commands are bound to the interpreter running RepoGym
- Deterministic correctness, regression, static-quality, and scope scores
- Deterministic run-to-run comparison in terminal or JSON form
- Terminal, JSON, and self-contained HTML reports
- Preflight submission auditing for scope, links, reparse points, size, and sensitive filenames
- Process-tree timeout cleanup plus unified local-path redaction in every report format
- Integrity-checked, versioned ZIP export and atomic import of portable tasks
- Two original, runnable Python tasks

## Quick start

RepoGym requires Python 3.11 or newer.

```bash
git clone https://github.com/chenwei217/RepoGym.git
cd repogym
python -m pip install -e ".[dev]"
repogym --help
repogym list
```

Validate and verify a task, grade the included correct submission, and render its report:

```bash
repogym validate tasks/python-cache-ttl
repogym doctor tasks/python-cache-ttl
repogym verify tasks/python-cache-ttl
repogym grade tasks/python-cache-ttl --submission examples/submissions/cache-ttl-fixed
repogym report .repogym/runs/<run-id> --format html --output report.html
repogym compare .repogym/runs/<run-a> .repogym/runs/<run-b>
repogym bundle export tasks/python-cache-ttl python-cache-ttl.zip
repogym bundle import python-cache-ttl.zip --destination imported-tasks
```

Run the project checks:

```bash
ruff check .
ruff format --check .
mypy src/repogym
pytest --cov=repogym --cov-report=term-missing
```

## CLI

| Command | Purpose |
| --- | --- |
| `repogym list [--tasks-dir PATH]` | Discover valid task definitions |
| `repogym validate TASK` | Check metadata, paths, and required files |
| `repogym doctor TASK` | Diagnose the local execution environment |
| `repogym verify TASK` | Prove the starter fails and the reference fix passes |
| `repogym grade TASK --submission DIR` | Grade a candidate in a temporary workspace |
| `repogym report RUN --format terminal\|json\|html [--output FILE]` | Re-render saved run artifacts |
| `repogym compare RUN_A RUN_B --format terminal\|json [--output FILE]` | Compare two persisted runs |
| `repogym bundle export TASK OUTPUT` | Export a versioned, integrity-checked task package |
| `repogym bundle import BUNDLE --destination DIR` | Verify and atomically import a task package |
| `repogym version` | Print the installed version |

Pass `--debug` before a command to show tracebacks for expected domain errors.

## Reproducibility and diagnostics

Every grade stores a SHA-256 task fingerprint in both `metadata.json` and `result.json`. The
digest covers normalized relative paths and exact bytes for `task.yaml`, `prompt.md`, the
configured description, `starter/`, public and private tests, and `reference/solution.patch`.
Changing any of those inputs changes the fingerprint; mtimes and file creation order do not.

Run `doctor` before a long evaluation to inspect the current environment. This output was
captured from the bundled cache task; the Python version and interpreter path will reflect the
local runtime:

```text
$ repogym doctor tasks/python-cache-ttl
PASS task definition: Loaded python-cache-ttl.
PASS starter project: Starter project directory exists.
PASS python version: Python 3.14.4; requires 3.11+.
PASS test command: Executable found: /path/to/venv/bin/python
PASS dependencies: Python module available: pytest
PASS working directory: Starter working directory exists: .
PASS public test discovery: 4 public tests found.
PASS private test discovery: 4 private tests found.
PASS temporary directory: Temporary workspace is writable.
PASS task fingerprint: Deterministic SHA-256:
d92dfb7b7bc039787c17692ef75e74d20c8ddf0906c05efa78f2a95bac64ddb0
```

When a task command starts with exactly `python` or `python.exe`, RepoGym replaces that first
argument with `sys.executable`. Consequently, virtual-environment and pipx installations run
tests with the same interpreter that runs RepoGym, even when another Python appears first on
`PATH`. Explicit absolute Python paths, other interpreter names, and non-Python commands are
left unchanged. Commands are always passed as argument lists with `shell=False`.

## Comparing runs

`compare` reports B minus A for the total score, every scoring dimension, passed/failed/total
tests, duration, status, timeout state, and violations. For the bundled broken and fixed cache
submissions, an actual local run produced:

```text
Metric             Run A  Run B   Delta
total score        20.00  100.00  +80.00
correctness         0.00   60.00  +60.00
regression_safety   0.00   20.00  +20.00
tests passed        0       8      +8
tests failed        8       0      -8
tests total         8       8      +0
Status: completed -> completed; timed out: False -> False
Violations added: 0; removed: 0
```

Use `--format json` and optionally `--output FILE` for automation. Comparisons read immutable
run artifacts and never re-run candidate code. A task-ID mismatch is an error; a fingerprint
mismatch is a prominent comparability warning.

## Task specification

Each task owns its prompt, starter tree, test suites, and reference patch:

```text
tasks/my-task/
├── task.yaml
├── prompt.md
├── starter/
├── tests/
│   ├── public/
│   └── private/
└── reference/
    └── solution.patch
```

```yaml
id: my-task
title: Repair an edge case
difficulty: medium
language: python
version: "1.0"
description_file: prompt.md
execution:
  timeout_seconds: 30
  test_command: python -m pytest -q
  working_directory: "."
scoring:
  correctness: {weight: 60}
  regression_safety: {weight: 20}
  code_quality: {weight: 10}
  scope_control: {weight: 10}
expected:
  failing_tests_before: 2
  passing_tests_after: 8
constraints:
  allowed_paths: [src/**, tests/**]
  forbidden_paths: [pyproject.toml, repogym/**]
```

See [Task authoring](docs/task-authoring.md) for the complete design guidance.

## Scoring model

Scores are calculated at run time; no result is hard-coded. Correctness is the weighted ratio
of all passed tests. Regression safety applies the same formula to public tests. Code quality
splits its weight equally between Python syntax and Ruff. Scope control gives full credit for
in-scope changes, proportionally deducts outside changes, and gives zero if a forbidden path is
changed. See [Scoring](docs/scoring.md) for edge cases and exact formulas.

## HTML report

The HTML renderer emits one portable file with no CDN dependency. It contains the overall
score, every scoring dimension, test statistics, violations, duration, and collapsed process
output. Untrusted output is HTML-escaped and local absolute paths are redacted first.

## Architecture

```mermaid
flowchart TD
    A[Task Definition] --> B[Validation and Doctor]
    B --> C[Task Fingerprint]
    C --> D[Isolated Workspace]
    D --> E[Test Execution and Evidence]
    E --> F[Deterministic Scoring]
    F --> G[JSON / Terminal / HTML Report]
    G --> H[Run Comparison]
```

The `Executor` protocol separates orchestration from process execution. The current release
ships a `LocalExecutor`; a future container executor can implement the same interface. More
detail is in [Architecture](docs/architecture.md).

## Security model

**LocalExecutor is not a sandbox.** Task tests and candidate code execute as the current OS
user and must be trusted. RepoGym audits submissions before copying, rejects links and path
escapes, and terminates the recorded process tree on timeout, but those controls do not contain
malicious code. Use a disposable VM or appropriately configured container for untrusted
material. Read [Security model](docs/security-model.md) before operating a shared service.

Persisted execution evidence includes a sanitized argument vector, exit code, timeout state,
duration, `<WORKSPACE>` working directory, output artifact names, test-statistics source, and
termination diagnostics. The same redaction policy is applied to captured output, JSON,
terminal, HTML, and comparisons; environment variables and tokens are never recorded
automatically.

Detailed workflows: [CLI reference](docs/cli.md),
[reproducibility](docs/reproducibility.md), [run comparison](docs/run-comparison.md),
[task bundles](docs/task-bundles.md), and [project milestones](docs/milestones.md).

## Roadmap

The following capabilities are planned and are not present in the MVP:

- Docker/OCI executor with resource and network policies
- GitHub issue importer
- coding-agent adapters and batch evaluation
- richer language-specific test result adapters

## Contributing

Bug reports, task proposals, and focused pull requests are welcome. See
[CONTRIBUTING.md](CONTRIBUTING.md) for local checks and task review expectations.

## License

Apache License 2.0. See [LICENSE](LICENSE).

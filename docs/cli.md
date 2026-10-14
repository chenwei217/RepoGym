# CLI reference

Commands use the stable codes below. Put `--debug` before the subcommand to include a traceback.

| Code | Meaning |
| ---: | --- |
| `0` | Command succeeded; `grade` also means a score of exactly 100 |
| `2` | Command syntax or option error reported by Typer |
| `10` | Task, submission, bundle, or command input is invalid |
| `20` | Test execution, verification, timeout, cancellation, or launch failed |
| `30` | Grading completed, but the score is below 100 |
| `40` | Environment, diagnostic, run-artifact, or filesystem operation failed |
| `70` | Unexpected internal RepoGym error |

| Command | Reads code | Executes task code | Writes artifacts |
| --- | --- | --- | --- |
| `repogym list [--tasks-dir PATH]` | task metadata | no | no |
| `repogym validate TASK` | task metadata and tests | no | no |
| `repogym init-task [TASK_ID] [--title TITLE] [--tasks-dir DIR] [--non-interactive]` | author values | no | new validated task directory |
| `repogym lint-task TASK` | task metadata and author content | no | no |
| `repogym doctor TASK` | task metadata and filesystem metadata | no | temporary probe only |
| `repogym verify TASK [--executor local\|docker]` | complete task | starter and reference | temporary workspace only |
| `repogym grade TASK --submission DIR [--no-cache] [--executor local\|docker]` | task and audited submission | candidate and tests on cache miss | `.repogym/runs/<id>/`, `.repogym/cache/` |
| `repogym report RUN --format terminal\|json\|html\|junit\|sarif [--output FILE]` | run artifacts | no | optional output file |
| `repogym compare RUN_A RUN_B --format terminal\|json [--output FILE]` | two run artifacts | no | optional output file |
| `repogym environment [--format terminal\|json]` | current non-sensitive runtime facts | no | no |
| `repogym executor-info [--backend local\|docker] [--format terminal\|json]` | backend availability and policy | no | no |
| `repogym bundle export TASK OUTPUT` | validated task directory | no | new ZIP task bundle |
| `repogym bundle import BUNDLE --destination DIR` | ZIP task bundle | no | verified task directory |
| `repogym cache list [--cache-dir PATH]` | cache manifests and artifacts | no | no |
| `repogym cache verify [--cache-dir PATH]` | cache manifests and artifacts | no | no |
| `repogym cache clear [--cache-dir PATH]` | cache entries | no | removes a snapshot of entries |
| `repogym plugins` | installed entry-point metadata and plugin imports | no | no |
| `repogym batch run MANIFEST [--format FORMAT]` | manifest, tasks, submissions, cache | candidate and tests on cache miss | individual runs, cache, and `batch.json` |
| `repogym batch report BATCH_RUN [--format FORMAT]` | persisted `batch.json` | no | optional output file |
| `repogym version` | package metadata | no | no |
| `repogym runs refresh [--runs-dir DIR]` | persisted run summaries | no | transactional SQLite index |
| `repogym runs list [--task ID] [--status STATUS] [--format terminal\|json]` | run index | no | no |
| `repogym runs show RUN_ID` | index and matching source result | no | no |
| `repogym archive export RUN OUTPUT` | sanitized run artifacts | no | new ZIP archive |
| `repogym archive verify ARCHIVE` | complete archive | no | no |
| `repogym archive import ARCHIVE --destination DIR` | verified archive | no | new run directory |

`doctor` separates PASS, WARN, and FAIL checks and never starts the configured test command.
`init-task` prompts for omitted ID/title unless `--non-interactive` is set, validates a staged
tree, refuses existing targets, and publishes atomically. `lint-task` reports coded author
warnings and returns invalid-task code 10 only for validation or authoring errors.
`verify` and `grade` stay local unless `--executor docker --docker-image IMAGE` is explicit.
Docker policy options set CPU, memory, PID, and opt-in network access. `executor-info` probes the
selected backend without executing task code; unavailable Docker returns code 40 and never causes
a local fallback. See [Execution backends](executors.md).
`compare` rejects different task IDs. Equal task IDs with unequal fingerprints produce a warning
because the score delta may cross task versions. Terminal and JSON comparisons use the same
deterministic comparison model. Available runtime snapshots add equality, fingerprints, and sorted
field differences; missing legacy snapshots remain explicitly unavailable.

`report --format junit` emits deterministic collected pytest cases for CI test viewers and falls
back to aggregate synthetic cases for old runs without that evidence. Terminal, JSON, and HTML
also display the same per-test model. `report --format sarif` emits SARIF 2.1.0 results for scope
violations and includes a relative file and line location when the violation carries them. HTML
requires `--output`; all machine formats may be printed or written with `--output`.

`bundle export` refuses to overwrite an existing path. `bundle import` requires an existing
destination directory, validates the complete archive, and refuses to replace an existing task.
See [Task bundles](task-bundles.md).

The same outcome has the same code in human and machine modes: for example, missing run
artifacts return `40` for terminal, JSON, JUnit, and SARIF reports, and both comparison formats.
POSIX shells read the code from `$?`; PowerShell reads `$LASTEXITCODE`. CI steps fail naturally
for every nonzero value. If a pipeline intentionally evaluates partial solutions, explicitly
accept `30` while continuing to reject `10`, `20`, `40`, and `70`.

`grade` enables the content-addressed cache by default. `--no-cache` forces execution, while
`--cache-dir` selects an alternate store. Hits still create a new ordinary run directory and
identify their source run; cancelled, timed-out, and launch-error results are never cached. Cache
integrity failures return environment code `40`. `cache verify` reports corruption without
modifying it; normal grading removes a corrupt matching entry and safely recomputes it.

`plugins` discovers only the `repogym.plugins` entry-point group. It reports loaded, failed,
incompatible, and conflicting registrations in deterministic order and exits successfully even
when individual plugins fail to import. Built-in commands do not discover plugins implicitly.
See [Plugin development](plugins.md) for the versioned contract and trust boundary.

`batch run` resolves paths relative to its versioned manifest, sorts unique job IDs, and continues
after individual failures. `batch report` replays the saved result without executing code. Both
support terminal, JSON, JUnit, and SARIF and return the persisted aggregate outcome after writing
the report. See [Batch evaluation](batch-evaluation.md) for schema, ordering, cache, and exit-code
semantics.

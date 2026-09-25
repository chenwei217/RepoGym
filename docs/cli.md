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
| `repogym doctor TASK` | task metadata and filesystem metadata | no | temporary probe only |
| `repogym verify TASK` | complete task | starter and reference | temporary workspace only |
| `repogym grade TASK --submission DIR [--no-cache]` | task and audited submission | candidate and tests on cache miss | `.repogym/runs/<id>/`, `.repogym/cache/` |
| `repogym report RUN --format terminal\|json\|html\|junit\|sarif [--output FILE]` | run artifacts | no | optional output file |
| `repogym compare RUN_A RUN_B --format terminal\|json [--output FILE]` | two run artifacts | no | optional output file |
| `repogym bundle export TASK OUTPUT` | validated task directory | no | new ZIP task bundle |
| `repogym bundle import BUNDLE --destination DIR` | ZIP task bundle | no | verified task directory |
| `repogym cache list [--cache-dir PATH]` | cache manifests and artifacts | no | no |
| `repogym cache verify [--cache-dir PATH]` | cache manifests and artifacts | no | no |
| `repogym cache clear [--cache-dir PATH]` | cache entries | no | removes a snapshot of entries |
| `repogym version` | package metadata | no | no |

`doctor` separates PASS, WARN, and FAIL checks and never starts the configured test command.
`compare` rejects different task IDs. Equal task IDs with unequal fingerprints produce a warning
because the score delta may cross task versions. Terminal and JSON comparisons use the same
deterministic comparison model.

`report --format junit` emits a deterministic aggregate test suite for CI test viewers. `report
--format sarif` emits SARIF 2.1.0 results for scope violations and includes a relative file and
line location when the violation carries them. HTML requires `--output`; all machine formats may
be printed or written with `--output`.

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

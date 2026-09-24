# CLI reference

All commands return zero on success and nonzero for validation, environment, security, or report
errors. Put `--debug` before the subcommand to include a traceback.

| Command | Reads code | Executes task code | Writes artifacts |
| --- | --- | --- | --- |
| `repogym list [--tasks-dir PATH]` | task metadata | no | no |
| `repogym validate TASK` | task metadata and tests | no | no |
| `repogym doctor TASK` | task metadata and filesystem metadata | no | temporary probe only |
| `repogym verify TASK` | complete task | starter and reference | temporary workspace only |
| `repogym grade TASK --submission DIR` | task and audited submission | candidate and tests | `.repogym/runs/<id>/` |
| `repogym report RUN --format terminal\|json\|html [--output FILE]` | run artifacts | no | optional output file |
| `repogym compare RUN_A RUN_B --format terminal\|json [--output FILE]` | two run artifacts | no | optional output file |
| `repogym version` | package metadata | no | no |

`doctor` separates PASS, WARN, and FAIL checks and never starts the configured test command.
`compare` rejects different task IDs. Equal task IDs with unequal fingerprints produce a warning
because the score delta may cross task versions. Terminal and JSON comparisons use the same
deterministic comparison model.

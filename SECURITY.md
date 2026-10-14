# Security policy

RepoGym's local executor runs task and submission code with the privileges of the invoking
user. It is intended only for trusted code. Do not expose it as a public grading service or run
unknown submissions on a workstation containing valuable data.

## Supported versions

The latest GitHub Release and the current `main` branch receive security fixes. Older releases may
be used to reproduce a report but are not guaranteed to receive backports.

## Reporting

Captured diagnostics and report replay apply shared best-effort credential filtering for labeled
secrets, authentication headers, URL passwords, and private-key blocks. Unknown or unlabeled
secrets may remain; tasks must not print credentials. RepoGym does not enumerate environment
variable values to discover secrets. See `docs/adr/0017-shared-credential-redaction.md`.

For suspected vulnerabilities, avoid a public issue until maintainers have assessed the report.
Private vulnerability reporting is not available for this private repository on its current GitHub
plan. Use the repository owner's GitHub profile to establish a private contact channel before
sharing details. Include affected versions, sanitized reproduction steps, impact, and any suggested
mitigation. Do not include live credentials or private task contents. Maintainers aim to acknowledge
a complete report within seven days and will coordinate disclosure after a fix or documented
mitigation is available.

See `docs/security-model.md` for trust boundaries and deployment guidance.


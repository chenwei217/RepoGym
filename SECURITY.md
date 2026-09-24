# Security policy

RepoGym's local executor runs task and submission code with the privileges of the invoking
user. It is intended only for trusted code. Do not expose it as a public grading service or run
unknown submissions on a workstation containing valuable data.

For suspected vulnerabilities, avoid a public issue until maintainers have had a chance to
assess the report. Because this repository is a project template without a published security
contact yet, use GitHub's private vulnerability reporting feature after the repository is
published. Include affected versions, reproduction steps, and impact.

See `docs/security-model.md` for trust boundaries and deployment guidance.


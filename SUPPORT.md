# Support

Use GitHub Issues for reproducible bugs and feature proposals. Include the RepoGym version,
platform, command, expected result, actual result, and a minimal sanitized task when possible.

Questions about untrusted execution must start with `docs/security-model.md`: the local executor
is not a sandbox, and the optional Docker backend does not make an unsafe image or daemon trusted.
Do not post vulnerabilities, credentials, private task contents, or unredacted local paths in an
issue. Follow `SECURITY.md` for private vulnerability reporting.

Only released versions and the current `main` branch receive routine support. Historical artifact
schemas remain readable where the compatibility documentation explicitly promises it.

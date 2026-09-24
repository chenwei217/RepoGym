# Security model

## Trust boundary

RepoGym treats task metadata, paths, and submission file trees as untrusted data, but the MVP
does **not** safely contain executable code. `LocalExecutor` starts the configured command with
`shell=False`, captures output with replacement decoding, and enforces a wall-clock timeout.
On timeout it uses `psutil` to terminate the exact child process and the descendants discovered
from that process, escalating from terminate to kill when necessary. The process nevertheless has
the invoking user's filesystem, network, process, and credential access. Process-tree cleanup is
not a security sandbox or an OS resource boundary.

Only run tasks and submissions you trust. For unknown code, use a disposable virtual machine or
a container runtime configured outside RepoGym with a read-only base, resource limits, no
secrets, restricted networking, and a dedicated unprivileged identity.

## Defensive controls

- task paths must be relative and cannot contain `..` or absolute/drive-qualified paths;
- submission preflight rejects links, detectable reparse points, special files, oversized files,
  sensitive filenames, case-conflicting paths, and files outside the declared allowed scope;
- starter, test, and accepted submission copies re-check links and special files while copying;
- reference patches cannot escape the workspace or alter declared forbidden paths;
- commands are tokenized and passed directly to `subprocess`, never to a shell;
- exact `python` and `python.exe` launchers are bound to `sys.executable`, preventing `PATH`
  precedence from silently selecting a different interpreter; explicitly configured absolute
  interpreter paths and other commands remain unchanged;
- timed-out local commands have their recorded process trees terminated without name-based kills;
- temporary workspaces are managed by the standard library and cleaned on exit;
- Jinja autoescaping protects the HTML report from task output injection.
- absolute paths are redacted consistently from persisted artifacts and all report formats;

The `doctor` command deliberately prints the resolved test executable path so operators can
confirm which interpreter it checked. Persisted run artifacts still redact that absolute path.

These controls prevent common accidental escapes and report injection. They are not a substitute
for OS-level isolation. A Docker executor is planned but not implemented.

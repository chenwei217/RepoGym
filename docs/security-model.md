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
- starter, test, and submission copies reject symbolic links and special files;
- reference patches cannot escape the workspace or alter declared forbidden paths;
- commands are tokenized and passed directly to `subprocess`, never to a shell;
- timed-out local commands have their recorded process trees terminated without name-based kills;
- temporary workspaces are managed by the standard library and cleaned on exit;
- Jinja autoescaping protects the HTML report from task output injection.

These controls prevent common accidental escapes and report injection. They are not a substitute
for OS-level isolation. A Docker executor is planned but not implemented.

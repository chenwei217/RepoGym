# Security model

## Trust boundary

RepoGym treats task metadata, paths, and submission file trees as untrusted data, but the MVP
does **not** safely contain executable code. `LocalExecutor` starts the configured command with
`shell=False`, captures output with replacement decoding, and enforces a wall-clock timeout.
Stdout and stderr are continuously drained into independent bounded head/tail buffers (1 MiB per
stream by default), with original byte counts and truncation flags retained as evidence. On
timeout RepoGym uses `psutil` to terminate the exact child process and the descendants discovered
from that process, escalating from terminate to kill when necessary. The process nevertheless
has the invoking user's filesystem, network, process, and credential access. These controls are
not a security sandbox or an OS resource boundary.

Only run tasks and submissions you trust with `LocalExecutor`. For unknown code, use a disposable
virtual machine or explicitly select RepoGym's Docker adapter with an independently hardened
daemon, reviewed image, no secrets, and any additional identity/runtime restrictions required by
your threat model.

## Defensive controls

- task paths must be relative and cannot contain `..` or absolute/drive-qualified paths;
- task scaffolding restricts IDs to lowercase hyphenated names, refuses existing targets, and
  validates in a same-filesystem staging tree before atomic publication;
- submission preflight rejects links, detectable reparse points, special files, oversized files,
  sensitive filenames, case-conflicting paths, and files outside the declared allowed scope;
- starter, test, and accepted submission copies re-check links and special files while copying;
- reference patches cannot escape the workspace or alter declared forbidden paths;
- commands, including Docker CLI commands, are tokenized and passed directly to `subprocess`,
  never to a shell;
- exact `python` and `python.exe` launchers are bound to `sys.executable`, preventing `PATH`
  precedence from silently selecting a different interpreter; explicitly configured absolute
  interpreter paths and other commands remain unchanged;
- timed-out and cooperatively cancelled commands have their recorded process trees terminated
  without name-based kills;
- process output is memory-bounded without stopping pipe drainage, including during timeout;
- temporary workspaces are managed by the standard library and cleaned on exit;
- Jinja autoescaping protects the HTML report from task output injection;
- absolute paths are redacted consistently from persisted artifacts and all report formats,
  including JUnit and SARIF; SARIF also re-redacts direct serializer input;
- pytest case evidence retains only stable IDs, status, duration, bounded sanitized failure
  summaries, and references to sanitized aggregate output; raw JUnit `system-out` is discarded;
- runtime snapshots use a fixed dependency allowlist and exclude environment variables,
  executable/home paths, usernames, hostnames, process IDs, and arbitrary package names;
- task bundle import rejects Zip Slip paths, links, name collisions, undeclared or oversized
  members, and integrity mismatches before atomically publishing a validated task;
- execution cache entries contain only already-sanitized run artifacts plus hashes, reject links
  and membership/hash mismatches, and are published by same-filesystem atomic rename;
- plugins are never selected implicitly; discovery failures and duplicate names are isolated,
  and report adapter input/output is redacted at the boundary.
- Docker execution is never implicit: it uses a read-only root, one writable workspace bind,
  `no-new-privileges`, bounded `/tmp`, resource/PID limits, and disabled networking by default;
  an unavailable CLI or daemon fails closed rather than falling back to local execution;
- batch manifests do not persist configured task/submission paths; job exceptions, embedded run
  snapshots, and all replay formats pass through the shared absolute-path redaction policy.

The `doctor` command deliberately prints the resolved test executable path so operators can
confirm which interpreter it checked. Persisted run artifacts still redact that absolute path.
Grading supplies both lexical and canonical temporary-workspace spellings to redaction so Windows
8.3 path aliases cannot degrade a workspace-relative command argument into an opaque host path.

These controls prevent common accidental escapes and report injection. Docker isolation is an
optional OS-level boundary enforced by the configured daemon, not by RepoGym itself. The writable
workspace, chosen image, daemon privileges, kernel/runtime vulnerabilities, and opt-in network
access remain operator-controlled risks; the feature does not make local execution a sandbox.

Cancellation is cooperative at the RepoGym API boundary: another thread or signal adapter must
call `CancellationToken.cancel()`. It is not an authorization boundary and cannot revoke files,
network operations, or other side effects completed before the process tree is stopped.

Cache locking prevents duplicate same-key execution but is not a sandbox or a distributed lock.
The key hashes interpreter and executor identity without persisting submission content or
environment variables. Anyone able to modify the cache directory can cause eviction or denial of
reuse; integrity validation prevents such changes from being silently trusted.

Plugins are also outside the data-only trust boundary. Python entry-point discovery imports and
executes package initialization in the RepoGym process, while task loader, executor, and reporter
methods run with the invoking user's full privileges. Protocol validation and report redaction
limit accidental incompatibility and disclosure; they do not contain malicious plugin code.
Install and invoke only reviewed plugins.

Batch execution does not reduce the trust required for tasks or submissions. A manifest may point
to any local path the process can read, and every cache miss runs candidate code with the selected
executor's privileges. Sequential execution limits implicit scheduling variability but is not a
resource or authorization boundary.

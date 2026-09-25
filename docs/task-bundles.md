# Reproducible task bundles

RepoGym package format version 1 is a ZIP file containing `manifest.json` and exactly the task
inputs used by the deterministic task fingerprint.

```bash
repogym bundle export tasks/python-cache-ttl python-cache-ttl.zip
mkdir imported-tasks
repogym bundle import python-cache-ttl.zip --destination imported-tasks
repogym verify imported-tasks/python-cache-ttl
```

Export validates the task first and refuses to overwrite an existing output. The manifest lists
files in lexical normalized-path order and records the task ID, task version, complete task
fingerprint, exporter Python/platform summary, and SHA-256 plus byte size for each file. It stores
no interpreter path, environment variable, credential, hostname, or user identity.

Import treats both names and bytes as untrusted. Before writing the final task directory it
rejects absolute paths, `..`, Windows drive paths, backslashes, NULs, directory and symbolic-link
members, duplicate or case-conflicting names, excessive counts and sizes, unexpected or missing
members, unsupported manifest schemas, and content mismatches. It then validates `task.yaml`, the
task layout, task version, and complete fingerprint in a temporary directory. Only a fully valid
task is atomically renamed into the destination, and an existing task is never replaced.

The package is a transport and integrity format, not a sandbox or signature format. A valid bundle
can still contain trusted executable task code; apply the same trust guidance as for an unpacked
task. Authenticity requires a separately trusted distribution channel or signature mechanism.

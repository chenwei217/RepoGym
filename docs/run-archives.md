# Portable execution evidence

Task bundles contain executable task definitions. Run archives contain sanitized execution
results and evidence and never execute task code.

```bash
repogym archive export .repogym/runs/RUN_ID run.zip
repogym archive verify run.zip
repogym archive import run.zip --destination .repogym/runs
repogym runs refresh
repogym report .repogym/runs/RUN_ID --format html --output report.html
```

Schema 1 uses a flat manifest with SHA-256 and byte sizes for the result, stdout/stderr, and
optional metadata, evidence, and changed-file inventory. ZIP timestamps and permissions are
normalized, so repeated exports of identical content produce identical bytes. Export filters
diagnostics again, drops unknown metadata fields, and updates output evidence digests. It never
modifies the source run. Old runs without metadata or evidence retain those missing capabilities.

Verification enforces exact membership and identity, strict versions, regular unencrypted files,
4 MiB per artifact, and 24 MiB total uncompressed data. It rejects path traversal, links, duplicates,
corruption, inconsistent evidence, and recognizable unredacted diagnostics. Checksums establish
integrity, not authenticity; an attacker can rewrite both a result and its manifest.

Import requires an existing non-linked destination. It validates before creating a staging tree,
locks the run ID, and atomically renames a fully written directory into place. Existing runs are
never replaced. A process crash may leave an `.import-RUN_ID.lock`; remove that one lock only after
confirming its owner has stopped, then retry. Invalid archives and publication conflicts return
exit code 10. Core tests use only local fixtures and need no network.

# Compatibility policy

RepoGym supports CPython 3.11 through 3.14 on Ubuntu and Windows. The declared
`requires-python = ">=3.11"` lower bound permits later CPython releases, but a new interpreter is
not part of the tested support matrix until CI covers it.

## Public surfaces

The documented CLI commands, numeric automation exit codes, versioned TaskSpec and batch schemas,
persisted run/evidence models, bundle manifests, and versioned plugin contracts are compatibility
surfaces. Readers reject unsupported future schema versions rather than guessing, and documented
legacy adapters remain covered by tests.

The import-level package root currently exposes only `repogym.__version__`. Python symbols used in
the README or dedicated API examples, including the executor contracts, are supported interfaces;
other implementation modules should be treated as internal unless documentation says otherwise.
The wheel includes `py.typed`, so type checkers can consume these inline annotations.

## Change policy

Run archive, catalog, and repeat-run analysis formats each use schema 1. New optional candidate
fingerprints preserve legacy result loading; missing historical identity is explicitly unknown.
Generated batch jobs may pin a task fingerprint without requiring it in existing schema-1 jobs.

RepoGym follows semantic versioning. During the 0.x series, a minor release may refine a documented
Python API, but persisted formats and CLI automation behavior require an explicit version or
migration path. Deprecations should appear in the CHANGELOG and remain usable for at least one
minor release when security or correctness does not require immediate removal.

Security fixes may tighten validation or reject previously accepted unsafe input without a
deprecation period. Such changes must retain a stable diagnostic and be called out in release notes.

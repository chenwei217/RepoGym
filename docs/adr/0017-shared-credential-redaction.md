# 0017: Shared credential filtering

## Problem and current behavior

Per-test failure summaries filtered some credentials, but captured stdout/stderr and old run replay
only shared path filtering. A task printing a credential could persist or display it elsewhere.

## Alternatives and decision

Filtering only exports leaves local artifacts exposed. Reading every environment variable to
build a secret inventory introduces another privacy risk. Add one deterministic text filter and
sensitive-key recognition at the existing shared persistence/report boundary. Do not collect
environment values. Keep the stricter opaque-string heuristic limited to failure summaries.

## External behavior and compatibility

Recognizable assignments, Bearer/Basic authentication, URL passwords, and private-key blocks become
`<REDACTED>` in new artifacts and replayed reports. Ordinary hashes, scores and test IDs survive.
This is best effort: unlabeled, encoded, split, or unknown credentials require upstream prevention.
Filtering changes displayed diagnostics but not execution, scores, or artifact schemas.

## Acceptance

Test structured keys, quoted values, multiline keys, idempotence, preserved hashes, new run
persistence, and all report formats over legacy raw artifacts using synthetic markers.

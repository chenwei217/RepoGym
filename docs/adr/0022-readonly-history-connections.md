# 0022: Enforced read-only history queries

## Problem and current behavior

History queries reject missing indexes, but an existing empty SQLite file still enters schema
initialization. Query connections are writable. Tests also used SQLite transaction contexts
without closing the connections, causing delayed ResourceWarning messages on Python 3.14.

## Alternatives and decision

Relying on convention leaves a read command able to mutate a selected database. Open query/show
connections with SQLite URI `mode=ro`, refuse uninitialized indexes, and reserve schema creation
for explicit refresh. Refresh rejects nonempty unversioned databases instead of adopting unrelated
tables. Use explicit closing contexts in tests while retaining transaction contexts.

## Compatibility and acceptance

Existing schema-1 indexes remain readable. Missing/empty/foreign databases produce stable history
errors and remain unchanged. Test actual write rejection, empty-file byte preservation, foreign
table preservation, URI escaping for spaces/#, and connection-resource warnings.

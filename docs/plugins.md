# Plugin development

RepoGym plugin API version 1 supports task loaders, execution backends, and report renderers. A
package may implement one or more roles in a single immutable registration. Plugins are opt-in:
installation and discovery never replace a built-in implementation automatically.

## Registration and discovery

Expose a `PluginRegistration` object from your package:

```toml
[project.entry-points."repogym.plugins"]
text-summary = "my_repogym_plugin:registration"
```

```python
from repogym.plugins import PLUGIN_API_VERSION, PluginRegistration

registration = PluginRegistration(
    name="text-summary",
    api_version=PLUGIN_API_VERSION,
    reporter=TextSummaryReporter(),
)
```

Names use lowercase letters, digits, and single hyphens. Registrations must declare API version
1 and provide at least one role. `repogym plugins` lists accepted registrations alongside load,
compatibility, protocol, and name-conflict diagnostics. Discovery order is deterministic; if two
packages claim the same registration name, the first sorted entry point is retained and the
other is rejected.

The complete minimal reporter is in
[`examples/plugins/minimal_plugin.py`](../examples/plugins/minimal_plugin.py).

## Stable boundaries

- `TaskLoaderPlugin.load_task(PluginTaskLoadRequest)` returns a mapping. RepoGym applies schema
  migration, strict TaskSpec validation, and the directory-ID invariant after the plugin returns.
- `ExecutorBackendPlugin.execute(PluginExecutionRequest)` returns a
  `PluginExecutionResponse`. The request contains immutable argv, working directory, timeout, and
  a read-only cancellation signal. `PluginExecutorAdapter` converts the response to the internal
  execution model and derives byte counts when omitted.
- `ReporterPlugin.render(PluginReportRequest)` returns text. RepoGym supplies a serialization-
  shaped result mapping and sanitized stdout/stderr, then redacts returned text again.

Use `discover_plugins()` and select a registration explicitly. Then call
`load_task_with_plugin`, construct `PluginExecutorAdapter`, or call `render_with_plugin`. An
explicitly selected extension that raises or returns the wrong type produces `PluginError`; other
discovered plugins and built-in commands continue to work.

## Trust and compatibility

Plugins run in the RepoGym process with the invoking user's privileges. Entry-point discovery
imports plugin code, and an executor plugin launches or delegates code according to its own
implementation. Install only reviewed plugins; the protocol is an interoperability boundary, not
a sandbox.

API version compatibility is exact. Plugins should import the public DTOs and protocols from
`repogym.plugins`, avoid internal modules, and declare their supported RepoGym release range in
package metadata. A future incompatible protocol will use a new API version rather than silently
changing version 1.

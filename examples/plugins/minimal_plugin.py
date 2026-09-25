"""Minimal RepoGym reporter plugin used by the extension documentation."""

from repogym.plugins import (
    PLUGIN_API_VERSION,
    PluginRegistration,
    PluginReportRequest,
)


class TextSummaryReporter:
    def render(self, request: PluginReportRequest) -> str:
        return f"{request.result['task_id']}: {request.result['score']}/100\n"


registration = PluginRegistration(
    name="text-summary",
    api_version=PLUGIN_API_VERSION,
    reporter=TextSummaryReporter(),
)

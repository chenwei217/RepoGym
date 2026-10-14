"""Offline repeated-run analysis over explicitly comparable observations."""

from repogym.analytics.cohorts import analyze_runs
from repogym.analytics.models import AnalysisError, AnalysisReport
from repogym.analytics.reporting import render_analysis

__all__ = ["AnalysisError", "AnalysisReport", "analyze_runs", "render_analysis"]

"""Bounded result loading, identity checks, grouping, and sample exclusions."""

import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from collections.abc import Sequence
from pathlib import Path

from repogym.analytics.models import AnalysisError, AnalysisReport, CohortKey, CohortStats, RunIssue
from repogym.analytics.statistics import case_statistics, measured_execution, summarize
from repogym.exceptions import RepoGymError
from repogym.history.models import RunSummary
from repogym.history.scan import linked, read_json_bytes
from repogym.models import GradeResult
from repogym.security import redact_value

MAX_RUNS = 200
MAX_INPUT_BYTES = 64 * 1024 * 1024


def analyze_runs(paths: Sequence[Path], *, include_cached: bool = False) -> AnalysisReport:
    """Compare only equal task/candidate/environment identities; never read captured output."""
    if not 1 <= len(paths) <= MAX_RUNS:
        raise AnalysisError(f"Analysis requires between 1 and {MAX_RUNS} run directories")
    loaded: dict[str, dict[str, GradeResult]] = defaultdict(dict)
    issues: list[RunIssue] = []
    total_bytes = 0
    for path in paths:
        label = (
            path.name
            if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,159}", path.name)
            else "invalid-run"
        )
        try:
            if linked(path) or not path.is_dir():
                raise ValueError("Run must be a non-linked directory")
            content = read_json_bytes(path / "result.json")
            total_bytes += len(content)
            if total_bytes > MAX_INPUT_BYTES:
                raise AnalysisError("Analysis exceeds total input byte limit")
            result = GradeResult.model_validate(redact_value(json.loads(content), [path.resolve()]))
            if result.run_id != path.name:
                raise ValueError("Run identity mismatch")
            RunSummary(
                run_id=result.run_id,
                task_id=result.task_id,
                score=result.score,
                status=result.status,
                passed=result.tests.passed,
                failed=result.tests.failed,
                task_fingerprint=result.task_fingerprint,
                duration_seconds=result.duration_seconds,
                result_sha256=hashlib.sha256(content).hexdigest(),
            )
            if any(not math.isfinite(c.duration_seconds) for c in result.test_evidence.cases):
                raise ValueError("Invalid per-case measurement")
            digest = hashlib.sha256(content).hexdigest()
            if digest in loaded[result.run_id]:
                issues.append(RunIssue(run_id=result.run_id, code="duplicate_run"))
            loaded[result.run_id][digest] = result
        except AnalysisError:
            raise
        except (OSError, RepoGymError, ValueError):
            issues.append(RunIssue(run_id=label, code="invalid_artifact"))

    groups: dict[CohortKey, list[GradeResult]] = defaultdict(list)
    for run_id, variants in sorted(loaded.items()):
        if len(variants) > 1:
            issues.append(RunIssue(run_id=run_id, code="conflicting_run_id"))
            continue
        result = next(iter(variants.values()))
        if result.task_fingerprint is None:
            issues.append(RunIssue(run_id=run_id, code="task_identity_unavailable"))
        elif result.candidate_fingerprint is None:
            issues.append(RunIssue(run_id=run_id, code="candidate_identity_unavailable"))
        elif result.environment.fingerprint is None:
            issues.append(RunIssue(run_id=run_id, code="environment_unavailable"))
        elif result.cache is not None and result.cache.hit and not include_cached:
            issues.append(RunIssue(run_id=run_id, code="cache_replay"))
        else:
            key = (
                result.task_id,
                result.task_fingerprint,
                result.candidate_fingerprint,
                result.environment.fingerprint,
            )
            groups[key].append(result)

    cohorts: list[CohortStats] = []
    for key, runs in sorted(groups.items()):
        scores = summarize(run.score for run in runs)
        if scores is None:
            raise AnalysisError("Cannot summarize an empty cohort")
        warnings = []
        if len(runs) < 2:
            warnings.append("insufficient_repetitions")
        if any(run.test_evidence.availability != "available" for run in runs):
            warnings.append("per_test_evidence_unavailable")
        cohorts.append(
            CohortStats(
                task_id=key[0],
                task_fingerprint=key[1],
                candidate_fingerprint=key[2],
                environment_fingerprint=key[3],
                run_ids=[run.run_id for run in runs],
                run_count=len(runs),
                status_counts=dict(sorted(Counter(r.status for r in runs).items())),
                perfect_score_rate=round(
                    sum(r.score == 100 and r.status == "completed" for r in runs) / len(runs), 6
                ),
                scores=scores,
                duration_seconds=summarize(
                    r.duration_seconds for r in runs if measured_execution(r)
                ),
                cases=case_statistics(runs),
                warnings=warnings,
            )
        )
    unique_issues = {(issue.run_id, issue.code): issue for issue in issues}
    return AnalysisReport(
        cohorts=cohorts, excluded=[unique_issues[k] for k in sorted(unique_issues)]
    )

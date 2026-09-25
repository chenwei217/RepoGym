"""Stable process exit codes for RepoGym automation."""

from enum import IntEnum


class ExitCode(IntEnum):
    """Public CLI outcome contract; values must remain stable."""

    SUCCESS = 0
    TASK_INVALID = 10
    EXECUTION_FAILED = 20
    SCORE_NOT_PASSED = 30
    ENVIRONMENT_ERROR = 40
    INTERNAL_ERROR = 70

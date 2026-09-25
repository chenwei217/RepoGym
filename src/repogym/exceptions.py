"""Domain exceptions used to produce concise CLI errors."""


class RepoGymError(Exception):
    """Base class for expected RepoGym failures."""


class TaskLoadError(RepoGymError):
    """Raised when a task specification cannot be loaded."""


class ValidationError(RepoGymError):
    """Raised when a task directory is invalid."""


class ExecutionError(RepoGymError):
    """Raised when a configured task execution cannot satisfy its contract."""


class FingerprintError(RepoGymError):
    """Raised when a complete deterministic task fingerprint cannot be computed."""


class SecurityError(RepoGymError):
    """Raised when an unsafe path or file is encountered."""


class PatchError(RepoGymError):
    """Raised when a reference patch cannot be safely applied."""


class ReportError(RepoGymError):
    """Raised when a run report is incomplete or invalid."""


class BundleError(RepoGymError):
    """Raised when a portable task bundle cannot be created or imported."""


class CacheError(RepoGymError):
    """Raised when an execution cache cannot be accessed safely."""


class PluginError(RepoGymError):
    """Raised when an explicitly selected plugin violates its contract."""

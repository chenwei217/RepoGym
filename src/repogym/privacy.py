"""Best-effort credential filtering for untrusted diagnostic text."""

import re

REDACTED = "<REDACTED>"
_KEY_NAMES = (
    r"(?:password|passwd|secret|token|api[_-]?key|(?:access|auth|refresh)[_-]?token|"
    r"client[_-]?secret|aws[_-]secret[_-]access[_-]key)"
)
_KEY = re.compile(rf"(?i)^{_KEY_NAMES}$")
_ASSIGNMENT = re.compile(
    rf"(?i)(\b{_KEY_NAMES}\b[\"']?\s*[:=]\s*)"
    r"(?:\"[^\"\r\n]*\"|'[^'\r\n]*'|[^\s,;&\"'<>]+)"
)
_AUTHORIZATION = re.compile(r"(?i)\b(Bearer|Basic)\s+[A-Za-z0-9._~+/=-]+")
_URL_PASSWORD = re.compile(r"(?i)(https?://)[^\s/:@]+:[^\s/@]+@")
_PRIVATE_KEY = re.compile(
    r"-----BEGIN (?:[A-Z0-9]+ )?PRIVATE KEY-----.*?"
    r"(?:-----END (?:[A-Z0-9]+ )?PRIVATE KEY-----|\Z)",
    re.DOTALL,
)


def sensitive_key(key: str) -> bool:
    """Recognize credential field names, preserving unrelated metadata keys."""
    return _KEY.fullmatch(key) is not None


def redact_credentials(text: str) -> str:
    """Remove recognizable credentials without collecting environment variable values.

    This cannot identify arbitrary unlabeled secrets. It intentionally preserves ordinary opaque
    strings such as fingerprints rather than guessing that all hashes are credentials.
    """
    text = _PRIVATE_KEY.sub(REDACTED, text)
    text = _URL_PASSWORD.sub(r"\1<REDACTED>@", text)
    text = _AUTHORIZATION.sub(r"\1 <REDACTED>", text)
    return _ASSIGNMENT.sub(r"\1<REDACTED>", text)

import json

import pytest

from repogym.privacy import redact_credentials, sensitive_key
from repogym.security import redact_sensitive_text, redact_value


@pytest.mark.parametrize(
    "template",
    [
        "api_key={}",
        '"password": "{}"',
        "refresh-token='{}'",
        "Authorization: Bearer {}",
        "Proxy-Authorization: Basic {}",
        "https://unit:{}@example.test/data",
        "-----BEGIN RSA PRIVATE KEY-----\n{}\n-----END RSA PRIVATE KEY-----",
        "-----BEGIN PRIVATE KEY-----\n{}",
        "client_secret={}",
        "AWS_SECRET_ACCESS_KEY={}",
    ],
)
def test_recognized_credentials_and_idempotence(template: str) -> None:
    marker = "fixture" + "credential42"
    original = template.format(marker)
    filtered = redact_credentials(original)
    assert marker not in filtered
    assert "<REDACTED>" in filtered
    assert redact_credentials(filtered) == filtered
    assert marker not in redact_sensitive_text(original)


def test_nested_sensitive_keys_are_removed_without_changing_input() -> None:
    marker = "fixture" + "credential42"
    original = {"nested": [{"API_KEY": marker, "value": "normal"}], "score": 100}
    safe = redact_value(original)
    assert marker not in json.dumps(safe)
    assert safe["nested"][0]["value"] == "normal"
    assert original["nested"][0]["API_KEY"] == marker
    assert sensitive_key("password")
    assert not sensitive_key("task_fingerprint")


def test_ordinary_text_and_fingerprints_are_preserved() -> None:
    text = "8 passed; task_fingerprint=" + "a" * 64 + "; key ordering and token count"
    assert redact_credentials(text) == text
    assert redact_credentials("token=<REDACTED>") == "token=<REDACTED>"

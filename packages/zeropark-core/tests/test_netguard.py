import pytest

from zeropark_core.netguard import BlockedURLError, validate_public_url


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/admin",
        "http://127.1/",                  # decimal shorthand bypass
        "http://169.254.169.254/latest/meta-data/",
        "http://10.0.0.5/internal",
        "http://192.168.1.1/router",
        "http://[::1]/",
        "ftp://example.com/file",          # disallowed scheme
        "file:///etc/passwd",
    ],
)
def test_blocked_urls(url, monkeypatch):
    monkeypatch.delenv("ZEROPARK_ALLOW_PRIVATE_URLS", raising=False)
    with pytest.raises(BlockedURLError):
        validate_public_url(url)


def test_public_literal_ip_allowed(monkeypatch):
    monkeypatch.delenv("ZEROPARK_ALLOW_PRIVATE_URLS", raising=False)
    assert validate_public_url("http://93.184.216.34/") == "http://93.184.216.34/"


def test_override_allows_private(monkeypatch):
    monkeypatch.setenv("ZEROPARK_ALLOW_PRIVATE_URLS", "1")
    assert validate_public_url("http://127.0.0.1/dev") == "http://127.0.0.1/dev"

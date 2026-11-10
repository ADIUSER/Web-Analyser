import socket

import pytest

from app.services.url_validator import URLValidationError, normalize_url, validate_url


def _answers(*ips):
    return [
        (socket.AF_INET if ":" not in ip else socket.AF_INET6, socket.SOCK_STREAM, 6, "", (ip, 443, 0, 0) if ":" in ip else (ip, 443))
        for ip in ips
    ]


def test_valid_public_url_is_normalized_and_dns_is_returned():
    result = validate_url("HTTPS://Example.COM/#top", resolver=lambda *_args, **_kw: _answers("93.184.216.34"))
    assert result.url == "https://example.com/"
    assert result.hostname == "example.com"
    assert result.addresses == ("93.184.216.34",)


def test_normalize_removes_fragment_and_default_port():
    assert normalize_url("https://Example.com:443/a?q=1#part") == "https://example.com/a?q=1"


@pytest.mark.parametrize("url", [
    "file:///etc/passwd",
    "ftp://example.com/",
    "https://user:secret@example.com/",
    "http://localhost/",
    "http://sub.local/",
    "https://example.com:8443/",
    "not a URL",
])
def test_rejects_unsupported_or_unsafe_url(url):
    with pytest.raises(URLValidationError):
        validate_url(url, resolver=lambda *_args, **_kw: _answers("93.184.216.34"))


@pytest.mark.parametrize("url", [
    "http://127.0.0.1/",
    "http://10.0.0.7/",
    "http://169.254.1.4/",
    "http://192.168.1.2/",
])
def test_rejects_non_public_ip_literals(url):
    with pytest.raises(URLValidationError):
        validate_url(url)


def test_rejects_mixed_public_and_private_dns_answers():
    with pytest.raises(URLValidationError, match="private or restricted"):
        validate_url("https://example.com", resolver=lambda *_args, **_kw: _answers("93.184.216.34", "10.0.0.1"))


def test_reports_dns_failure_as_validation_error():
    def fail(*_args, **_kwargs):
        raise socket.gaierror("name not known")
    with pytest.raises(URLValidationError, match="could not be resolved"):
        validate_url("https://example.com", resolver=fail)

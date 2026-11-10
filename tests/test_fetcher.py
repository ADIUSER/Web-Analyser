from types import SimpleNamespace

import pytest
import requests

from app.services import fetcher as fetcher_module
from app.services.fetcher import FetchError, ResponseTooLarge, SafeFetcher
from app.services.url_validator import URLValidationError, ValidatedURL


class FakeResponse:
    def __init__(self, status_code=200, headers=None, chunks=None):
        self.status_code = status_code
        self.headers = headers or {"Content-Type": "text/html", "Content-Length": "2"}
        self._chunks = chunks or [b"ok"]
        self.closed = False

    def iter_content(self, chunk_size=8192):
        yield from self._chunks

    def close(self):
        self.closed = True


class FakeSession:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.headers = {}
        self.trust_env = True
        self.mounted = {}
        self.closed = False

    def mount(self, prefix, adapter):
        self.mounted[prefix] = adapter

    def request(self, *args, **kwargs):
        assert kwargs["verify"] is True
        assert kwargs["allow_redirects"] is False
        if self.error:
            raise self.error
        return self.response

    def close(self):
        self.closed = True


def _validated(url, **_kwargs):
    if "127.0.0.1" in url or "localhost" in url:
        raise URLValidationError("The website resolves to a private or restricted IP address.")
    return ValidatedURL(url, "https", "example.com", 443, ("93.184.216.34",))


def test_fetcher_revalidates_redirect_destination(monkeypatch):
    redirect = FakeResponse(302, {"Location": "http://127.0.0.1/admin", "Content-Type": "text/html"}, [])
    monkeypatch.setattr(fetcher_module, "validate_url", _validated)
    monkeypatch.setattr(requests, "Session", lambda: FakeSession(response=redirect))
    fetcher = SafeFetcher({"REQUEST_DELAY_SECONDS": 0, "MAX_REDIRECTS": 3, "ALLOWED_HTTP_PORTS": (80,), "ALLOWED_HTTPS_PORTS": (443,)})
    with pytest.raises(FetchError, match="private or restricted"):
        fetcher.fetch("https://example.com/")
    assert redirect.closed


def test_fetcher_enforces_content_length_limit(monkeypatch):
    response = FakeResponse(200, {"Content-Type": "text/html", "Content-Length": "1000"}, [b"x" * 1000])
    monkeypatch.setattr(fetcher_module, "validate_url", _validated)
    monkeypatch.setattr(requests, "Session", lambda: FakeSession(response=response))
    fetcher = SafeFetcher({"REQUEST_DELAY_SECONDS": 0, "MAX_RESPONSE_BYTES": 10, "ALLOWED_HTTP_PORTS": (80,), "ALLOWED_HTTPS_PORTS": (443,)})
    with pytest.raises(ResponseTooLarge):
        fetcher.fetch("https://example.com/")
    assert response.closed


def test_fetcher_translates_request_timeout(monkeypatch):
    monkeypatch.setattr(fetcher_module, "validate_url", _validated)
    monkeypatch.setattr(requests, "Session", lambda: FakeSession(error=requests.exceptions.Timeout()))
    fetcher = SafeFetcher({"REQUEST_DELAY_SECONDS": 0, "ALLOWED_HTTP_PORTS": (80,), "ALLOWED_HTTPS_PORTS": (443,)})
    with pytest.raises(FetchError, match="timed out"):
        fetcher.fetch("https://example.com/")

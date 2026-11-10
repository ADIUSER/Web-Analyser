"""Bounded HTTP fetching with SSRF checks, redirect validation, and DNS pinning."""
from __future__ import annotations

import functools
import socket
import time
import threading
from dataclasses import dataclass
from urllib.parse import urljoin

import requests
from requests.adapters import HTTPAdapter
from urllib3.connection import HTTPConnection, HTTPSConnection
from urllib3.connectionpool import HTTPConnectionPool, HTTPSConnectionPool
from urllib3.exceptions import ConnectTimeoutError, NewConnectionError, NameResolutionError
from urllib3.poolmanager import PoolManager
from urllib3.util import connection as urllib3_connection

from .url_validator import URLValidationError, ValidatedURL, normalize_url, validate_url


class FetchError(RuntimeError):
    """Safe, user-displayable fetch failure; detailed exceptions are logged upstream."""


class ResponseTooLarge(FetchError):
    pass


class UnsupportedContentType(FetchError):
    pass


@dataclass
class FetchResult:
    requested_url: str
    final_url: str
    status_code: int
    headers: dict
    body: bytes
    response_time_ms: float
    response_size_bytes: int
    redirect_count: int
    content_type: str


class _PinnedHTTPConnection(HTTPConnection):
    def __init__(self, *args, pinned_ip: str, **kwargs):
        self._pinned_ip = pinned_ip
        super().__init__(*args, **kwargs)

    def _new_conn(self):
        try:
            return urllib3_connection.create_connection(
                (self._pinned_ip, self.port),
                self.timeout,
                source_address=self.source_address,
                socket_options=self.socket_options,
            )
        except socket.gaierror as exc:
            raise NameResolutionError(self.host, self, exc) from exc
        except (socket.timeout, TimeoutError) as exc:
            raise ConnectTimeoutError(self, f"Connection to {self.host} timed out") from exc
        except OSError as exc:
            raise NewConnectionError(self, f"Could not connect to the validated destination: {exc}") from exc


class _PinnedHTTPSConnection(HTTPSConnection):
    def __init__(self, *args, pinned_ip: str, **kwargs):
        self._pinned_ip = pinned_ip
        super().__init__(*args, **kwargs)

    def _new_conn(self):
        try:
            return urllib3_connection.create_connection(
                (self._pinned_ip, self.port),
                self.timeout,
                source_address=self.source_address,
                socket_options=self.socket_options,
            )
        except socket.gaierror as exc:
            raise NameResolutionError(self.host, self, exc) from exc
        except (socket.timeout, TimeoutError) as exc:
            raise ConnectTimeoutError(self, f"Connection to {self.host} timed out") from exc
        except OSError as exc:
            raise NewConnectionError(self, f"Could not connect to the validated destination: {exc}") from exc


def _make_pinned_pool_classes(pinned_ip: str):
    class PinnedHTTPPool(HTTPConnectionPool):
        ConnectionCls = staticmethod(functools.partial(_PinnedHTTPConnection, pinned_ip=pinned_ip))

    class PinnedHTTPSPool(HTTPSConnectionPool):
        ConnectionCls = staticmethod(functools.partial(_PinnedHTTPSConnection, pinned_ip=pinned_ip))

    return {"http": PinnedHTTPPool, "https": PinnedHTTPSPool}


class _PinnedPoolManager(PoolManager):
    def __init__(self, *args, pool_classes_by_scheme, **kwargs):
        super().__init__(*args, **kwargs)
        self.pool_classes_by_scheme = pool_classes_by_scheme


class _PinnedHTTPAdapter(HTTPAdapter):
    def __init__(self, pinned_ip: str):
        self._pool_classes = _make_pinned_pool_classes(pinned_ip)
        super().__init__(max_retries=0, pool_connections=1, pool_maxsize=1, pool_block=True)

    def init_poolmanager(self, connections, maxsize, block=False, **pool_kwargs):
        self.poolmanager = _PinnedPoolManager(
            num_pools=connections,
            maxsize=maxsize,
            block=block,
            pool_classes_by_scheme=self._pool_classes,
            **pool_kwargs,
        )


class SafeFetcher:
    """Fetch only public websites, pinning each validated hostname to a public IP."""

    REDIRECT_CODES = {301, 302, 303, 307, 308}
    HTML_TYPES = {"text/html", "application/xhtml+xml"}

    def __init__(self, config):
        self.config = config
        self._host_last_request = {}
        self._rate_limit_lock = threading.Lock()
        self.timeout = (
            float(config.get("REQUEST_CONNECT_TIMEOUT_SECONDS", 5)),
            float(config.get("REQUEST_READ_TIMEOUT_SECONDS", 10)),
        )

    def _validate(self, url: str) -> ValidatedURL:
        return validate_url(
            url,
            allowed_http_ports=tuple(self.config.get("ALLOWED_HTTP_PORTS", (80,))),
            allowed_https_ports=tuple(self.config.get("ALLOWED_HTTPS_PORTS", (443,))),
        )

    def _new_session(self, validated: ValidatedURL) -> requests.Session:
        session = requests.Session()
        # Never honor caller-controlled or host-environment proxy variables.
        session.trust_env = False
        session.headers.update({
            "User-Agent": self.config.get("USER_AGENT", "PortfolioWebsiteAnalyzer/1.0"),
            "Accept": "text/html,application/xhtml+xml;q=0.9,text/plain;q=0.5,*/*;q=0.1",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "close",
        })
        pinned_ip = validated.addresses[0]
        adapter = _PinnedHTTPAdapter(pinned_ip)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        return session

    def _respect_delay(self, hostname: str):
        delay = max(0.0, float(self.config.get("REQUEST_DELAY_SECONDS", 0.25)))
        with self._rate_limit_lock:
            now = time.monotonic()
            remaining = delay - (now - self._host_last_request.get(hostname, 0.0))
            if remaining > 0:
                time.sleep(remaining)
            self._host_last_request[hostname] = time.monotonic()

    def fetch(
        self,
        url: str,
        *,
        method: str = "GET",
        max_bytes: int | None = None,
        accepted_types=None,
        allow_non_html: bool = False,
    ) -> FetchResult:
        if method not in {"GET", "HEAD"}:
            raise FetchError("Only GET and HEAD requests are supported.")
        requested_url = url
        current_url = normalize_url(url, tuple(self.config.get("ALLOWED_HTTP_PORTS", (80,))), tuple(self.config.get("ALLOWED_HTTPS_PORTS", (443,))))
        max_bytes = int(max_bytes or self.config.get("MAX_RESPONSE_BYTES", 2_000_000))
        accepted_types = set(accepted_types or self.HTML_TYPES)
        max_redirects = int(self.config.get("MAX_REDIRECTS", 5))
        total_start = time.monotonic()
        redirect_count = 0

        while True:
            try:
                validated = self._validate(current_url)
            except URLValidationError as exc:
                raise FetchError(str(exc)) from exc

            session = self._new_session(validated)
            response = None
            try:
                self._respect_delay(validated.hostname)
                response = session.request(
                    method,
                    validated.url,
                    timeout=self.timeout,
                    allow_redirects=False,
                    stream=True,
                    verify=True,
                )
                if response.status_code in self.REDIRECT_CODES:
                    location = response.headers.get("Location")
                    if not location:
                        raise FetchError("The website returned a redirect without a destination.")
                    if redirect_count >= max_redirects:
                        raise FetchError("The website exceeded the redirect limit.")
                    # Redirect destination gets parsed, DNS-checked, and pinned on next loop.
                    current_url = urljoin(validated.url, location)
                    redirect_count += 1
                    continue

                content_type = response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
                if not allow_non_html and response.status_code < 400 and content_type not in accepted_types:
                    raise UnsupportedContentType("The destination did not return a supported HTML response.")

                content_length = response.headers.get("Content-Length")
                if content_length and method != "HEAD":
                    try:
                        if int(content_length) > max_bytes:
                            raise ResponseTooLarge("The response is larger than the configured size limit.")
                    except ValueError:
                        pass

                body_parts = []
                size = 0
                if method != "HEAD":
                    for chunk in response.iter_content(chunk_size=16_384):
                        if not chunk:
                            continue
                        size += len(chunk)
                        if size > max_bytes:
                            raise ResponseTooLarge("The response is larger than the configured size limit.")
                        body_parts.append(chunk)
                body = b"".join(body_parts)
                return FetchResult(
                    requested_url=requested_url,
                    final_url=validated.url,
                    status_code=response.status_code,
                    headers=dict(response.headers),
                    body=body,
                    response_time_ms=(time.monotonic() - total_start) * 1000,
                    response_size_bytes=size,
                    redirect_count=redirect_count,
                    content_type=content_type,
                )
            except requests.exceptions.SSLError as exc:
                raise FetchError("TLS certificate verification failed for this website.") from exc
            except requests.exceptions.Timeout as exc:
                raise FetchError("The website request timed out.") from exc
            except requests.exceptions.TooManyRedirects as exc:
                raise FetchError("The website exceeded the redirect limit.") from exc
            except requests.exceptions.ConnectionError as exc:
                raise FetchError("The website could not be reached.") from exc
            except requests.exceptions.RequestException as exc:
                raise FetchError("The website request failed.") from exc
            finally:
                if response is not None:
                    response.close()
                session.close()

    def check_link(self, url: str) -> tuple[int | None, str]:
        """Check a link with HEAD, falling back to a bounded GET for common HEAD failures."""
        try:
            head = self.fetch(url, method="HEAD", allow_non_html=True, max_bytes=1024)
            status = head.status_code
            if status not in {400, 403, 405, 501}:
                return status, _status_label(status)
        except (FetchError, URLValidationError):
            # Try GET once below. Any failed or unsafe GET is reported as unknown.
            pass
        try:
            get_result = self.fetch(url, method="GET", allow_non_html=True, max_bytes=64 * 1024)
            return get_result.status_code, _status_label(get_result.status_code)
        except (FetchError, URLValidationError):
            return None, "unknown"


def _status_label(status: int) -> str:
    if 200 <= status < 400:
        return "reachable"
    if status in {404, 410}:
        return "broken"
    if status >= 400:
        return "http_error"
    return "unknown"

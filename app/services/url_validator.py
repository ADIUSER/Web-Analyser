"""Strict URL validation and DNS safety checks used before every outbound request."""
from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import SplitResult, urlsplit, urlunsplit


class URLValidationError(ValueError):
    """Raised when a URL is malformed or does not point to a public web host."""


@dataclass(frozen=True)
class ValidatedURL:
    url: str
    scheme: str
    hostname: str
    port: int
    addresses: tuple[str, ...]


def _is_public_ip(value: str) -> bool:
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return False
    # is_global excludes private, loopback, link-local, multicast, unspecified,
    # reserved and other non-routable special-use ranges.
    return bool(address.is_global)


def _canonical_host(hostname: str) -> str:
    hostname = hostname.rstrip(".").lower()
    if not hostname:
        raise URLValidationError("Please enter a URL with a hostname.")
    try:
        # Canonicalize internationalized domain names before DNS validation.
        return hostname.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise URLValidationError("The hostname is invalid.") from exc


def _parse_url(raw_url: str, allowed_http_ports=(80,), allowed_https_ports=(443,)) -> tuple[SplitResult, str, int]:
    if not isinstance(raw_url, str):
        raise URLValidationError("Please enter a valid website URL.")
    raw_url = raw_url.strip()
    if not raw_url or len(raw_url) > 2048:
        raise URLValidationError("Enter a URL between 1 and 2048 characters.")
    if any(ord(char) < 32 or ord(char) == 127 for char in raw_url):
        raise URLValidationError("The URL contains unsupported control characters.")
    try:
        parsed = urlsplit(raw_url)
    except ValueError as exc:
        raise URLValidationError("The URL could not be parsed.") from exc

    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"}:
        raise URLValidationError("Only HTTP and HTTPS website URLs are supported.")
    if not parsed.netloc or not parsed.hostname:
        raise URLValidationError("Include a hostname, for example https://example.com.")
    if parsed.username is not None or parsed.password is not None or "@" in parsed.netloc:
        raise URLValidationError("URLs containing username or password credentials are not allowed.")
    try:
        explicit_port = parsed.port
        port = explicit_port if explicit_port is not None else (443 if scheme == "https" else 80)
    except ValueError as exc:
        raise URLValidationError("The URL contains an invalid port.") from exc
    allowed_ports = allowed_https_ports if scheme == "https" else allowed_http_ports
    if port not in allowed_ports:
        expected = "443" if scheme == "https" else "80"
        raise URLValidationError(f"For safety, {scheme.upper()} URLs must use port {expected}.")
    if parsed.fragment:
        parsed = parsed._replace(fragment="")
    host = _canonical_host(parsed.hostname)
    # Reject common local-only names even before DNS resolution.
    if host == "localhost" or host.endswith((".localhost", ".local", ".internal", ".test")):
        raise URLValidationError("Local and internal hostnames cannot be scanned.")
    return parsed, host, port


def normalize_url(raw_url: str, allowed_http_ports=(80,), allowed_https_ports=(443,)) -> str:
    """Normalize a URL for crawl deduplication; DNS safety is checked separately."""
    parsed, host, port = _parse_url(raw_url, allowed_http_ports, allowed_https_ports)
    scheme = parsed.scheme.lower()
    is_ipv6 = ":" in host
    netloc_host = f"[{host}]" if is_ipv6 else host
    default_port = 443 if scheme == "https" else 80
    netloc = netloc_host if port == default_port else f"{netloc_host}:{port}"
    path = parsed.path or "/"
    return urlunsplit((scheme, netloc, path, parsed.query, ""))


def validate_url(
    raw_url: str,
    *,
    resolver=socket.getaddrinfo,
    allowed_http_ports=(80,),
    allowed_https_ports=(443,),
) -> ValidatedURL:
    """Parse URL, resolve all addresses, and reject if any is not globally routable.

    The chosen public address is later pinned by the HTTP adapter, avoiding a second
    DNS lookup at connection time. Rejecting mixed public/private DNS answers is
    intentionally conservative.
    """
    parsed, hostname, port = _parse_url(raw_url, allowed_http_ports, allowed_https_ports)
    scheme = parsed.scheme.lower()

    try:
        literal_ip = ipaddress.ip_address(hostname)
        resolved = [str(literal_ip)]
    except ValueError:
        try:
            answers = resolver(hostname, port, type=socket.SOCK_STREAM)
        except (socket.gaierror, OSError) as exc:
            raise URLValidationError("The website hostname could not be resolved.") from exc
        resolved = []
        for answer in answers:
            try:
                address = str(ipaddress.ip_address(answer[4][0].split("%", 1)[0]))
            except (ValueError, IndexError, TypeError):
                continue
            if address not in resolved:
                resolved.append(address)

    if not resolved:
        raise URLValidationError("The website hostname did not resolve to an IP address.")
    unsafe = [address for address in resolved if not _is_public_ip(address)]
    if unsafe:
        raise URLValidationError("The website resolves to a private or restricted IP address.")
    normalized = normalize_url(raw_url, allowed_http_ports, allowed_https_ports)
    # Keep the resolved address list; fetcher pins the actual TCP connection to one.
    return ValidatedURL(
        url=normalized,
        scheme=scheme,
        hostname=hostname,
        port=port,
        addresses=tuple(resolved),
    )

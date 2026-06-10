"""SSRF guard: validate that a URL targets a public host before fetching.

String blacklists ("localhost", "169.254...") are trivially bypassed (127.1,
decimal IPs, DNS rebinding aliases). This module resolves the hostname and
rejects any address in a private, loopback, link-local, or otherwise
non-global range. Engines that fetch user-supplied URLs (crawl, browse) call
`validate_public_url` before connecting.

Set ZEROPARK_ALLOW_PRIVATE_URLS=1 to disable (local development / tests
against localhost fixtures only — never in production).
"""

from __future__ import annotations

import ipaddress
import os
import socket
from urllib.parse import urlparse

from zeropark_core.errors import ZeroparkError


class BlockedURLError(ZeroparkError):
    """Raised when a URL resolves to a non-public address or is malformed."""


_ALLOWED_SCHEMES = {"http", "https"}


def _is_public(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def private_urls_allowed() -> bool:
    return os.environ.get("ZEROPARK_ALLOW_PRIVATE_URLS", "").lower() in ("1", "true", "yes")


def validate_public_url(url: str) -> str:
    """Validate scheme and resolve the host; raise BlockedURLError if non-public.

    Returns the URL unchanged on success so call sites can chain it.
    """
    if private_urls_allowed():
        return url

    parsed = urlparse(url)
    if parsed.scheme.lower() not in _ALLOWED_SCHEMES:
        raise BlockedURLError(f"URL scheme '{parsed.scheme}' is not allowed.")
    host = parsed.hostname
    if not host:
        raise BlockedURLError("URL has no hostname.")

    # Literal IP fast path (also catches forms like 127.1 via ipaddress parsing below)
    try:
        ip = ipaddress.ip_address(host)
        if not _is_public(ip):
            raise BlockedURLError(f"URL host {host} is in a blocked address range.")
        return url
    except ValueError:
        pass  # not a literal IP — resolve via DNS

    try:
        infos = socket.getaddrinfo(host, parsed.port or 80, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise BlockedURLError(f"Could not resolve host '{host}': {exc}") from exc

    for info in infos:
        addr = info[4][0]
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            continue
        if not _is_public(ip):
            raise BlockedURLError(
                f"URL host '{host}' resolves to blocked address {addr}."
            )
    return url

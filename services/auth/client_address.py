"""client_address.py — the client address auth keys its per-IP limits and audit rows on.

Gap AUTH-IP-RATE-LIMIT-KEYS-ON-THE-GATEWAY-ADDRESS-01. Every auth handler used to take
``request.client.host``. uvicorn runs without ``--proxy-headers`` (``Dockerfile`` CMD), so
behind the gateway that is the gateway's own address: every user shared ONE
``sahool:ip_rate:<gateway>`` bucket in ``main.check_ip_rate`` (20 requests/minute), one
client could exhaust registration and password reset for everybody, and the per-IP limit
did not limit any particular attacker. The same address went into ``audit_log`` and the
MFA attempt/audit rows, so forensics recorded the gateway too.

The chain this module reads (public Railway deployment)::

    client ──▶ Railway edge ──▶ gateway (frontend/nginx.conf) ──▶ auth (this service)

* The Railway edge appends the address it received the connection from to
  ``X-Forwarded-For``. Measured live on staging 2026-10-15: requests without XFF and with
  two different forged XFF values from one egress fell into ONE gateway bucket, i.e. the
  last element the gateway receives is the real client and a forged left-most element
  cannot select a bucket. The gateway keys its own ``limit_req`` on that last element
  (``$sahool_client_addr``).
* The gateway forwards ``X-Forwarded-For: $proxy_add_x_forwarded_for`` — what it
  received plus its own peer (the edge hop) appended on the right.
* Auth is reached over a private network: the compose bridge (RFC 1918) locally, and
  Railway private networking (``SAHOOL_AUTH_UPSTREAM=${{sahool-auth-main.
  RAILWAY_PRIVATE_DOMAIN}}:8000``, IPv6 ULA) on Railway.

So the client is the right-most XFF element that is not itself a proxy hop. We read XFF
ONLY when the direct peer is a trusted proxy (otherwise anyone reaching auth directly
could pick their own bucket), walk it from the right skipping trusted hops, and take the
first untrusted element. Anything a client writes lands to the LEFT of what the edge
appends, so it is never reached while the real client address is untrusted.

``AUTH_TRUSTED_PROXY_CIDRS`` (comma/space separated CIDRs) sets the trusted networks.
Unset ⇒ :data:`DEFAULT_TRUSTED_PROXY_CIDRS`: loopback, RFC 1918, IPv6 ULA (the networks
the gateway reaches auth from) and RFC 6598 shared address space (never a routable
client address at a public edge; the class platform proxies use for internal hops —
an assumption, not measured here). ``none`` ⇒ trust no proxy (peer address only). An
invalid value raises at import: a mistyped trust list must stop the service, not
silently fall back to the gateway bucket or, worse, trust everything.

Declared limits: what auth itself receives behind the Railway gateway is not measured
(only the gateway's view is); if the edge hop the gateway appends is outside the trusted
set, auth keys on that hop — set ``AUTH_TRUSTED_PROXY_CIDRS`` to include it.
"""

from __future__ import annotations

import ipaddress
import os
from collections.abc import Iterable
from typing import Any

IPNetwork = ipaddress.IPv4Network | ipaddress.IPv6Network
IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address

DEFAULT_TRUSTED_PROXY_CIDRS: tuple[str, ...] = (
    "127.0.0.0/8",
    "::1/128",
    "10.0.0.0/8",
    "172.16.0.0/12",
    "192.168.0.0/16",
    "fc00::/7",
    "100.64.0.0/10",
)

_ENV = "AUTH_TRUSTED_PROXY_CIDRS"
UNKNOWN = "unknown"


def parse_trusted_proxies(value: str | None) -> tuple[IPNetwork, ...]:
    """Parse ``AUTH_TRUSTED_PROXY_CIDRS``. Unset/blank ⇒ defaults; ``none`` ⇒ ().

    Raises ``ValueError`` naming the bad element — a wrong trust list is a deploy error.
    """
    if value is None or not value.strip():
        items: Iterable[str] = DEFAULT_TRUSTED_PROXY_CIDRS
    elif value.strip().lower() == "none":
        return ()
    else:
        items = [p for p in value.replace(",", " ").split() if p]
    nets: list[IPNetwork] = []
    for item in items:
        try:
            nets.append(ipaddress.ip_network(item, strict=False))
        except ValueError as exc:
            raise ValueError(f"{_ENV}: invalid network {item!r}: {exc}") from exc
    return tuple(nets)


TRUSTED_PROXIES: tuple[IPNetwork, ...] = parse_trusted_proxies(os.getenv(_ENV))


def parse_address(raw: str) -> IPAddress | None:
    """One address as it appears in XFF or ``request.client.host`` ⇒ IP, or None.

    Accepts ``v4``, ``v4:port``, ``v6``, ``[v6]``, ``[v6]:port``; unwraps IPv4-mapped
    IPv6 (``::ffff:10.0.0.2`` is 10.0.0.2 — a dual-stack listener reports it that way).
    """
    text = raw.strip().strip('"')
    if not text:
        return None
    if text.startswith("["):
        end = text.find("]")
        if end < 0:
            return None
        rest = text[end + 1 :]
        if rest and not (rest.startswith(":") and rest[1:].isdigit()):
            return None
        text = text[1:end]
    elif text.count(":") == 1:
        host, _, port = text.partition(":")
        if not port.isdigit():
            return None
        text = host
    try:
        addr = ipaddress.ip_address(text.split("%", 1)[0])
    except ValueError:
        return None
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped is not None:
        return addr.ipv4_mapped
    return addr


def _trusted(addr: IPAddress, trusted: tuple[IPNetwork, ...]) -> bool:
    return any(addr.version == net.version and addr in net for net in trusted)


def resolve_client_ip(
    peer: str | None,
    forwarded_for: Iterable[str] = (),
    trusted: tuple[IPNetwork, ...] | None = None,
) -> str:
    """The client address for a connection from ``peer`` carrying ``forwarded_for``.

    ``forwarded_for`` is every X-Forwarded-For header value in arrival order.
    """
    nets = TRUSTED_PROXIES if trusted is None else trusted
    if not peer:
        return UNKNOWN
    peer_addr = parse_address(peer)
    peer_text = str(peer_addr) if peer_addr is not None else peer
    if peer_addr is None or not _trusted(peer_addr, nets):
        return peer_text
    elements = [e for value in forwarded_for for e in value.split(",")]
    for element in reversed(elements):
        addr = parse_address(element)
        if addr is None:
            # Garbage between us and the client: nothing to its left is trustworthy.
            return peer_text
        if not _trusted(addr, nets):
            return str(addr)
    # No XFF, or every hop is a trusted proxy: the nearest one is all we know.
    return peer_text


def client_ip(request: Any) -> str:
    """The address auth keys ``check_ip_rate``, audit and MFA rows on for ``request``."""
    client = getattr(request, "client", None)
    peer = getattr(client, "host", None) if client else None
    return resolve_client_ip(peer, request.headers.getlist("x-forwarded-for"))

"""Witness: auth's per-IP limit keys on the client, not on the gateway in front of it.

Gap AUTH-IP-RATE-LIMIT-KEYS-ON-THE-GATEWAY-ADDRESS-01. Every auth handler took
``request.client.host``; behind the gateway that is the gateway, so every user shared
one ``sahool:ip_rate:<gateway>`` bucket in ``main.check_ip_rate`` (20/minute) — one
client exhausted registration / password reset for everybody. The fix resolves the
client from ``X-Forwarded-For`` only when the direct peer is a trusted proxy, walking
from the right (``services/auth/client_address.py`` documents the measured chain).

The end-to-end tests run the real ``check_ip_rate`` through the real password-reset
handler on an in-memory Redis, with the gateway as the direct peer (10.0.0.2).
"""

from __future__ import annotations

import ast
import asyncio
import importlib.util
import re
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
AUTH_DIR = ROOT / "services" / "auth"
HELPER = AUTH_DIR / "client_address.py"
GATEWAY = "10.0.0.2"
RESET_PATH = "/v1/auth/password-reset/request"

sys.path.insert(0, str(Path(__file__).resolve().parent))
from service_module import load_service_main  # noqa: E402


class _FakeRedis:
    def __init__(self) -> None:
        self.counts: dict[str, int] = {}

    async def incr(self, key: str) -> int:
        self.counts[key] = self.counts.get(key, 0) + 1
        return self.counts[key]

    async def expire(self, key: str, seconds: int) -> bool:
        return True


class _PassedRateLimit(Exception):
    """Raised right after ``check_ip_rate`` let the request through."""


class _StopCounter:
    def inc(self, *a, **k):
        raise _PassedRateLimit


def _request(peer: str | None, *xff: str):
    from starlette.requests import Request

    scope = {
        "type": "http",
        "method": "POST",
        "path": RESET_PATH,
        "headers": [(b"x-forwarded-for", v.encode()) for v in xff],
        "client": (peer, 40000) if peer else None,
    }
    return Request(scope)


@pytest.fixture
def auth(monkeypatch):
    main = load_service_main(str(AUTH_DIR), required_attrs=("check_ip_rate", "app"))
    redis = _FakeRedis()
    monkeypatch.setattr(main, "_redis", redis)
    monkeypatch.setattr(main, "RESET_COUNTER", _StopCounter())
    handler = next(r.endpoint for r in main.app.routes if getattr(r, "path", None) == RESET_PATH)
    body = main.PasswordResetRequest(email="someone@example.com")

    def send(peer: str, *xff: str) -> int:
        """One reset request; 200 = passed the IP limit, 429 = limited."""
        from fastapi import HTTPException

        try:
            asyncio.run(handler(body, _request(peer, *xff)))
        except _PassedRateLimit:
            return 200
        except HTTPException as exc:
            return exc.status_code
        raise AssertionError("handler returned without reaching RESET_COUNTER")

    return send, redis


def test_two_clients_behind_the_gateway_get_independent_buckets(auth):
    send, redis = auth
    statuses = [send(GATEWAY, "198.51.100.7") for _ in range(21)]
    assert statuses[:20] == [200] * 20 and statuses[20] == 429, statuses
    assert send(GATEWAY, "198.51.100.8") == 200, (
        "a second client behind the same gateway was limited by the first client's "
        f"requests; buckets: {sorted(redis.counts)}"
    )
    assert set(redis.counts) == {
        "sahool:ip_rate:198.51.100.7",
        "sahool:ip_rate:198.51.100.8",
    }, sorted(redis.counts)


def test_forged_left_most_element_cannot_select_the_bucket(auth):
    send, redis = auth
    for forged in ("1.1.1.1", "2.2.2.2", "203.0.113.9, 10.9.9.9"):
        send(GATEWAY, f"{forged}, 198.51.100.7")
    assert redis.counts == {"sahool:ip_rate:198.51.100.7": 3}, redis.counts


def test_railway_chain_client_edge_gateway(auth):
    """Edge appends the client, the gateway appends the edge hop, auth sees the gateway."""
    send, redis = auth
    send("fd12:ab::5", "6.6.6.6, 198.51.100.7, 100.64.0.9")
    assert set(redis.counts) == {"sahool:ip_rate:198.51.100.7"}, sorted(redis.counts)


def test_untrusted_peer_cannot_choose_its_bucket_with_xff(auth):
    send, redis = auth
    send("198.51.100.50", "1.2.3.4")
    assert set(redis.counts) == {"sahool:ip_rate:198.51.100.50"}, sorted(redis.counts)


_PEER_READ = re.compile(r"\.client\.host|request\.client\b")


def test_no_auth_call_site_reads_the_peer_address_itself():
    offenders = []
    for path in sorted([*AUTH_DIR.glob("*.py"), *(AUTH_DIR / "routers").glob("*.py")]):
        if path == HELPER:
            continue
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if _PEER_READ.search(line):
                offenders.append(f"{path.relative_to(ROOT)}:{n}: {line.strip()}")
    assert offenders == [], (
        "auth must key limits/audit on client_address.client_ip(request); the direct "
        "peer is the gateway, so these sites put every user in one bucket:\n" + "\n".join(offenders)
    )


def _sibling_imports_of_routers() -> set[str]:
    siblings = {p.stem for p in AUTH_DIR.glob("*.py")} - {"__init__"}
    found: set[str] = set()
    for path in (AUTH_DIR / "routers").glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                found |= {a.name.split(".")[0] for a in node.names}
            elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
                found.add(node.module.split(".")[0])
    return found & siblings


def test_image_ships_every_sibling_module_the_routers_import():
    """router_registry silently skips a router whose import fails — so a missing COPY
    removes login/register/reset from the running service with a green build."""
    imported = _sibling_imports_of_routers()
    assert "client_address" in imported, sorted(imported)
    dockerfile = (AUTH_DIR / "Dockerfile").read_text(encoding="utf-8")
    missing = [
        m
        for m in sorted(imported)
        if not re.search(rf"^COPY services/auth/{m}\.py /app/{m}\.py$", dockerfile, re.M)
    ]
    assert missing == [], f"services/auth/Dockerfile does not COPY {missing}"


# ── resolver unit tests ─────────────────────────────────────────────────────────


def _load_helper(monkeypatch, env: str | None = None):
    if env is None:
        monkeypatch.delenv("AUTH_TRUSTED_PROXY_CIDRS", raising=False)
    else:
        monkeypatch.setenv("AUTH_TRUSTED_PROXY_CIDRS", env)
    spec = importlib.util.spec_from_file_location("auth_client_address_test", HELPER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def ca(monkeypatch):
    return _load_helper(monkeypatch)


@pytest.mark.parametrize(
    ("peer", "xff", "expected"),
    [
        ("10.0.0.2", ["198.51.100.7"], "198.51.100.7"),
        ("10.0.0.2", [], "10.0.0.2"),
        ("10.0.0.2", ["198.51.100.7:51234"], "198.51.100.7"),
        ("10.0.0.2", ["[2001:db8::7]:443"], "2001:db8::7"),
        ("10.0.0.2", ["2001:db8::7"], "2001:db8::7"),
        ("10.0.0.2", ["::ffff:198.51.100.7"], "198.51.100.7"),
        ("::ffff:10.0.0.2", ["198.51.100.7"], "198.51.100.7"),
        ("10.0.0.2", ["1.1.1.1, 198.51.100.7", "172.16.0.4"], "198.51.100.7"),
        ("10.0.0.2", ["198.51.100.7", "198.51.100.8"], "198.51.100.8"),
        ("10.0.0.2", ["198.51.100.7, garbage"], "10.0.0.2"),
        ("10.0.0.2", ["198.51.100.7, , 10.0.0.9"], "10.0.0.2"),
        ("10.0.0.2", ["192.168.1.4, 10.0.0.9"], "10.0.0.2"),
        ("127.0.0.1", ["198.51.100.7"], "198.51.100.7"),
        ("198.51.100.50", ["1.2.3.4"], "198.51.100.50"),
        (None, ["198.51.100.7"], "unknown"),
        ("testclient", ["198.51.100.7"], "testclient"),
    ],
)
def test_resolve_client_ip(ca, peer, xff, expected):
    assert ca.resolve_client_ip(peer, xff) == expected


def test_trust_none_reads_only_the_peer(monkeypatch):
    mod = _load_helper(monkeypatch, "none")
    assert mod.TRUSTED_PROXIES == ()
    assert mod.resolve_client_ip("10.0.0.2", ["198.51.100.7"]) == "10.0.0.2"


def test_explicit_trust_list_replaces_the_defaults(monkeypatch):
    mod = _load_helper(monkeypatch, "203.0.113.0/24, 10.0.0.2/32")
    assert mod.resolve_client_ip("10.0.0.2", ["198.51.100.7, 203.0.113.4"]) == "198.51.100.7"
    assert mod.resolve_client_ip("10.0.0.3", ["198.51.100.7"]) == "10.0.0.3"


def test_invalid_trust_list_fails_at_import(monkeypatch):
    with pytest.raises(ValueError, match="AUTH_TRUSTED_PROXY_CIDRS"):
        _load_helper(monkeypatch, "10.0.0.0/8, not-a-network")


def test_client_ip_reads_repeated_headers_in_order(ca):
    req = _request(GATEWAY, "6.6.6.6", "198.51.100.7")
    assert ca.client_ip(req) == "198.51.100.7"
    assert ca.client_ip(_request(None)) == "unknown"

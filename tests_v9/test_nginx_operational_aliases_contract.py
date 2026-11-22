"""The gateway's readiness/metrics aliases must reach a handler the service declares.

The fault (audit F10): ``nginx/nginx.v9.conf`` served ``/api/rag/``,
``/api/knowledge-graph/`` and ``/api/ai-agronomist/`` only through prefixes that rewrite to
``/v1/``. The three services declare ``/readyz`` and ``/metrics`` at their root, so the six
aliases ``scripts/observability_smoke.sh`` probes resolved to ``/v1/readyz`` and
``/v1/metrics``, which no service declares: 401 without a token, 404 with one.

Each alias must now be an exact-match location that proxies to the root handler and keeps
the prefix's identity check. Nothing else under the prefix may change: a near-miss path
still takes the guarded ``/v1/`` rewrite.

Static scan (no nginx). The request-level proof is
``tests_v9/test_nginx_v9_operational_aliases_runtime.py``.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from _nginx_resolve import locations, resolve, upstream

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
CONF = (ROOT / "nginx" / "nginx.v9.conf").read_text(encoding="utf-8")

SERVICES = {
    "/api/rag/": ("sahool-rag-retrieval:8000", "services/rag-retrieval/main.py"),
    "/api/knowledge-graph/": ("sahool-knowledge-graph:8000", "services/knowledge-graph/main.py"),
    "/api/ai-agronomist/": ("sahool-ai-agronomist:8000", "services/ai_agronomist/main.py"),
}
ALIASES = [f"{prefix}{name}" for prefix in SERVICES for name in ("readyz", "metrics")]
NEAR_MISSES = [
    f"{alias}{suffix}" for alias in ALIASES for suffix in ("/", "x", "/extra", ".json")
] + [alias.upper() for alias in ALIASES]


def _service(path: str) -> tuple[str, str, str]:
    prefix = next(p for p in SERVICES if path.lower().startswith(p))
    return (prefix, *SERVICES[prefix])


def _declared_get_routes(source: str) -> set[str]:
    text = (ROOT / source).read_text(encoding="utf-8")
    return set(re.findall(r'(?m)^@app\.get\(\s*"([^"]+)"', text))


def test_the_six_aliases_are_the_ones_the_smoke_script_probes() -> None:
    smoke = (ROOT / "scripts" / "observability_smoke.sh").read_text(encoding="utf-8")
    assert len(ALIASES) == 6
    for alias in ALIASES:
        assert re.search(rf"(?m)^check\w* \w+ {re.escape(alias)}( |$)", smoke), alias


@pytest.mark.parametrize("alias", ALIASES)
def test_alias_reaches_a_handler_the_service_declares(alias: str) -> None:
    _, host, source = _service(alias)
    block = resolve(CONF, alias)
    target_host, uri = upstream(block, alias)
    assert target_host == host, f"{alias} goes to {target_host}, not {host}"
    assert uri in _declared_get_routes(source), (
        f"{alias} is served by `location {block.key}` and proxied to {uri}, "
        f"which {source} does not declare"
    )
    assert uri == "/" + alias.rsplit("/", 1)[1]
    assert block.key == f"= {alias}", f"{alias} must be an exact-match location"


@pytest.mark.parametrize("alias", ALIASES)
def test_alias_keeps_the_identity_check_of_its_prefix(alias: str) -> None:
    block = resolve(CONF, alias)
    assert "auth_request /_auth_verify;" in block.body, (
        f"`location {block.key}` answers without the gateway identity check"
    )
    assert "limit_req zone=" in block.body, f"`location {block.key}` has no rate limit"
    assert "include /etc/nginx/proxy_params.conf;" in re.sub(r"\s+", " ", block.body), (
        f"`location {block.key}` does not clear the client's trust headers"
    )
    assert "$http_x_" not in block.body, f"`location {block.key}` forwards a client header"
    assert not re.search(r"\b(allow|satisfy)\b", block.body), (
        f"`location {block.key}`: an allow/satisfy rule can bypass auth_request"
    )


@pytest.mark.parametrize("prefix", SERVICES)
def test_prefix_is_still_guarded_and_still_rewrites_to_v1(prefix: str) -> None:
    host = SERVICES[prefix][0]
    block = resolve(CONF, f"{prefix}query")
    assert block.key == prefix
    assert "auth_request /_auth_verify;" in block.body
    assert upstream(block, f"{prefix}query") == (host, "/v1/query")


@pytest.mark.parametrize("path", NEAR_MISSES)
def test_near_miss_does_not_take_the_exact_location(path: str) -> None:
    """Only the exact path is aliased; anything else stays on the guarded /v1/ rewrite."""
    block = resolve(CONF, path)
    assert block.modifier != "=", f"{path} is served by `location {block.key}`"
    if path != path.lower():
        # Location matching is case-sensitive: this is not under the service prefix at all.
        assert not any(host in block.body for host, _ in SERVICES.values()), block.key
        return
    prefix, host, _ = _service(path)
    assert block.key == prefix
    assert "auth_request /_auth_verify;" in block.body, (
        f"{path} is served by `location {block.key}` without the identity check"
    )
    assert upstream(block, path) == (host, "/v1/" + path[len(prefix) :])


def test_no_new_unauthenticated_prefix_under_the_three_services() -> None:
    """The only unauthenticated location under the three prefixes is the existing liveness."""
    open_blocks = sorted(
        block.key
        for block in locations(CONF)
        if any(block.path.startswith(prefix) for prefix in SERVICES)
        and "auth_request" not in block.body
    )
    assert open_blocks == ["= /api/ai-agronomist/healthz"], open_blocks

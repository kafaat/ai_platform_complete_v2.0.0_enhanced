"""Both nginx edges refuse vegetation-analysis's service-to-service ``internal/`` prefix.

The scouting-verification receiver (``/internal/anomalies/{ref}/verification-context`` and
``/verification-results`` on vegetation-analysis) is called by field-management on the service
network. ``/api/vegetation/`` proxies to the vegetation root, so without a dedicated block a
browser request to ``/api/vegetation/internal/...`` would reach the receiver with whatever
``X-Task-Service-Token`` / ``X-Tenant-Assertion`` headers it sent (``proxy_params`` does not
clear them). The checks resolve which ``location`` nginx would pick for a URI by nginx's own
rule for prefix locations: the longest matching prefix wins and ``^~`` stops the regex scan.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
CONFS = ("nginx/nginx.v9.conf", "frontend/nginx.conf")


def _servers(conf: str) -> list[str]:
    text = re.sub(r"#[^\n]*", "", (ROOT / conf).read_text(encoding="utf-8"))
    out = []
    for m in re.finditer(r"\bserver\s*\{", text):
        depth, k = 1, m.end()
        while depth:
            depth += {"{": 1, "}": -1}.get(text[k], 0)
            k += 1
        out.append(text[m.end() : k - 1])
    return [s for s in out if "/api/vegetation/" in s]


def _locations(server: str) -> list[tuple[str, str, str]]:
    out = []
    for m in re.finditer(r"location\s+(\^~|=|~\*|~)?\s*(\S+)\s*\{", server):
        depth, k = 1, m.end()
        while depth:
            depth += {"{": 1, "}": -1}.get(server[k], 0)
            k += 1
        out.append((m.group(1) or "", m.group(2), server[m.end() : k - 1]))
    return out


def _resolve(server: str, uri: str) -> tuple[str, str, str]:
    locs = _locations(server)
    exact = [loc for loc in locs if loc[0] == "=" and loc[1] == uri]
    if exact:
        return exact[0]
    prefixes = [loc for loc in locs if loc[0] in ("", "^~") and uri.startswith(loc[1])]
    best = max(prefixes, key=lambda loc: len(loc[1]))
    if best[0] == "^~":
        return best
    for loc in locs:
        if loc[0] in ("~", "~*"):
            flags = re.IGNORECASE if loc[0] == "~*" else 0
            if re.search(loc[1], uri, flags):
                return loc
    return best


@pytest.mark.parametrize("conf", CONFS)
def test_each_conf_has_a_server_that_proxies_vegetation(conf):
    assert _servers(conf), f"{conf}: no server block proxies /api/vegetation/"


@pytest.mark.parametrize("conf", CONFS)
@pytest.mark.parametrize(
    "uri",
    [
        "/api/vegetation/internal/",
        "/api/vegetation/internal/anomalies/urn:sahool:anomaly:x/verification-results",
        "/api/vegetation/internal/anomalies/x/verification-context?tenant=t",
    ],
)
def test_the_internal_prefix_is_answered_at_the_edge_and_never_proxied(conf, uri):
    for server in _servers(conf):
        modifier, path, body = _resolve(server, uri)
        assert (modifier, path) == ("^~", "/api/vegetation/internal/"), (conf, uri, path)
        assert "proxy_pass" not in body
        assert re.search(r"\breturn\s+404\b", body)


@pytest.mark.parametrize("conf", CONFS)
def test_public_vegetation_paths_are_still_proxied(conf):
    for server in _servers(conf):
        _, path, body = _resolve(server, "/api/vegetation/v1/anomalies")
        assert path == "/api/vegetation/"
        assert "proxy_pass" in body

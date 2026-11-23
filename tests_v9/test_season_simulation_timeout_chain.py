"""Every hop in front of the season simulation run waits longer than the web client.

Devin review and hospital review on #1582: the run
(``POST /api/v1/seasons/{id}/simulate``, ``services/sahool-platform/api/routers/seasons.py``)
awaits the NDVI series (raster, 20 s), the weather archive (20 s), ET0 (20 s) and GDD (20 s)
one after another, then saves and mirrors the context (3 s). The web client gave up at 15 s,
and each gateway in front of the platform cut the route at 60 s, so the dialog reported a
failure for a run the server went on to save.

The order that keeps the user's message honest: the run's upstream bounds < the client's
timeout < every proxy's read timeout on that route. Then the client gives up first, with its
own message, and never a proxy's 504.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
RUN_UPSTREAM_BOUNDS_S = 20 + 20 + 20 + 20 + 3  # raster, archive, ET0, GDD, decision mirror
SIMULATE_ROUTE = "location ~ ^/api/v1/seasons/[^/]+/simulate$ {"
GATEWAYS = [
    "frontend/nginx.conf",
    "nginx/nginx.v9.conf",
    "helm/sahool/files/gateway/routes.conf",
]


def _client_timeout_s() -> float:
    source = (ROOT / "frontend/src/services/api/reports.ts").read_text(encoding="utf-8")
    match = re.search(r"SEASON_SIMULATION_TIMEOUT_MS = ([\d_]+);", source)
    assert match, "the simulate request names its timeout"
    assert "timeout: SEASON_SIMULATION_TIMEOUT_MS" in source, "and passes it to the request"
    return int(match.group(1).replace("_", "")) / 1000


def _simulate_block(conf: str) -> str:
    text = (ROOT / conf).read_text(encoding="utf-8")
    assert text.count(SIMULATE_ROUTE) == 1, f"{conf}: one simulate location"
    start = text.index(SIMULATE_ROUTE)
    return text[start : text.index("}", start)]


def _seconds(value: str) -> float:
    match = re.fullmatch(r"(\d+)(s|m)?", value)
    assert match, value
    return int(match.group(1)) * (60 if match.group(2) == "m" else 1)


def test_the_client_waits_longer_than_the_run_upstream_bounds():
    assert _client_timeout_s() > RUN_UPSTREAM_BOUNDS_S


@pytest.mark.parametrize("conf", GATEWAYS)
def test_each_gateway_waits_longer_than_the_client_on_the_simulate_route(conf):
    block = _simulate_block(conf)
    timeouts = re.findall(r"proxy_read_timeout\s+(\w+);", block)
    assert len(timeouts) == 1, f"{conf}: the simulate location sets its own read timeout"
    assert _seconds(timeouts[0]) > _client_timeout_s(), (
        f"{conf}: the proxy would answer 504 before the client gives up"
    )


def test_the_helm_ingress_waits_longer_than_the_client():
    ingress = (ROOT / "helm/sahool/templates/ingress.yaml").read_text(encoding="utf-8")
    match = re.search(r'nginx\.ingress\.kubernetes\.io/proxy-read-timeout:\s*"(\d+)"', ingress)
    assert match and int(match.group(1)) > _client_timeout_s()


def test_the_helm_simulate_location_precedes_the_general_platform_surface():
    routes = (ROOT / "helm/sahool/files/gateway/routes.conf").read_text(encoding="utf-8")
    # A regex location wins over a plain prefix location, so order is for the reader; the
    # target must still be the platform with the path passed as is.
    block = _simulate_block("helm/sahool/files/gateway/routes.conf")
    assert "proxy_pass http://sahool_platform;" in block
    assert routes.index(SIMULATE_ROUTE) < routes.index("location /api/v1/ {")

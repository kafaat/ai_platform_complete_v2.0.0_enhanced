"""Railway gateway parity with the compose gateway for every `/api` location (W0-09).

The fault (web-1 / deploy-4, CONFIRMED): ``frontend/nginx.conf`` is the public Railway
gateway (``deploy/railway/Dockerfile.frontend`` renders it with ``render_frontend.py``), but
it had no ``/api/v1/seasons*``, ``/api/v1/field-tasks/`` or ``/api/v1/scouting-media/``
block. Those paths fell to its ``/api/`` catch-all, so the platform, which owns none of
them, answered 404. COG tiles (deploy-11) fell there too and answered 401, because ``<img>``
carries no Authorization header and only ``nginx.v9.conf`` bridged the session cookie.

This contract makes the drift visible: every ``location`` in ``nginx/nginx.v9.conf`` whose
path is under ``/api`` must exist in ``frontend/nginx.conf`` with the same modifier and path,
or be declared here, either as reaching the same platform path through the catch-all (checked
against v9's own target, so a change there fails this test) or as not ported, with a reason.

Static scan of the two files, no nginx. The request-level proof (routing, identity headers,
the cookie bridge) is ``frontend/tests/test_nginx_runtime.py``.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
V9 = ROOT / "nginx" / "nginx.v9.conf"
FRONTEND = ROOT / "frontend" / "nginx.conf"

#: v9 locations the Railway gateway serves through its ``location /api/`` catch-all, which
#: proxies ``/api/<rest>`` to ``sahool-platform:8000/api/<rest>`` unchanged. Valid only while
#: v9 sends the same path to the platform, which ``test_catch_all_declarations_still_hold``
#: checks against v9's proxy_pass.
SAME_PLATFORM_PATH = {
    "/api/v1/": "the platform's unified /api/v1/ surface",
    "/api/edge/": "platform service_proxy injects the edge token after its own JWT check",
    "/api/soil/": "platform service_proxy injects the soil token after its own JWT check",
    "/api/field-forms/": "platform route, same path",
}

#: v9 locations deliberately not on the Railway gateway, each with the reason. Adding a
#: block for one of them later removes it from here (the test fails while both exist).
NOT_PORTED = {
    "= /api/indicators/readyz": "compose fleet probe of the indicators container; Railway "
    "has no indicators service and /api/indicators/ goes to the platform",
    "= /api/weather/readyz": "compose fleet probe; Railway weather goes to the platform",
    "= /api/vegetation/readyz": "compose fleet probe; /api/vegetation/ forwards it as-is",
    "/api/knowledge-graph/": "knowledge-graph is not in the Railway fleet (deploy-5, W3-10)",
    "= /api/knowledge-graph/readyz": "knowledge-graph is not in the Railway fleet (as above)",
    "= /api/knowledge-graph/metrics": "knowledge-graph is not in the Railway fleet (as above)",
    # F10 (2026-11-22): the four below are NOT equivalent on Railway. frontend/nginx.conf
    # still sends them through its /v1/ prefixes to /v1/readyz and /v1/metrics, which no
    # service declares. Not ported here because frontend/** was frozen for #1572/#1573;
    # porting them removes these entries (test_declarations_are_neither_stale... fails).
    "= /api/rag/readyz": "OPEN DEFECT on Railway: prefix rewrites to /v1/readyz (no handler)",
    "= /api/rag/metrics": "OPEN DEFECT on Railway: prefix rewrites to /v1/metrics (no handler)",
    "= /api/ai-agronomist/readyz": "OPEN DEFECT on Railway: prefix rewrites to /v1/readyz "
    "(no handler)",
    "= /api/ai-agronomist/metrics": "OPEN DEFECT on Railway: prefix rewrites to /v1/metrics "
    "(no handler)",
    "/api/video/": "video-processor is not in the Railway fleet (deploy-5, W3-10)",
    "/api/agriai/": "agriai-engine is not in the Railway fleet (deploy-5, W3-10)",
    "/api/": "v9's JSON 404 guard; on Railway the same prefix is the platform catch-all",
}

#: The blocks W0-09 ports, with the upstream each must reach and the token it must inject.
PORTED = {
    "~ ^/api/v1/gis/cloud-native/rasters/[^/]+/tiles/": ("frontend_platform", None),
    "^~ /api/v1/scouting-media/": ("frontend_scout_ingest", "X-Scout-Media-Token"),
    "^~ /api/v1/field-tasks/": ("frontend_field_management", "X-Field-Tasks-Token"),
    "~ ^/api/v1/seasons/[^/]+/simulate$": ("frontend_platform", None),
    "~ ^/api/v1/seasons/[^/]+/accept$": ("frontend_scout_ingest", "X-Season-Entry-Token"),
    "~ ^/api/v1/seasons": ("frontend_scout_ingest", "X-Season-Entry-Token"),
}

_HEADER = re.compile(r"(?m)^\s*location\s+((?:=|\^~|~\*|~)\s+)?(\S+)\s*\{")


def _strip_comments(text: str) -> str:
    return re.sub(r"(?m)#[^\n]*", "", text)


def _locations(text: str) -> dict[str, str]:
    """``"<modifier> <path>"`` (or ``"<path>"``) -> block body, braces balanced."""
    text = _strip_comments(text)
    found = {}
    for match in _HEADER.finditer(text):
        modifier = (match[1] or "").strip()
        key = f"{modifier} {match[2]}".strip()
        depth, start = 0, text.index("{", match.start())
        for index in range(start, len(text)):
            if text[index] == "{":
                depth += 1
            elif text[index] == "}":
                depth -= 1
                if depth == 0:
                    found[key] = text[start + 1 : index]
                    break
        else:
            raise AssertionError(f"unbalanced braces after location {key}")
    return found


def _path(key: str) -> str:
    return key.split(" ", 1)[-1]


def _served(key: str, frontend: dict[str, str]) -> bool:
    """Same matcher, or both plain/``^~`` prefixes of one path (they serve the same paths;
    ``^~`` only stops later regexes from taking them, which v9 gets from its own order)."""
    if key in frontend:
        return True
    modifier, _, path = key.rpartition(" ")
    return modifier in {"", "^~"} and (path in frontend or f"^~ {path}" in frontend)


def _v9_api_locations() -> dict[str, str]:
    return {
        k: v for k, v in _locations(V9.read_text(encoding="utf-8")).items() if "/api" in _path(k)
    }


def test_the_scan_sees_both_gateways() -> None:
    v9 = _v9_api_locations()
    frontend = _locations(FRONTEND.read_text(encoding="utf-8"))
    assert len(v9) >= 25, f"v9 /api scan looks empty: {sorted(v9)}"
    assert "/api/ " not in frontend and "/api/" in frontend, (
        f"frontend catch-all not found: {sorted(frontend)}"
    )


def test_every_v9_api_location_is_on_the_railway_gateway_or_declared() -> None:
    frontend = _locations(FRONTEND.read_text(encoding="utf-8"))
    declared = set(SAME_PLATFORM_PATH) | set(NOT_PORTED)
    missing = sorted(
        k for k in _v9_api_locations() if not _served(k, frontend) and k not in declared
    )
    assert not missing, (
        "v9 /api locations with no frontend/nginx.conf block and no declaration (they fall "
        f"to the platform catch-all and 404 on Railway): {missing}"
    )


def test_declarations_are_neither_stale_nor_shadowing_a_real_block() -> None:
    v9 = _v9_api_locations()
    frontend = _locations(FRONTEND.read_text(encoding="utf-8"))
    for key in set(SAME_PLATFORM_PATH) | set(NOT_PORTED):
        assert key in v9, f"declared {key!r} is no longer a v9 location; drop the declaration"
        if key != "/api/":
            assert not _served(key, frontend), (
                f"{key!r} is ported now; remove it from the declarations"
            )


def test_catch_all_declarations_still_hold() -> None:
    """A path declared as served by the catch-all must still go to the platform unchanged."""
    v9 = _v9_api_locations()
    frontend = _locations(FRONTEND.read_text(encoding="utf-8"))
    assert re.search(r"proxy_pass\s+http://frontend_platform/api/;", frontend["/api/"]), (
        "the Railway catch-all no longer proxies /api/ to the platform unchanged"
    )
    for path in SAME_PLATFORM_PATH:
        target = re.search(r"proxy_pass\s+http://(\w+)(\S*);", v9[path])
        assert target, f"v9 {path} has no proxy_pass"
        assert (target[1], target[2]) == ("platform_backend", path), (
            f"v9 {path} now goes to {target[1]}{target[2]}, not the platform at the same path; "
            "port the block instead of declaring it covered by the catch-all"
        )


def test_ported_blocks_reach_the_owner_with_verified_identity_only() -> None:
    frontend = _locations(FRONTEND.read_text(encoding="utf-8"))
    v9 = _v9_api_locations()
    for key, (upstream, token) in PORTED.items():
        assert key in v9, f"{key!r} is not a v9 location any more"
        body = frontend.get(key)
        assert body is not None, f"frontend/nginx.conf has no `location {key}` (web-1/deploy-4)"
        assert re.search(rf"proxy_pass\s+http://{upstream}\b", body), (
            f"{key} must proxy to {upstream}"
        )
        assert "limit_req zone=" in body, f"{key} has no rate limit"
        assert "$http_x_tenant_id" not in body, f"{key} forwards the caller's tenant header"
        assert re.search(r'proxy_set_header\s+X-Agent-Token\s+"";', body), (
            f"{key} does not clear X-Agent-Token (no proxy_params.conf in this file)"
        )
        if key.endswith("/simulate$"):
            # Platform trust model: the platform verifies the JWT itself.
            assert "auth_request" not in body, "simulate must mirror v9 (platform checks JWT)"
            assert re.search(r'proxy_set_header\s+X-Tenant-Id\s+"";', body), (
                "simulate must clear the caller's X-Tenant-Id"
            )
            continue
        verifier = "/_auth_edge_sign" if key.endswith("/accept$") else "/_auth_verify"
        assert f"auth_request {verifier};" in body, f"{key} is not behind {verifier}"
        tenant = re.search(r"proxy_set_header\s+X-Tenant-Id\s+(\$\w+);", body)
        assert tenant, f"{key} does not inject a tenant from the auth response"
        assert re.search(
            rf"auth_request_set\s+\{tenant[1]}\s+\$upstream_http_x_tenant_id;", body
        ), f"{key} tenant {tenant[1]} is not taken from the auth response"
        if token:
            assert re.search(rf'proxy_set_header\s+{token}\s+"@[A-Z_]+_TOKEN@";', body), (
                f"{key} must set {token} from a render placeholder, never from the client"
            )


def test_cookie_bridge_and_edge_signature_are_present() -> None:
    frontend = _locations(FRONTEND.read_text(encoding="utf-8"))
    tiles = frontend["~ ^/api/v1/gis/cloud-native/rasters/[^/]+/tiles/"]
    assert 'set $fwd_auth "Bearer $cookie_sahool_at";' in tiles, "tile cookie bridge missing"
    assert re.search(r"proxy_set_header\s+Authorization\s+\$fwd_auth;", tiles), (
        "the platform reads Authorization only; the bridged token must be forwarded"
    )
    edge = frontend.get("= /_auth_edge_sign")
    assert edge is not None, "accept needs the internal edge-signature subrequest"
    assert re.search(r"(?m)^\s*internal;", edge), "/_auth_edge_sign must be internal"
    assert "/v1/auth/edge-sign" in edge, "edge signature must be asked of auth"
    assert re.search(r"X-Canonical-Path\s+\$season_canonical_path;", edge), (
        "the gateway must write the canonical path itself"
    )
    assert "$arg_access_token" not in edge, "no query-string token for the sensitive action"
    source = _strip_comments(FRONTEND.read_text(encoding="utf-8"))
    assert re.search(r"map\s+\$request_uri\s+\$season_canonical_path\s*\{", source), (
        "single declared canonical source map missing"
    )


def test_regex_order_matches_v9_and_precedes_static_assets() -> None:
    """nginx takes the FIRST matching regex: simulate and accept before the general season
    block, and the tile regex before the static-asset regex that ends in .png."""
    source = _strip_comments(FRONTEND.read_text(encoding="utf-8"))

    def at(fragment: str) -> int:
        position = source.find(fragment)
        assert position != -1, f"{fragment!r} not found"
        return position

    simulate = at("location ~ ^/api/v1/seasons/[^/]+/simulate$")
    accept = at("location ~ ^/api/v1/seasons/[^/]+/accept$")
    general = at("location ~ ^/api/v1/seasons {")
    tiles = at("location ~ ^/api/v1/gis/cloud-native/rasters/")
    static = at("location ~* \\.(js|css|png")
    assert simulate < accept < general, "season regex order differs from nginx.v9.conf"
    assert max(general, tiles) < static, "static-asset regex would take .png tiles first"


def _adapter():
    spec = importlib.util.spec_from_file_location(
        "railway_frontend_parity", ROOT / "deploy/railway/render_frontend.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_new_upstreams_can_be_declared_absent() -> None:
    adapter = _adapter()
    env = {
        "SAHOOL_AUTH_UPSTREAM": "sahool-auth.railway.internal:8000",
        "SAHOOL_PLATFORM_UPSTREAM": "sahool-platform.railway.internal:8000",
        "SAHOOL_SCOUT_INGEST_UPSTREAM": "absent",
        "SAHOOL_FIELD_MANAGEMENT_UPSTREAM": "absent",
    }
    config = adapter.render(FRONTEND.read_text(encoding="utf-8"), env, ["10.0.0.2"])
    assert "sahool-scout-ingest.railway.internal:8000 resolve" not in config, (
        "an absent scout-ingest must not be looked up"
    )
    assert "sahool-field-management.railway.internal:8000 resolve" not in config, (
        "an absent field-management must not be looked up"
    )
    assert f"listen unix:{adapter.ABSENT_SOCKET};" in config, "absent stub missing"

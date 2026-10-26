"""WEB-ENDPOINT-CONSTANTS-WITHOUT-SERVER-HANDLER-01 — a web `/api/v1` path must have a handler.

Fourteen `/api/v1` constants sat in ``frontend/src/lib/globalScaleRuntime.ts`` (seven
``phase8`` paths) and ``frontend/src/lib/enterpriseGisPhase7.ts`` (collaboration
sessions/events, distributed raster plan/jobs, digital-twin scenario simulation,
planet-scale readiness, autonomous recommendations). No server decorator served any of
them and no screen called them; only their own test file imported the objects. They
read as capability that does not exist. The fourteenth was the subtle one:
``/api/v1/recommendations/autonomous`` *looks* served because
``GET /api/v1/recommendations/{rec_id}`` exists, but that handler reads ``autonomous`` as
a recommendation id. So a literal segment on the web side never matches a route
parameter here.

**What this guard proves.** Every ``/api/v1`` string or template literal in non-test
code under ``frontend/src`` (comments excluded, via the same lexical mask the inventory
edge resolver uses) matches a route in the committed, CI-drift-checked
``route_inventory.generated.json`` (``scripts/ci/generate_service_inventory.py --check``),
by path and, when the literal is the first argument of ``.get/.post/.put/.patch/.delete``,
by method too. Gateway prefix rewrites declared in ``nginx/nginx.v9.conf`` (the
``/api/v1/seasons`` map to scout-ingest's ``/internal/seasons``) are applied to the
inventory before matching, derived from the file rather than restated here.

**What it does not prove (declared, not hidden).** That the gateway routes the path to
the service that owns the matching handler; that is the inventory edge resolver's job
(``scripts/diagnostics/resolve_inventory_edges.py``). A path built at runtime from
variables is invisible to a static scan, and so is a JSX attribute string (the shared
mask treats it as markup). A file whose lexical boundaries cannot be read fails this
guard rather than being skipped.
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
FRONTEND_SRC = ROOT / "frontend/src"
ROUTE_INVENTORY = ROOT / "route_inventory.generated.json"
GATEWAY_CONF = ROOT / "nginx/nginx.v9.conf"

_SPEC = importlib.util.spec_from_file_location(
    "_frontend_api_v1_route_guard_edges", ROOT / "scripts/diagnostics/resolve_inventory_edges.py"
)
edges = importlib.util.module_from_spec(_SPEC)
assert _SPEC.loader is not None
sys.modules[_SPEC.name] = edges
_SPEC.loader.exec_module(edges)

#: Pre-existing debt outside this gap, frozen so it can only shrink: entries in the
#: documentation-only ``BACKEND_COVERAGE_REGISTRY`` (the endpoint UI coverage gate
#: already excludes that file as "phantom evidence") whose glob prefix or path has no
#: route in the inventory. Each is a separate finding to register; a new entry here is
#: not a fix. An entry that starts matching must be deleted (see the staleness test).
KNOWN_UNMATCHED_COVERAGE_REGISTRY = frozenset(
    {
        ("frontend/src/config/backendCoverageRegistry.ts", "/api/v1/ogc/*"),
        ("frontend/src/config/backendCoverageRegistry.ts", "/api/v1/stac/*"),
        ("frontend/src/config/backendCoverageRegistry.ts", "/api/v1/cog/*"),
        ("frontend/src/config/backendCoverageRegistry.ts", "/api/v1/soil/*"),
        ("frontend/src/config/backendCoverageRegistry.ts", "/api/v1/pest/*"),
        ("frontend/src/config/backendCoverageRegistry.ts", "/api/v1/simulation/*"),
        (
            "frontend/src/config/backendCoverageRegistry.ts",
            "/api/v1/fields/{field_id}/soil-sampling-plan",
        ),
        ("frontend/src/config/backendCoverageRegistry.ts", "/api/v1/approvals/*"),
        ("frontend/src/config/backendCoverageRegistry.ts", "/api/v1/invitations/*"),
        ("frontend/src/config/backendCoverageRegistry.ts", "/api/v1/phase9/*"),
        ("frontend/src/config/backendCoverageRegistry.ts", "/api/v1/phase10/*"),
        ("frontend/src/config/backendCoverageRegistry.ts", "/api/v1/phase11/*"),
        ("frontend/src/config/backendCoverageRegistry.ts", "/api/v1/phase12/*"),
        ("frontend/src/config/backendCoverageRegistry.ts", "/api/v1/runtime/*"),
        ("frontend/src/config/backendCoverageRegistry.ts", "/api/v1/marketplace/*"),
        ("frontend/src/config/backendCoverageRegistry.ts", "/api/v1/plugins/*"),
        ("frontend/src/config/backendCoverageRegistry.ts", "/api/v1/ecosystem/*"),
    }
)

_HTTP_CALL = re.compile(r"\.\s*(get|post|put|patch|delete)\s*(?:<[^()]*>)?\s*\(\s*$")
_TEMPLATE_EXPR = re.compile(r"\$\{(?:[^{}]|\{[^{}]*\})*\}")
_NAMED_PARAM = re.compile(r"\{[^{}/]*\}")
_GATEWAY_REWRITE = re.compile(r'"~\^(/api/v1/[\w/-]+)\(\?<(\w+)>[^"]*"\s+(/[\w/-]+)\$(\w+);')


@dataclass(frozen=True)
class WebPath:
    file: str
    line: int
    raw: str
    method: str | None
    prefix_only: bool

    @property
    def key(self) -> tuple[str, str]:
        return (self.file, self.raw)


# ── server side ─────────────────────────────────────────────────────────────


def gateway_rewrites(conf_text: str) -> list[tuple[str, str]]:
    """``(public_prefix, internal_prefix)`` pairs from nginx ``map`` regex entries."""
    return [(m.group(1), m.group(3)) for m in _GATEWAY_REWRITE.finditer(conf_text)]


@lru_cache(maxsize=1)
def server_routes() -> frozenset[tuple[str, str]]:
    rows = json.loads(ROUTE_INVENTORY.read_text(encoding="utf-8"))
    routes = {(row["method"].upper(), row["path"]) for row in rows}
    for public, internal in gateway_rewrites(GATEWAY_CONF.read_text(encoding="utf-8")):
        for method, path in list(routes):
            if path == internal or path.startswith(internal + "/"):
                routes.add((method, public + path[len(internal) :]))
    return frozenset(routes)


# ── web side ────────────────────────────────────────────────────────────────


def scan_source(text: str, *, rel: str, jsx: bool) -> tuple[list[WebPath], str | None]:
    """Every ``/api/v1`` literal in executable code; adjacent ``'a' + 'b'`` are joined."""
    code, error = edges._scan_code(text, jsx=jsx)
    if error:
        return [], error
    found: list[WebPath] = []
    i = 0
    while i < len(code):
        if code[i] not in "\"'`":
            i += 1
            continue
        start = i
        end = edges._literal_end(text, i)
        raw = text[i + 1 : end - 1]
        prefix_only = False
        # Join a chain of literal concatenations; a non-literal operand makes it a prefix.
        while True:
            rest = code[end:]
            stripped = rest.lstrip()
            if not stripped.startswith("+"):
                break
            after_plus = stripped[1:].lstrip()
            nxt = end + (len(rest) - len(after_plus))
            if after_plus[:1] in ("'", '"', "`"):
                nxt_end = edges._literal_end(text, nxt)
                raw += text[nxt + 1 : nxt_end - 1]
                end = nxt_end
            else:
                prefix_only = True
                break
        if raw.startswith("/api/v1/") or raw == "/api/v1":
            call = _HTTP_CALL.search(code[max(0, start - 240) : start])
            found.append(
                WebPath(
                    file=rel,
                    line=text.count("\n", 0, start) + 1,
                    raw=raw,
                    method=call.group(1).upper() if call else None,
                    prefix_only=prefix_only,
                )
            )
        i = end
    return found, None


def _is_param(segment: str) -> bool:
    return _NAMED_PARAM.fullmatch(segment) is not None


def _segment_matches(web: str, route: str) -> bool:
    if _is_param(route):
        # A literal web segment never satisfies a route parameter: that is exactly how
        # `/recommendations/autonomous` passed for `/recommendations/{rec_id}`.
        return "{}" in web
    if "{}" in web:
        pattern = "[^/]*".join(re.escape(part) for part in web.split("{}"))
        return re.fullmatch(pattern, route) is not None
    return web == route


def _path_matches(web_segments: list[str], route_path: str) -> bool:
    route_segments = [s for s in route_path.split("/") if s]
    for index, route_seg in enumerate(route_segments):
        if route_seg.startswith("{") and route_seg.endswith(":path}"):
            return len(web_segments) > index
        if index >= len(web_segments) or not _segment_matches(web_segments[index], route_seg):
            return False
    return len(web_segments) == len(route_segments)


def _normalise(raw: str) -> str:
    path = _TEMPLATE_EXPR.sub("{}", raw).split("?", 1)[0]
    return _NAMED_PARAM.sub("{}", path)


def has_server_route(web: WebPath, routes: frozenset[tuple[str, str]]) -> bool:
    path = _normalise(web.raw)
    candidates = [
        route_path
        for method, route_path in routes
        if web.method is None or method in (web.method, "ANY")
    ]
    if web.prefix_only or "*" in path or path.endswith("/"):
        prefix = path.split("*", 1)[0].rstrip("/")
        prefix_segments = [s for s in prefix.split("/") if s]
        for route_path in candidates:
            route_segments = [s for s in route_path.split("/") if s]
            if len(route_segments) >= len(prefix_segments) and all(
                _segment_matches(w, r)
                for w, r in zip(prefix_segments, route_segments, strict=False)
            ):
                return True
        return False
    web_segments = [s for s in path.split("/") if s]
    return any(_path_matches(web_segments, route_path) for route_path in candidates)


def _is_scanned(path: Path) -> bool:
    return path.suffix in (".ts", ".tsx") and not edges._is_test_source(path)


@lru_cache(maxsize=1)
def frontend_paths() -> tuple[tuple[WebPath, ...], tuple[tuple[str, str], ...]]:
    found: list[WebPath] = []
    blind: list[tuple[str, str]] = []
    for path in sorted(FRONTEND_SRC.rglob("*")):
        if not _is_scanned(path):
            continue
        text = path.read_text(encoding="utf-8")
        if "/api/v1" not in text:
            continue
        rel = path.relative_to(ROOT).as_posix()
        items, error = scan_source(text, rel=rel, jsx=path.suffix == ".tsx")
        if error:
            blind.append((rel, error))
        found.extend(items)
    return tuple(found), tuple(blind)


def _unmatched(paths) -> list[WebPath]:
    routes = server_routes()
    return [p for p in paths if not has_server_route(p, routes)]


# ── the guard ───────────────────────────────────────────────────────────────


def test_no_frontend_file_holding_api_v1_is_lexically_unreadable():
    _, blind = frontend_paths()
    assert not blind, (
        "a frontend file that mentions /api/v1 could not be lexed, so its literals were "
        f"not checked (fail closed, not skipped): {blind}"
    )


def test_scan_reaches_the_frontend_api_surface():
    found, _ = frontend_paths()
    # The canonical client config documents its own /api/v1 calls; an empty scan means
    # the scanner went blind, not that the frontend stopped calling the platform.
    assert found, "no /api/v1 literal found under frontend/src: the scanner is blind"
    assert any(p.method for p in found), "no HTTP-call method was attributed to any literal"


def test_every_frontend_api_v1_literal_has_a_server_route():
    unmatched = [
        p for p in _unmatched(frontend_paths()[0]) if p.key not in KNOWN_UNMATCHED_COVERAGE_REGISTRY
    ]
    detail = "\n".join(f"  {p.file}:{p.line}  {p.method or 'ANY'} {p.raw}" for p in unmatched)
    assert not unmatched, (
        "frontend /api/v1 path(s) with no matching server route (method + path) in "
        "route_inventory.generated.json. Build the handler (and regenerate the inventory) "
        "or delete the constant; a path no server serves reads as capability that does "
        f"not exist (WEB-ENDPOINT-CONSTANTS-WITHOUT-SERVER-HANDLER-01):\n{detail}"
    )


def test_known_unmatched_baseline_has_no_stale_entries():
    found, _ = frontend_paths()
    present = {p.key for p in found}
    unmatched = {p.key for p in _unmatched(found)}
    stale = sorted(KNOWN_UNMATCHED_COVERAGE_REGISTRY - (present & unmatched))
    assert not stale, (
        "baseline entries that no longer exist or now match a route; delete them so the "
        f"debt list only shrinks: {stale}"
    )


# ── witnesses: the guard rejects what the gap found, and accepts real shapes ──

#: Verbatim from ``ae30a0fcf`` (the tree on which the gap was measured), embedded rather
#: than read from history: a test that needs a SHA is skipped in CI's depth-1 checkout.
_REMOVED_CONSTANTS_TS = """\
export const globalScaleRuntimeEndpoints = {
  topology: '/api/v1/gis/cloud-native/phase8/global/topology',
  loadMatrix: '/api/v1/gis/cloud-native/phase8/load/matrix',
  loadResults: '/api/v1/gis/cloud-native/phase8/load/results',
  disasterRecovery: '/api/v1/gis/cloud-native/phase8/disaster-recovery/plan',
  errorBudget: '/api/v1/gis/cloud-native/phase8/slo/error-budget',
  costGuardrails: '/api/v1/gis/cloud-native/phase8/cost/guardrails',
  releaseGate: '/api/v1/gis/cloud-native/phase8/release-gate',
} as const;
export const enterpriseGisPhase7Endpoints = {
  collaborationSession: '/api/v1/gis/collaboration/sessions',
  collaborationEvents: (sessionId: string) => `/api/v1/gis/collaboration/sessions/${sessionId}/events`,
  collaborationSocket: (sessionId: string) => `/ws/gis/collaboration/${sessionId}`,
  ogcLanding: '/ogc',
  ogcConformance: '/ogc/conformance',
  distributedRasterPlan: '/api/v1/gis/raster/distributed/plan',
  distributedRasterJobs: '/api/v1/gis/raster/distributed/jobs',
  digitalTwinScenario: '/api/v1/digital-twin/scenarios/simulate',
  autonomousRecommendations: '/api/v1/recommendations/autonomous',
  planetScaleReadiness: '/api/v1/gis/readiness/planet-scale',
};
"""


def test_guard_rejects_each_of_the_fourteen_removed_constants():
    found, error = scan_source(_REMOVED_CONSTANTS_TS, rel="fixture.ts", jsx=False)
    assert error is None
    assert len(found) == 14, [p.raw for p in found]
    accepted = [p.raw for p in found if has_server_route(p, server_routes())]
    assert not accepted, f"guard would let these back in: {accepted}"


def test_literal_segment_never_satisfies_a_route_parameter():
    autonomous = WebPath("f.ts", 1, "/api/v1/recommendations/autonomous", None, False)
    by_id = WebPath("f.ts", 1, "/api/v1/recommendations/${recId}", "GET", False)
    routes = server_routes()
    assert ("GET", "/api/v1/recommendations/{rec_id}") in routes, "precondition moved"
    assert not has_server_route(autonomous, routes)
    assert has_server_route(by_id, routes)


def test_method_is_part_of_the_match():
    get_state = (
        "kongApi.get(`/api/v1/fields/${encodeURIComponent(f)}` +\n"
        "  `/seasons/${encodeURIComponent(s)}/state`);\n"
    )
    delete_state = get_state.replace("kongApi.get(", "kongApi.delete(")
    routes = server_routes()
    (ok,), _ = scan_source(get_state, rel="f.ts", jsx=False)
    (bad,), _ = scan_source(delete_state, rel="f.ts", jsx=False)
    assert (ok.method, ok.raw.count("/")) == ("GET", 7), "concatenated literals must join"
    assert has_server_route(ok, routes)
    assert bad.method == "DELETE"
    assert not has_server_route(bad, routes)


def test_comments_are_not_constants_and_gateway_rewrites_apply():
    source = (
        "// kongApi.get('/api/v1/nowhere/at/all')\n"
        "/* '/api/v1/also/nowhere' */\n"
        "export const accept = (id: string) => kongApi.post(`/api/v1/seasons/${id}/accept`);\n"
    )
    found, error = scan_source(source, rel="f.ts", jsx=False)
    assert error is None
    assert [p.raw for p in found] == ["/api/v1/seasons/${id}/accept"]
    assert ("/api/v1/seasons", "/internal/seasons") in gateway_rewrites(
        GATEWAY_CONF.read_text(encoding="utf-8")
    )
    assert has_server_route(found[0], server_routes())

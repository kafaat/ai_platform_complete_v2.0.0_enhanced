"""Regression guards for defects measured by the 2026-09-02 live E2E pass."""

from __future__ import annotations

import ast
import importlib
import re
import sys
from pathlib import Path, PurePosixPath

import pytest
import yaml
from fastapi import HTTPException

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]


def _source(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_mfa_router_owns_its_crypto_dependencies():
    source = _source("services/auth/routers/mfa.py")
    tree = ast.parse(source)
    imports = {
        alias.name for node in tree.body if isinstance(node, ast.Import) for alias in node.names
    }
    assert {"mfa_crypto", "pyotp"} <= imports
    assert "main.mfa_crypto" not in source
    assert "main.pyotp" not in source


def test_market_runtime_tables_are_created_by_forward_migration():
    migration = _source("migrations/v229_market_mcp_schema.sql")
    required = {
        "market_suppliers",
        "market_products",
        "market_price_history",
        "market_procurement_orders",
        "market_procurement_items",
        "market_analytics_snapshots",
    }
    for table in required:
        assert f"CREATE TABLE IF NOT EXISTS {table}" in migration
        assert f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY" in migration
        assert f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY" in migration
        assert f"CREATE POLICY tenant_isolation ON {table}" in migration
    assert "v229_market_mcp_schema.sql" in _source("migrations/MANIFEST.txt")
    assert _source("migrations/MANIFEST.txt").rstrip().endswith("v206_rls_final_hardening.sql")


def test_market_tenant_guc_is_scoped_by_transaction_context():
    source = _source("services/mcp_servers/market_server.py")
    tree = ast.parse(source)
    functions = {node.name: node for node in tree.body if isinstance(node, ast.AsyncFunctionDef)}

    def transactions(function: ast.AsyncFunctionDef) -> list[ast.AsyncWith]:
        return [
            node
            for node in ast.walk(function)
            if isinstance(node, ast.AsyncWith)
            and any("transaction()" in ast.unparse(item.context_expr) for item in node.items)
        ]

    assert "async def tenant_connection" in source
    assert len(transactions(functions["tenant_connection"])) == 1
    assert transactions(functions["tool_create_procurement"]) == []
    assert source.count("async with tenant_connection(tenant_id) as conn:") == 10
    assert source.count("set_config('app.current_tenant'") == 1


def test_market_authz_guc_and_visibility_query_share_transaction():
    source = _source("services/mcp_servers/market_db_authz.py")
    tree = ast.parse(source)
    fn = next(
        n
        for n in tree.body
        if isinstance(n, ast.AsyncFunctionDef) and n.name == "batch_visible_under_tenant"
    )
    transactions = [
        n
        for n in ast.walk(fn)
        if isinstance(n, ast.AsyncWith) and "transaction()" in ast.unparse(n.items[0].context_expr)
    ]
    assert len(transactions) == 1
    body = ast.unparse(transactions[0])
    assert "set_config" in body and "inventory_batches" in body


@pytest.mark.asyncio
async def test_wofost_invalid_arguments_are_422_not_500(monkeypatch):
    mcp_dir = ROOT / "services" / "mcp_servers"
    monkeypatch.syspath_prepend(str(ROOT))
    monkeypatch.syspath_prepend(str(mcp_dir))
    saved_shared = {
        name: module
        for name, module in sys.modules.items()
        if name == "shared" or name.startswith("shared.")
    }
    for name in saved_shared:
        sys.modules.pop(name, None)
    sys.modules.pop("wofost_server", None)
    try:
        module = importlib.import_module("wofost_server")
        with pytest.raises(HTTPException) as caught:
            await module._execute("run_wofost_simulation", {"crop": "not-a-crop"})
        assert caught.value.status_code == 422
        assert isinstance(caught.value.detail, list)
    finally:
        for name in [n for n in sys.modules if n == "shared" or n.startswith("shared.")]:
            sys.modules.pop(name, None)
        sys.modules.update(saved_shared)


def test_compose_wires_mfa_key_and_outbox_switch():
    for compose in ("docker-compose.v9.yml", "docker-compose.fixed.yml"):
        source = _source(compose)
        assert "MFA_SECRET_ENCRYPTION_KEY:" in source
        assert "FEATURE_NATS_PUBLISHERS:" in source
        assert "JOBS_DATABASE_URL:" in source


def test_geometry_revert_decodes_jsonb_strings_before_guarding():
    source = _source("services/sahool-platform/api/routers/fields.py")
    fn = next(
        n
        for n in ast.parse(source).body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        and n.name == "revert_field_geometry"
    )
    rendered = ast.unparse(fn)
    assert "isinstance(raw_geometry, str)" in rendered
    assert "json.loads(raw_geometry)" in rendered
    assert rendered.index("json.loads(raw_geometry)") < rendered.index(
        "guard_field_geometry(raw_geometry)"
    )
    assert "stored_geometry_invalid" in rendered


def _service_block(source: str, service_name: str) -> str:
    match = re.search(
        rf"(?ms)^  {re.escape(service_name)}:\n(?P<body>.*?)(?=^  [^ \n][^:]*:|\Z)",
        source,
    )
    assert match is not None, service_name
    return match.group("body")


# nginx bundle -> (compose file that mounts it, nginx service name in that compose).
_NGINX_BUNDLES = {
    "nginx/nginx.v9.conf": ("docker-compose.v9.yml", "sahool-nginx"),
    "nginx/nginx.fixed.conf": ("docker-compose.fixed.yml", "sahool-nginx"),
    "nginx/nginx.unified.conf": ("docker-compose.unified.yml", "nginx"),
    "nginx/nginx.light.conf": ("docker-compose.light.yml", "nginx"),
}
# Every nginx config that proxies browser/API traffic (the four bundles + the SPA container).
_NGINX_CONFIGS = (*_NGINX_BUNDLES, "frontend/nginx.conf")


def _nginx_live(text: str) -> str:
    """Drop `#` comments so commented-out directives cannot satisfy or fail an assertion."""
    return "\n".join(line.split("#", 1)[0] for line in text.splitlines())


def _location_blocks(text: str) -> list[tuple[str, str]]:
    """(selector, body) for each `location` block, brace-matched; quoted `${VAR}` is skipped."""
    text = _nginx_live(text)
    blocks = []
    for match in re.finditer(r"\blocation\s+([^{;]+?)\s*\{", text):
        depth, quote, i = 1, None, match.end()
        while depth and i < len(text):
            char = text[i]
            if quote:
                quote = None if char == quote else quote
            elif char in "\"'":
                quote = char
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
            i += 1
        blocks.append((match.group(1).strip(), text[match.end() : i - 1]))
    return blocks


def test_v25_live_audit_wiring_regressions():
    variants = {
        "docker-compose.v9.yml": ("sahool-supervisor-agent", "sahool-local-ai-rag"),
        "docker-compose.fixed.yml": ("sahool-supervisor-agent", "sahool-local-ai-rag"),
        "docker-compose.unified.yml": ("supervisor-agent", "local-ai-rag"),
    }

    # Finding #6: the tiler must recover after daemon restarts; it is v9-only — fixed/unified
    # dropped it (no consumer: TILER-IN-FIXED-AND-UNIFIED-HAS-NO-CONSUMER-AND-CANNOT-BUILD-01).
    tiler = _service_block(_source("docker-compose.v9.yml"), "raster-tiler-service")
    assert "restart: unless-stopped" in tiler
    assert not [c for c in variants if "v9" not in c and "\n  raster-tiler-service:" in _source(c)]

    # Finding #5: scope the RAG wiring assertion to the supervisor service itself,
    # so an unrelated variable elsewhere cannot make this test pass.
    for compose, (supervisor_name, rag_name) in variants.items():
        source = _source(compose)
        supervisor = _service_block(source, supervisor_name)
        if compose == "docker-compose.unified.yml":
            assert 'LOCAL_AI_RAG_URL: "http://sahool-unified-local-ai-rag:8000"' in supervisor
        else:
            assert (
                "LOCAL_AI_RAG_URL: ${LOCAL_AI_RAG_URL:-http://sahool-local-ai-rag:8000}"
                in supervisor
            )

        # supervisor and local-ai-rag must agree on the verifier mode. In RS256
        # deployments a missing JWT_PUBLIC_KEY silently falls back to HS256 and
        # causes /v1/query bearer validation to fail with 401.
        assert "JWT_SECRET:" in supervisor
        assert "JWT_PUBLIC_KEY:" in supervisor
        rag = _service_block(source, rag_name)
        assert "JWT_SECRET:" in rag
        assert "JWT_PUBLIC_KEY:" in rag

    # Finding #1: every active upstream in **every** gateway bundle must be re-resolved
    # after a container is replaced. The resolve parameter requires a shared-memory
    # upstream zone and nginx >= 1.27.3. Previously only v9 was asserted, so fixed and
    # unified (26 upstreams) and light (7) kept the audit's boot-time-pinned 502.
    for conf, (compose, service) in _NGINX_BUNDLES.items():
        nginx_service = _service_block(_source(compose), service)
        assert f"./{conf}:" in nginx_service, (compose, conf)
        image = re.search(r"image:\s*nginx:(\d+)\.(\d+)\.(\d+)-alpine\b", nginx_service)
        assert image is not None, f"{compose}: nginx image must be a pinned version tag"
        assert tuple(int(p) for p in image.groups()) >= (1, 27, 3), compose

        nginx = _nginx_live(_source(conf))
        assert "resolver 127.0.0.11 valid=10s ipv6=off;" in nginx, conf
        assert re.search(r"\bresolver_timeout\s+\d+s;", nginx), conf
        upstreams = re.findall(r"(?ms)^\s*upstream\s+([^\s{]+)\s*\{([^}]*)\}", nginx)
        assert upstreams, conf
        for name, body in upstreams:
            assert re.search(r"\bzone\s+" + re.escape(name) + r"\s+64k;", body), (conf, name)
            servers = re.findall(r"\bserver\s+([^;]+);", body)
            assert servers, (conf, name)
            for server in servers:
                assert re.search(r"\sresolve\b", server), (conf, name, server)

        # A literal `proxy_pass http://host:port` bypasses the upstream zone: it is
        # resolved once at boot (and fails boot when the name is absent). Every
        # proxy_pass must name a declared upstream.
        names = {name for name, _ in upstreams}
        for target in re.findall(r"\bproxy_pass\s+([^;]+);", nginx):
            host = re.match(r"https?://([^/$;]+)", target.strip())
            assert host is not None, (conf, target)
            assert host.group(1) in names, (conf, target)

    nginx = _source("nginx/nginx.v9.conf")

    # Finding #4, narrowed to the current trust model.
    agriai = nginx.split("location /api/agriai/", 1)[1].split("location /api/", 1)[0]
    assert 'proxy_set_header X-Agent-Token "${SAHOOL_AGENT_TOKEN}";' in agriai

    # Guardrails keeps the existing caller contract: the browser sends /v1 in
    # the suffix and nginx only strips /api/guardrails/. The service token stays
    # private, so direct browser validation still fails closed by design.
    guardrails = nginx.split("location /api/guardrails/", 1)[1].split("location /api/rag/", 1)[0]
    assert "proxy_pass http://guardrails_backend/;" in guardrails
    assert "proxy_pass http://guardrails_backend/v1/;" not in guardrails
    assert "proxy_set_header X-Agent-Token" not in guardrails
    assert "/api/guardrails/v1/validate" in _source("frontend/src/hooks/useApi.ts")


def _frontend_image_listen_ports() -> set[int]:
    """Ports the frontend image listens on, derived the way `docker build` produces them:
    frontend/nginx.conf is copied to conf.d/default.conf and the Dockerfile's own `sed -i`
    edits are applied to it. Cross-checked against EXPOSE so neither side drifts alone."""
    dockerfile = _source("frontend/Dockerfile")
    assert "COPY nginx.conf /etc/nginx/conf.d/default.conf" in dockerfile
    conf = _source("frontend/nginx.conf")
    for old, new in re.findall(
        r"sed -i 's/([^/]*)/([^/]*)/' /etc/nginx/conf\.d/default\.conf", dockerfile
    ):
        conf = conf.replace(old, new)
    listens = {
        int(port)
        for port in re.findall(r"(?m)^\s*listen\s+(?:\S*:)?(\d+)(?=[\s;])", _nginx_live(conf))
    }
    exposed = {int(port) for port in re.findall(r"(?m)^EXPOSE\s+(\d+)", dockerfile)}
    assert listens and listens == exposed, (listens, exposed)
    return listens


def test_every_bundle_routes_the_spa_to_the_port_the_frontend_image_listens_on():
    """NGINX-LIGHT-AND-UNIFIED-FRONTEND-PORT-MISMATCH-01, measured with nginx 1.27.5 running the
    real frontend image config: light and unified sent the SPA to :80 while the non-root image
    listens on 8080 (`listen 8080;` — the Dockerfile's `sed 's/listen 80;/…/'` matches nothing),
    so every SPA path through either gateway was 502 `connect() failed (111: Connection
    refused)`; 200 after the fix. The Finding-#1 loop above asserts *how* each upstream is
    resolved, never *where* it lands, and the older pin `"frontend:80" in src` is a substring
    of both ports. The port is derived from the image build here, not typed."""
    ports = _frontend_image_listen_ports()
    for conf, (compose_file, _nginx_service) in _NGINX_BUNDLES.items():
        services = yaml.safe_load(_source(compose_file))["services"]
        frontends = {
            name: svc
            for name, svc in services.items()
            if isinstance(svc.get("build"), dict)
            and PurePosixPath(svc["build"].get("context", "")) == PurePosixPath("frontend")
        }
        assert len(frontends) == 1, (compose_file, sorted(frontends))
        ((name, svc),) = frontends.items()
        assert svc["build"].get("dockerfile", "Dockerfile") == "Dockerfile", compose_file

        upstreams = dict(
            re.findall(r"(?ms)^\s*upstream\s+([^\s{]+)\s*\{([^}]*)\}", _nginx_live(_source(conf)))
        )
        servers = re.findall(r"\bserver\s+([A-Za-z0-9_.-]+):(\d+)\b", upstreams["frontend_backend"])
        assert servers, conf
        for host, port in servers:
            assert host in {name, svc.get("container_name", name)}, (conf, host)
            assert int(port) in ports, (conf, f"{host}:{port}", ports)

        # The compose side must describe the same container port it exposes, publishes or probes.
        declared = [str(p) for p in svc.get("expose") or []]
        declared += [str(p).rsplit(":", 1)[-1] for p in svc.get("ports") or []]
        declared += re.findall(r"localhost:(\d+)", str((svc.get("healthcheck") or {}).get("test")))
        assert declared, compose_file
        for port in declared:
            assert int(port.split("/", 1)[0]) in ports, (compose_file, name, port, ports)


def test_service_token_is_injected_only_behind_auth_request():
    """Finding #2 of the v25 review, measured with a real nginx: the agriai block injected
    `X-Agent-Token` on network position alone. real_ip trusts X-Forwarded-For from the same
    private ranges the allowlist admits, so a private peer without XFF, or with a forged
    `X-Forwarded-For: 10.9.9.9`, received 200 with the token injected — i.e. any public client
    arriving through a private hop (Docker Desktop port forwarding, an LB without XFF,
    docker-proxy for IPv6). A location that injects a server-side service token must verify
    the caller first; the private allowlist stays as defence in depth, not as identity."""
    injecting = []
    for conf in _NGINX_CONFIGS:
        for selector, body in _location_blocks(_source(conf)):
            if re.search(r'\bproxy_set_header\s+X-[A-Za-z-]*Token\s+"[^"]+"', body):
                injecting.append((conf, selector))
                assert re.search(r"\bauth_request\s+/", body), (conf, selector)
    assert ("nginx/nginx.v9.conf", "/api/agriai/") in injecting, injecting

    agriai = dict(_location_blocks(_source("nginx/nginx.v9.conf")))["/api/agriai/"]
    assert "deny all;" in agriai
    # identity reaches the service only from the verified auth response, never the client.
    assert re.search(r"auth_request_set\s+\$tenant\s+\$upstream_http_x_tenant_id;", agriai)
    assert re.search(r"proxy_set_header\s+X-Tenant-Id\s+\$tenant;", agriai)
    assert re.search(r"proxy_set_header\s+X-User-Id\s+\$auth_uid;", agriai)


def test_ai_agronomist_healthz_is_exact_matched_before_the_v1_prefix():
    """M5 of the v25 review: `location /api/ai-agronomist/ { proxy_pass …/v1/; }` rewrote the
    probe to /v1/healthz, but the service serves /healthz — every smoke/recovery probe
    (scripts/runtime_smoke.sh, scripts/recovery/recovery_smoke.sh) got 401, and 404 with a
    token. The exact match mirrors `location = /api/agent/health`: an unauthenticated liveness
    probe, and only the exact path — /healthz/ai-provider and the rest stay behind auth_request."""
    assert '@app.get("/healthz")' in _source("services/ai_agronomist/main.py")
    routed = []
    for conf in _NGINX_CONFIGS:
        blocks = _location_blocks(_source(conf))
        prefix = [b for sel, b in blocks if re.fullmatch(r"(\^~\s+)?/api/ai-agronomist/", sel)]
        if not prefix:
            continue
        routed.append(conf)
        assert re.search(r"\bauth_request\s+/", prefix[0]), conf
        health = [b for sel, b in blocks if sel == "= /api/ai-agronomist/healthz"]
        assert len(health) == 1, conf
        assert re.search(r"\bproxy_pass\s+http://[A-Za-z0-9_]+/healthz;", health[0]), conf
        assert "auth_request" not in health[0], conf
    assert {"nginx/nginx.v9.conf", "frontend/nginx.conf"} <= set(routed), routed

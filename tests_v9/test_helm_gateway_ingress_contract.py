"""Helm production boot env and gateway-only Ingress (W0-04, W0-06; deploy-1/2/12).

W0-04 / deploy-1: the chart rendered no ``REDIS_URL`` for sahool-platform (its JWT
denylist refuses to boot without Redis in production) and no ``JWT_PUBLIC_KEY`` for
guardrails and raster (RS256 is mandatory in production), so a production install could
not start. ``PRODUCTION_REQUIRED_ENV`` in scripts/deploy/validate_helm_readiness.py names
each mandatory variable with the code that enforces it; the chart must render every one.

W0-06 / deploy-2 / deploy-12: the Ingress routed each workload's prefix straight to its
Service: no rewrite to the ``/v1/*`` paths the services serve, no JWT verification, and a
client-sent ``X-Tenant-Id`` reached raster and ai-agronomist, which derive the tenant from
it. The Ingress now has one backend, the SAHOOL gateway (nginx ``auth_request`` ->
auth ``/v1/auth/verify`` -> verified tenant injection, client identity headers cleared),
and NetworkPolicy admits raster only from the gateway and sahool-platform (its one
in-cluster caller) and ai-agronomist only from the gateway. The gateway resolves auth per
request, so it starts before the auth Service exists and fails verified routes closed.

Three layers, so the contract is enforced in every environment:
  1. structural checks on values, templates and files/gateway (no helm, no nginx);
  2. the gateway's own nginx files run in a real nginx against stub auth and services
     (skipped only when the nginx binary is absent);
  3. ``helm template`` with values-production.yaml (skipped only when helm is absent).
"""

from __future__ import annotations

import copy
import importlib.util
import os
import re
import shutil
import socket
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
CHART = ROOT / "helm" / "sahool"
GATEWAY_FILES = CHART / "files" / "gateway"


def _validator():
    spec = importlib.util.spec_from_file_location(
        "validate_helm_readiness", ROOT / "scripts" / "deploy" / "validate_helm_readiness.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


VALIDATOR = _validator()


def _production_values() -> dict:
    base = VALIDATOR.load_yaml(CHART / "values.yaml")
    overlay = VALIDATOR.load_yaml(CHART / "values-production.yaml")
    return VALIDATOR.deep_merge(base, overlay)


def _upstream_name(workload: str) -> str:
    return workload.replace("-", "_")


# ── 1. structural: production env (W0-04) ───────────────────────────────────────


def test_production_values_render_every_mandatory_env_var() -> None:
    errors = VALIDATOR.production_env_errors(_production_values())
    assert errors == [], f"production values miss mandatory env vars: {errors}"


@pytest.mark.parametrize(
    ("workload", "var"),
    [
        ("sahool-platform", "REDIS_URL"),
        ("sahool-guardrails-engine", "JWT_PUBLIC_KEY"),
        ("sahool-raster-service", "JWT_PUBLIC_KEY"),
    ],
)
def test_removing_a_mandatory_var_fails_the_contract(workload: str, var: str) -> None:
    values = copy.deepcopy(_production_values())
    values["workloads"][workload]["secretEnv"].pop(var)
    values["workloads"][workload].get("env", {}).pop(var, None)
    errors = VALIDATOR.production_env_errors(values)
    assert any(workload in e and var in e for e in errors), (
        f"dropping {var} from {workload} must fail the production env contract, got {errors}"
    )


def test_a_secret_env_pointing_at_an_undeclared_secret_ref_fails() -> None:
    values = copy.deepcopy(_production_values())
    del values["global"]["secretRefs"]["redisUrl"]
    errors = VALIDATOR.production_env_errors(values)
    assert any("REDIS_URL" in e and "redisUrl" in e for e in errors), (
        f"a secretKeyRef with no global.secretRefs entry renders an empty name: {errors}"
    )


def test_the_contract_names_variables_the_cited_code_actually_reads() -> None:
    for workload, required in VALIDATOR.PRODUCTION_REQUIRED_ENV.items():
        for var, source in required.items():
            path = ROOT / re.split(r"[: ]", source, maxsplit=1)[0]
            assert path.is_file(), f"{workload}/{var}: cited source {path} does not exist"
            assert var in path.read_text(encoding="utf-8") or (
                var == "REDIS_URL" and "denylist_redis_url" in path.read_text(encoding="utf-8")
            ), f"{workload}/{var}: {path} never reads {var}; the contract has drifted"


def test_the_production_readiness_validator_passes() -> None:
    result = subprocess.run(
        ["python", "scripts/deploy/validate_helm_readiness.py", "--env", "production"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert result.returncode == 0, f"validator failed:\n{result.stdout}{result.stderr}"


# ── 1. structural: gateway-only Ingress (W0-06) ─────────────────────────────────


def test_the_ingress_has_one_backend_the_gateway() -> None:
    text = (CHART / "templates" / "ingress.yaml").read_text(encoding="utf-8")
    assert ".Values.workloads" not in text, "the Ingress must not loop over workloads"
    backends = re.findall(r"service:\s*\n\s+name:\s*(\S+)", text)
    assert backends == ["sahool-gateway"], f"Ingress backends must be only the gateway: {backends}"
    assert "gateway.enabled" in text and "fail" in text, (
        "the Ingress must refuse to render without the gateway rather than fall back"
    )


def test_gateway_errors_are_empty_and_catch_a_direct_route() -> None:
    values = _production_values()
    assert VALIDATOR.gateway_errors(values) == [], VALIDATOR.gateway_errors(values)
    broken = copy.deepcopy(values)
    broken["workloads"]["sahool-raster-service"]["gatewayOnly"] = False
    assert any("sahool-raster-service" in e for e in VALIDATOR.gateway_errors(broken)), (
        "raster without gatewayOnly must fail the gateway contract"
    )
    broken = copy.deepcopy(values)
    broken["gateway"]["enabled"] = False
    assert any("gateway.enabled" in e for e in VALIDATOR.gateway_errors(broken)), (
        "an enabled Ingress without the gateway must fail the gateway contract"
    )


def _locations(text: str) -> dict[str, str]:
    """Map each `location` header (modifier + pattern) to its body. No nested blocks."""
    out: dict[str, str] = {}
    for m in re.finditer(r"^location\s+([^{]+?)\s*\{", text, re.M):
        depth, i = 1, m.end()
        while depth:
            depth += {"{": 1, "}": -1}.get(text[i], 0)
            i += 1
        out[m.group(1).strip()] = text[m.end() : i - 1]
    return out


def _routes() -> dict[str, str]:
    return _locations((GATEWAY_FILES / "routes.conf").read_text(encoding="utf-8"))


# W3-09: enabled workloads the gateway does not route by pathPrefix, with the reason. Every
# other enabled workload must declare a pathPrefix that has a route.
_UNROUTED_WORKLOADS = {
    # Addressed by $sahool_auth_addr (gateway.auth), in /_auth_verify and /auth/.
    "sahool-auth": "gateway.auth",
    # /api/weather/ goes to sahool-platform, which calls weather-service internally.
    "sahool-weather-service": "internal: sahool-platform",
    # /api/soil/ goes to sahool-platform's service proxy, which calls soil-service.
    "sahool-soil-service": "internal: sahool-platform",
    # Called with its bearer by sahool-platform and sahool-raster-service; no public route.
    "sahool-decision-service": "internal: bearer-authenticated",
    # /api/v1/field-tasks/ needs a gateway-injected token the chart's ConfigMap cannot hold.
    "sahool-field-management": "internal: token + tenant assertion",
}


def test_workloads_without_a_prefix_are_exactly_the_declared_ones() -> None:
    unrouted = {
        name
        for name, spec in _production_values()["workloads"].items()
        if spec.get("enabled") and not spec.get("pathPrefix")
    }
    assert unrouted == set(_UNROUTED_WORKLOADS), (
        f"a workload without pathPrefix must be declared unrouted with its reason: {unrouted}"
    )


def test_every_enabled_workload_prefix_has_a_gateway_route() -> None:
    routes = _routes()
    for name, spec in _production_values()["workloads"].items():
        if not spec.get("enabled") or name in _UNROUTED_WORKLOADS:
            continue
        prefix = spec["pathPrefix"].rstrip("/") + "/"
        assert prefix in routes, f"{name}: no gateway route for {prefix}"
        assert f"http://{_upstream_name(name)}" in routes[prefix], (
            f"{name}: the {prefix} route must proxy to upstream {_upstream_name(name)}"
        )


def test_routes_name_only_upstreams_the_chart_renders() -> None:
    known = {
        _upstream_name(n)
        for n, spec in _production_values()["workloads"].items()
        if spec.get("pathPrefix")
    }
    text = (GATEWAY_FILES / "routes.conf").read_text(encoding="utf-8")
    used = set(re.findall(r"proxy_pass\s+http://([a-z_]+)", text))
    assert used and used <= known, f"routes use upstreams the chart never renders: {used - known}"
    auth_targets = set(re.findall(r"proxy_pass\s+http://(\$[a-z_]+)", text))
    assert auth_targets == {"$sahool_auth_addr"}, (
        f"auth must be addressed only through $sahool_auth_addr: {auth_targets}"
    )
    helper = (CHART / "templates" / "_helpers.tpl").read_text(encoding="utf-8")
    assert 'replace "-" "_"' in helper, "the helper must render the underscored upstreams"


def test_auth_is_resolved_per_request_so_the_gateway_starts_without_it() -> None:
    """Review MEDIUM: a static `upstream sahool_auth` made nginx exit at start-up
    (`host not found in upstream`) because the chart does not deploy auth, so `helm
    --atomic` rolled back the whole release. The auth host is now a variable resolved by
    `resolver` per request; a missing Service fails the verified routes, not the boot."""
    helper = (CHART / "templates" / "_helpers.tpl").read_text(encoding="utf-8")
    assert "upstream sahool_auth" not in helper, (
        "a static auth upstream is resolved at start-up and kills nginx without the Service"
    )
    assert re.search(r"^resolver \{\{ required .*\.Values\.gateway\.resolver", helper, re.M), (
        "the helper must render a `resolver` from gateway.resolver"
    )
    assert "map $host $sahool_auth_addr" in helper and ".svc." in helper, (
        "the auth address must be a fully qualified Service name (nginx resolver has no "
        "search domains)"
    )
    values = _production_values()
    assert values["gateway"]["resolver"], "gateway.resolver must be set"
    broken = copy.deepcopy(values)
    broken["gateway"]["resolver"] = ""
    assert any("gateway.resolver" in e for e in VALIDATOR.gateway_errors(broken)), (
        "an empty resolver must fail the gateway contract"
    )


def test_the_chart_deploys_the_auth_verifier_and_warns_when_it_does_not() -> None:
    """W3-09: the chart deploys services/auth as the gateway's verifier. The deploy-path
    notice now speaks only when the auth workload is absent or disabled."""
    values = _production_values()
    auth = values["workloads"][values["gateway"]["auth"]["serviceName"]]
    assert auth["enabled"] and auth["port"] == values["gateway"]["auth"]["port"], (
        "the gateway's auth address must be the deployed auth workload and its port"
    )
    assert VALIDATOR.gateway_auth_notice(values) is None
    disabled = copy.deepcopy(values)
    disabled["workloads"]["sahool-auth"]["enabled"] = False
    notice = VALIDATOR.gateway_auth_notice(disabled)
    assert notice and "sahool-auth" in notice and "fail closed" in notice, (
        f"a disabled auth workload must still be reported: {notice}"
    )
    moved = copy.deepcopy(values)
    moved["workloads"]["sahool-auth"]["port"] = 8001
    assert any("gateway.auth.port" in e for e in VALIDATOR.gateway_errors(moved)), (
        "a gateway auth port that misses the auth workload port must fail"
    )
    result = subprocess.run(
        ["python", "scripts/deploy/validate_helm_readiness.py", "--env", "production"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert result.returncode == 0, result.stdout
    assert "does not deploy the auth Service" not in result.stdout, (
        f"the chart deploys auth, so the validator must not warn about it:\n{result.stdout}"
    )
    deploy = (ROOT / "scripts" / "deploy" / "deploy_production.sh").read_text(encoding="utf-8")
    assert 'kubectl --namespace sahool get service "$AUTH_SERVICE"' in deploy, (
        "deploy_production.sh must check for the auth Service after the install"
    )


def test_an_empty_trusted_ingress_namespace_list_is_refused() -> None:
    """Review LOW: an empty list rendered `from:` with no peers, which admits every source."""
    broken = copy.deepcopy(_production_values())
    broken["networkPolicy"]["trustedIngressNamespaces"] = []
    assert any("trustedIngressNamespaces" in e for e in VALIDATOR.gateway_errors(broken)), (
        "an empty trustedIngressNamespaces must fail the gateway contract"
    )
    text = (CHART / "templates" / "networkpolicy.yaml").read_text(encoding="utf-8")
    assert "if not .Values.networkPolicy.trustedIngressNamespaces" in text and "fail " in text, (
        "the template must refuse to render an empty ingress-controller `from`"
    )


def test_identity_is_cleared_first_and_injected_only_after_auth_request() -> None:
    for header, body in _routes().items():
        if header == "= /_auth_verify" or "proxy_pass" not in body:
            continue
        assert "include proxy_params.conf;" in body, f"{header}: must include proxy_params.conf"
        include_at = body.index("include proxy_params.conf;")
        for m in re.finditer(r"proxy_set_header\s+(X-Tenant-Id|X-User-Id|X-User-Role)\s", body):
            assert m.start() > include_at, (
                f"{header}: {m.group(1)} set before proxy_params.conf would be cleared again"
            )
            assert "auth_request /_auth_verify;" in body, (
                f"{header}: injects {m.group(1)} without auth_request (unverified identity)"
            )


def test_raster_and_agronomist_routes_verify_the_jwt_and_rewrite_to_v1() -> None:
    routes = _routes()
    raster = routes["/api/raster/"]
    assert "auth_request /_auth_verify;" in raster, "raster route must verify the JWT"
    assert "proxy_pass http://sahool_raster_service/;" in raster, "raster prefix must be stripped"
    agronomist = routes["/api/ai-agronomist/"]
    assert "auth_request /_auth_verify;" in agronomist, "agronomist route must verify the JWT"
    assert "proxy_pass http://sahool_ai_agronomist/v1/;" in agronomist, (
        "agronomist prefix must be rewritten to /v1/ (deploy-2)"
    )
    assert "internal;" in routes["= /_auth_verify"], "the verify location must be internal"
    assert "http://$sahool_auth_addr/v1/auth/verify" in routes["= /_auth_verify"], (
        "auth_request must reach auth GET /v1/auth/verify"
    )


def _cleared(path: Path) -> set[str]:
    text = path.read_text(encoding="utf-8")
    return {h.lower() for h in re.findall(r'^proxy_set_header\s+(\S+)\s+""\s*;', text, re.M)}


def test_gateway_clears_every_header_the_compose_gateway_clears_and_more() -> None:
    chart = _cleared(GATEWAY_FILES / "proxy_params.conf")
    compose = _cleared(ROOT / "nginx" / "proxy_params.conf")
    assert compose <= chart, f"chart gateway forgets to clear: {compose - chart}"
    for header in ("x-tenant-id", "x-tenant-assertion", "x-user-id", "x-user-role"):
        assert header in chart, f"chart gateway must clear client-sent {header}"


# raster: sahool-platform's raster_service_client. ai-agronomist: no in-code caller.
_EXPECTED_CALLERS = {"sahool-raster-service": ["sahool-platform"], "sahool-ai-agronomist": []}


def test_network_policy_admits_gateway_only_workloads_from_gateway_and_callers() -> None:
    values = _production_values()
    for name in VALIDATOR.GATEWAY_ONLY_WORKLOADS:
        spec = values["workloads"][name]
        assert spec.get("gatewayOnly") is True, f"{name} must be gatewayOnly"
        assert spec.get("internalCallers") == _EXPECTED_CALLERS[name], (
            f"{name}: in-cluster callers must be exactly the code that calls it"
        )
    text = (CHART / "templates" / "networkpolicy.yaml").read_text(encoding="utf-8")
    assert "operator: NotIn" in text and "$workload.gatewayOnly" in text, (
        "the namespace-wide allow must exclude gatewayOnly workloads (policies are additive)"
    )
    assert "app.kubernetes.io/component: sahool-gateway" in text, (
        "gatewayOnly workloads must admit the gateway pods by label"
    )
    gateway_policy = text.split("name: sahool-gateway-from-ingress-controller", 1)
    assert len(gateway_policy) == 2, "a policy must admit the ingress controller to the gateway"
    before = gateway_policy[0]
    assert "trustedIngressNamespaces" not in before, (
        "ingress controller namespaces must reach only the gateway, not every workload"
    )


# ── 2. real nginx with the chart's gateway files ────────────────────────────────


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


_ECHO = (
    'return 200 "{name} $request_uri tenant=[$http_x_tenant_id] '
    "user=[$http_x_user_id] role=[$http_x_user_role] "
    'assertion=[$http_x_tenant_assertion] agent=[$http_x_agent_token]\\n";'
)


def _test_upstreams(workloads: list[str], *, auth_addr: str | None = None) -> str:
    """The chart's upstream names, each served by an in-process stub server.

    ``auth_addr`` replaces the stub auth with a host name nothing resolves (the resolver
    points at a closed local port), as in a namespace where auth is not deployed."""
    auth_port = _free_port()
    lines = [
        f"resolver 127.0.0.1:{_free_port()} valid=10s ipv6=off;",
        "resolver_timeout 1s;",
        f'map $host $sahool_auth_addr {{ default "{auth_addr or f"127.0.0.1:{auth_port}"}"; }}',
        f"""server {{ listen 127.0.0.1:{auth_port};
  location = /v1/auth/verify {{
    if ($http_authorization = "Bearer good") {{
      add_header X-Tenant-ID tenant-verified; add_header X-User-Id user-verified;
      add_header X-User-Role farmer; return 200;
    }}
    return 401;
  }}
  location / {{ {_ECHO.format(name="auth")} }}
}}""",
    ]
    for name in workloads:
        port = _free_port()
        lines.append(f"upstream {_upstream_name(name)} {{ server 127.0.0.1:{port}; }}")
        lines.append(
            f"server {{ listen 127.0.0.1:{port}; location / {{ {_ECHO.format(name=name)} }} }}"
        )
    return "\n".join(lines)


def _run_gateway(tmp: Path, auth_addr: str | None = None):
    port = _free_port()
    conf = (GATEWAY_FILES / "nginx.conf").read_text(encoding="utf-8")
    assert "listen 8080;" in conf, "the gateway listens on 8080 (values gateway.port)"
    conf = conf.replace("listen 8080;", f"listen 127.0.0.1:{port};").replace("/tmp/", f"{tmp}/")
    (tmp / "nginx.conf").write_text(conf, encoding="utf-8")
    for rel in ("routes.conf", "proxy_params.conf"):
        shutil.copy(GATEWAY_FILES / rel, tmp / rel)
    workloads = sorted(_production_values()["workloads"])
    (tmp / "upstreams.conf").write_text(
        _test_upstreams(workloads, auth_addr=auth_addr), encoding="utf-8"
    )
    cmd = ["nginx", "-p", str(tmp), "-c", str(tmp / "nginx.conf")]
    check = subprocess.run(cmd + ["-t"], capture_output=True, text=True, encoding="utf-8")
    assert check.returncode == 0, f"nginx -t rejected the chart gateway config:\n{check.stderr}"
    log = (tmp / "stderr.log").open("w", encoding="utf-8")
    proc = subprocess.Popen(cmd + ["-g", "daemon off;"], stdout=subprocess.DEVNULL, stderr=log)
    try:
        yield port
    finally:
        proc.terminate()
        proc.wait(timeout=10)
        log.close()


@pytest.fixture(scope="module")
def gateway(tmp_path_factory):
    if shutil.which("nginx") is None:
        pytest.skip("nginx binary not installed")
    yield from _run_gateway(tmp_path_factory.mktemp("gateway"))


@pytest.fixture(scope="module")
def gateway_without_auth(tmp_path_factory):
    if shutil.which("nginx") is None:
        pytest.skip("nginx binary not installed")
    yield from _run_gateway(
        tmp_path_factory.mktemp("gateway-noauth"),
        auth_addr="sahool-auth.sahool.svc.cluster.local:8000",
    )


def _get(port: int, path: str, headers: dict[str, str] | None = None) -> tuple[int, str]:
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", headers=headers or {})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    for _ in range(50):
        try:
            with opener.open(req, timeout=5) as r:
                return r.status, r.read().decode().strip()
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode().strip()
        except urllib.error.URLError:
            time.sleep(0.1)
    raise AssertionError(f"gateway did not answer on {port}")


_FORGED = {
    "X-Tenant-Id": "tenant-evil",
    "X-Tenant-Assertion": "forged",
    "X-User-Id": "user-evil",
    "X-User-Role": "admin",
    "X-Agent-Token": "stolen",
}


def test_raster_gets_the_verified_tenant_not_the_forged_one(gateway: int) -> None:
    status, body = _get(
        gateway,
        "/api/raster/v1/fields/f1/timeseries",
        {"Authorization": "Bearer good", **_FORGED},
    )
    assert status == 200, f"verified raster request must pass: {status} {body}"
    assert body.startswith("sahool-raster-service /v1/fields/f1/timeseries "), (
        f"the /api/raster prefix must be stripped to the service's /v1 path: {body}"
    )
    assert "tenant=[tenant-verified]" in body, f"forged X-Tenant-Id must be replaced: {body}"
    assert "assertion=[]" in body and "agent=[]" in body, f"forged headers must be cleared: {body}"


def test_raster_without_a_valid_token_is_rejected_before_the_service(gateway: int) -> None:
    status, body = _get(gateway, "/api/raster/v1/fields/f1/timeseries", dict(_FORGED))
    assert status == 401, f"no bearer must be rejected by auth_request: {status} {body}"
    assert "sahool-raster-service" not in body, f"the service must not be reached: {body}"
    status, body = _get(gateway, "/api/raster/v1/x", {"Authorization": "Bearer bad", **_FORGED})
    assert status == 401, f"an invalid bearer must be rejected: {status} {body}"


def test_raster_tiles_verify_the_session_cookie(gateway: int) -> None:
    status, body = _get(gateway, "/api/raster/v1/tiles/1/2/3.png", {"Cookie": "sahool_at=good"})
    assert status == 200 and "tenant=[tenant-verified]" in body, (
        f"a tile with the HttpOnly session cookie must be verified and pass: {status} {body}"
    )


def test_raster_tiles_accept_the_access_token_query(gateway: int) -> None:
    """Review LOW: a `set $fwd_auth` in the tile location was lost in the subrequest, so
    the query fallback always answered 401. It now reaches /_auth_verify."""
    status, body = _get(gateway, "/api/raster/v1/tiles/1/2/3.png?access_token=good", _FORGED)
    assert status == 200 and "tenant=[tenant-verified]" in body, (
        f"a tile with a valid access_token query must be verified and pass: {status} {body}"
    )
    status, body = _get(gateway, "/api/raster/v1/tiles/1/2/3.png?access_token=bad")
    assert status == 401, f"an invalid access_token query must be rejected: {status} {body}"
    status, body = _get(
        gateway, "/api/raster/v1/tiles/1/2/3.png?access_token=bad", {"Cookie": "sahool_at=good"}
    )
    assert status == 200, f"the session cookie wins over the query token: {status} {body}"
    status, body = _get(gateway, "/api/ai-agronomist/ask?access_token=good")
    assert status == 401, f"only tile routes accept the query token: {status} {body}"


def test_agronomist_gets_verified_identity_under_v1(gateway: int) -> None:
    status, body = _get(
        gateway, "/api/ai-agronomist/ask", {"Authorization": "Bearer good", **_FORGED}
    )
    assert status == 200, f"verified agronomist request must pass: {status} {body}"
    assert body.startswith("sahool-ai-agronomist /v1/ask "), (
        f"/api/ai-agronomist must be rewritten to /v1 (deploy-2): {body}"
    )
    for expected in ("tenant=[tenant-verified]", "user=[user-verified]", "role=[farmer]"):
        assert expected in body, f"agronomist must get verified {expected}: {body}"
    status, body = _get(gateway, "/api/ai-agronomist/ask", dict(_FORGED))
    assert status == 401, f"agronomist without a bearer must be rejected: {status} {body}"


def test_agronomist_healthz_is_open_but_carries_no_identity(gateway: int) -> None:
    status, body = _get(gateway, "/api/ai-agronomist/healthz", dict(_FORGED))
    assert status == 200 and body.startswith("sahool-ai-agronomist /healthz "), (
        f"agronomist liveness must stay unauthenticated: {status} {body}"
    )
    assert "tenant=[]" in body and "role=[]" in body, f"no identity on healthz: {body}"


@pytest.mark.parametrize(
    ("path", "service", "upstream_path"),
    [
        ("/api/v1/fields", "sahool-platform", "/api/v1/fields"),
        ("/api/guardrails/v1/validate", "sahool-guardrails-engine", "/v1/validate"),
    ],
)
def test_self_verifying_services_never_see_a_client_identity_header(
    gateway: int, path: str, service: str, upstream_path: str
) -> None:
    status, body = _get(gateway, path, {"Authorization": "Bearer any", **_FORGED})
    assert status == 200 and body.startswith(f"{service} {upstream_path} "), (
        f"{path} must reach {service} at {upstream_path}: {status} {body}"
    )
    assert "tenant=[]" in body and "user=[]" in body and "role=[]" in body, (
        f"client-sent identity headers must be cleared before {service}: {body}"
    )


@pytest.mark.parametrize(
    "path", ["/internal/fields/f1/state", "/v1/fields/f1/timeseries", "/_auth_verify"]
)
def test_unrouted_and_internal_paths_are_not_forwarded(gateway: int, path: str) -> None:
    status, body = _get(gateway, path, {"Authorization": "Bearer good"})
    assert status == 404, f"{path} must not be forwarded anywhere: {status} {body}"


def test_gateway_starts_without_auth_and_fails_verified_routes_closed(
    gateway_without_auth: int,
) -> None:
    """Review MEDIUM: with auth not deployed, nginx must still start (no `helm --atomic`
    rollback of the whole release), verified routes must refuse, and the self-verifying
    platform surface must keep serving."""
    port = gateway_without_auth
    status, body = _get(port, "/gateway/healthz")
    assert status == 200, f"the gateway must start and be ready without auth: {status} {body}"
    for path in ("/api/raster/v1/fields/f1/timeseries", "/api/ai-agronomist/ask"):
        status, body = _get(port, path, {"Authorization": "Bearer good", **_FORGED})
        assert status == 500, f"{path}: an unreachable verifier must fail closed: {status} {body}"
        assert "sahool-" not in body, f"{path}: the service must not be reached: {body}"
    status, body = _get(port, "/auth/login")
    assert status == 502, f"/auth/ without the auth Service must answer 502: {status} {body}"
    status, body = _get(port, "/api/v1/fields", {"Authorization": "Bearer any", **_FORGED})
    assert status == 200 and body.startswith("sahool-platform /api/v1/fields "), (
        f"the self-verifying platform surface must keep serving: {status} {body}"
    )
    assert "tenant=[]" in body, f"no identity header without verification: {body}"


# ── 3. helm template with the production overlay ───────────────────────────────


def _helm_template(*extra: str) -> list[dict]:
    result = subprocess.run(
        [
            "helm",
            "template",
            "sahool",
            str(CHART),
            "-f",
            str(CHART / "values.yaml"),
            "-f",
            str(CHART / "values-production.yaml"),
            *extra,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert result.returncode == 0, f"helm template failed:\n{result.stderr}"
    return [doc for doc in yaml.safe_load_all(result.stdout) if doc]


def _deployment_env(docs: list[dict], name: str) -> set[str]:
    for doc in docs:
        if doc.get("kind") == "Deployment" and doc["metadata"]["name"] == name:
            return {e["name"] for e in doc["spec"]["template"]["spec"]["containers"][0]["env"]}
    raise AssertionError(f"no Deployment {name} rendered")


# Read before the binary lookup: the CI helm-render step sets HELM_RENDER_REQUIRED=1, so a
# missing helm fails these tests there instead of skipping them green.
HELM_RENDER_REQUIRED = os.environ.get("HELM_RENDER_REQUIRED") == "1"


def needs_helm(test):
    skip = pytest.mark.skipif(
        not HELM_RENDER_REQUIRED and shutil.which("helm") is None,
        reason="helm binary not installed",
    )
    return pytest.mark.helm_render(skip(test))


@needs_helm
def test_helm_production_render_has_every_mandatory_env_var() -> None:
    docs = _helm_template()
    for workload, required in VALIDATOR.PRODUCTION_REQUIRED_ENV.items():
        env = _deployment_env(docs, workload)
        missing = set(required) - env
        assert not missing, f"{workload}: rendered Deployment lacks {sorted(missing)}"
        assert "SAHOOL_ENV" in env, f"{workload}: SAHOOL_ENV must be rendered"


@needs_helm
def test_helm_render_without_platform_redis_url_fails_the_contract() -> None:
    docs = _helm_template("--set", "workloads.sahool-platform.secretEnv.REDIS_URL=null")
    env = _deployment_env(docs, "sahool-platform")
    missing = set(VALIDATOR.PRODUCTION_REQUIRED_ENV["sahool-platform"]) - env
    assert missing == {"REDIS_URL"}, (
        f"the production contract must flag exactly the removed REDIS_URL, got {missing}"
    )


@needs_helm
def test_helm_refuses_an_empty_trusted_ingress_namespace_list() -> None:
    result = subprocess.run(
        [
            "helm",
            "template",
            "sahool",
            str(CHART),
            "-f",
            str(CHART / "values.yaml"),
            "-f",
            str(CHART / "values-production.yaml"),
            "--set",
            "networkPolicy.trustedIngressNamespaces=null",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert result.returncode != 0 and "trustedIngressNamespaces" in result.stderr, (
        f"an empty ingress-controller list must fail the render:\n{result.stderr}"
    )


@needs_helm
def test_helm_render_routes_the_ingress_only_to_the_gateway() -> None:
    docs = _helm_template()
    ingresses = [d for d in docs if d.get("kind") == "Ingress"]
    assert len(ingresses) == 1, f"exactly one Ingress expected, got {len(ingresses)}"
    paths = ingresses[0]["spec"]["rules"][0]["http"]["paths"]
    backends = {p["backend"]["service"]["name"] for p in paths}
    assert backends == {"sahool-gateway"}, f"Ingress backends must be only the gateway: {backends}"
    config = next(
        d
        for d in docs
        if d.get("kind") == "ConfigMap" and d["metadata"]["name"] == "sahool-gateway"
    )
    for workload in _production_values()["workloads"]:
        if workload in _UNROUTED_WORKLOADS:
            continue
        assert f"upstream {_upstream_name(workload)} " in config["data"]["upstreams.conf"], (
            f"gateway upstreams.conf lacks {workload}"
        )


@needs_helm
def test_helm_render_network_policy_isolates_raster_and_agronomist() -> None:
    docs = _helm_template()
    policies = {d["metadata"]["name"]: d for d in docs if d.get("kind") == "NetworkPolicy"}
    for workload in VALIDATOR.GATEWAY_ONLY_WORKLOADS:
        policy = policies.get(f"{workload}-gateway-only")
        assert policy, f"no gateway-only NetworkPolicy for {workload}"
        sources = {
            peer["podSelector"]["matchLabels"]["app.kubernetes.io/component"]
            for rule in policy["spec"]["ingress"]
            for peer in rule["from"]
        }
        expected = {"sahool-gateway", *_EXPECTED_CALLERS[workload]}
        assert sources == expected, f"{workload} must admit only {expected}: {sources}"
        internal = policies["sahool-internal-allow"]["spec"]["podSelector"]["matchExpressions"][0]
        assert internal["operator"] == "NotIn" and workload in internal["values"], (
            f"the namespace-wide allow must exclude {workload}"
        )
    for name, policy in policies.items():
        has_ns = any(
            "namespaceSelector" in peer
            for rule in policy["spec"].get("ingress", [])
            for peer in rule.get("from", [])
        )
        assert not has_ns or name == "sahool-gateway-from-ingress-controller", (
            f"{name}: only the gateway may admit the ingress controller namespace"
        )

"""Helm NetworkPolicy: opt-in public egress and caller-only ingress (W3-09).

Before W3-09 the namespace default policy let every pod open TCP 443 to any address,
including the gateway, the migration Job and workloads that call no external provider.
Public HTTPS is now rendered by one policy, ``sahool-public-https-egress``, that selects
only the workloads declaring ``publicHttpsEgress: true``; the global
``networkPolicy.allowPublicHttpsEgress`` flag still withdraws it from all of them.

A workload with no auth of its own and no gateway route can be ``internalOnly``: it
admits only its ``internalCallers``. The structural checks run everywhere; the render
checks need the helm binary and are skipped without it.
"""

from __future__ import annotations

import ast
import copy
import importlib.util
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
CHART = ROOT / "helm" / "sahool"
TEMPLATE = CHART / "templates" / "networkpolicy.yaml"


def _validator():
    spec = importlib.util.spec_from_file_location(
        "validate_helm_readiness_np", ROOT / "scripts" / "deploy" / "validate_helm_readiness.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


VALIDATOR = _validator()

# Which workloads call an external provider over HTTPS, and which one. A workload joins
# this map with the code that makes the call; nothing else gets public egress.
_EXPECTED_PUBLIC_EGRESS = {
    "sahool-platform": "Open-Meteo / MET Norway (services/sahool-platform/api/connectors)",
    "sahool-raster-service": "Copernicus Data Space (CDSE_CLIENT_ID/SECRET)",
    "sahool-ai-agronomist": "hosted model providers when AI_PROVIDER is openrouter/anthropic",
    "sahool-weather-service": "Open-Meteo forecast/archive (services/weather-service/open_meteo.py)",
    "sahool-soil-service": "ISRIC SoilGrids (services/soil-service/soilgrids_client.py)",
    # Configurable, not literal: QDRANT_URL / OLLAMA_BASE_URL may name a managed external host.
    "sahool-rag-retrieval": "QDRANT_URL / OLLAMA_BASE_URL (services/rag-retrieval/main.py:53,55)",
}

# Every enabled workload WITHOUT public egress, with the env names its runtime import closure
# reads (main.py plus every service module and shared/ module it imports, transitively). A
# workload joins this map when it loses or is deployed without public egress; a new env name in
# its closure fails the test below, so an outbound setting is judged instead of being silently
# cut off by the default-deny policy.
_NO_PUBLIC_EGRESS_EVIDENCE: dict[str, frozenset[str]] = {
    "sahool-knowledge-graph": frozenset(
        {
            "KG_GRAPHQL_MAX_DEPTH",
            "KG_GRAPHQL_MAX_QUERY_BYTES",
            "KG_GRAPHQL_MAX_TOKENS",
            "KG_SQLITE_PATH",
            "SAHOOL_AGENT_TOKEN",
            "SEASON_EDGE_HMAC_KEY",
        }
    ),
    # DATABASE_URL is a database port, never 443; JWT_PUBLIC_KEY is a PEM value, not a JWKS URL.
    "sahool-guardrails-engine": frozenset(
        {
            "CORS_ORIGINS",
            "DATABASE_URL",
            "JWT_PUBLIC_KEY",
            "JWT_SECRET",
            "SAHOOL_AGENT_TOKEN",
            "SAHOOL_ALLOW_HS256_IN_PROD",
            "SAHOOL_ALLOW_RLS_BYPASS_ROLE",
            "SAHOOL_ENFORCE_RLS_ROLE",
            "SAHOOL_ENV",
        }
    ),
    # Databases, assertion Redis and the optional owner-proof client; see _GATED_OUTBOUND.
    # read_side_compare.py, production_promotion.py and staging_probe.py are operator
    # scripts that main.py does not import, so they remain outside the closure.
    "sahool-decision-service": frozenset(
        {
            "ACTIVATION_CACHE_TTL_SECONDS",
            "ACTIVATION_ENVIRONMENT_ID",
            "ACTIVATION_EVIDENCE_SIGNING_KEY",
            "ACTIVATION_PROBE_SIGNING_KEY",
            "DATABASE_URL",
            "DECISION_DB_POOL_MAX",
            # W4-05: an on/off switch for the WX-12 loop, read in persistence.py; not outbound.
            "DECISION_MODEL_LIFECYCLE_ENABLED",
            "DECISION_EXECUTION_REQUEST_MAX_AGE_S",
            "DECISION_REQUIRE_AGRONOMIC_CONTEXT",
            "DECISION_REQUIRE_AUTH_TOKEN",
            "DECISION_REQUIRE_SEPARATION_OF_DUTIES",
            "DECISION_REQUIRE_SOIL_EVIDENCE_GATE",
            "DECISION_REQUIRE_SOIL_PROFILE",
            "DECISION_SERVICE_ALLOW_SCHEMA_CHANGE",
            "DECISION_SERVICE_AUTH_TOKEN",
            "DECISION_SERVICE_SOR_ENABLED",
            "DECISION_STRICT_WORKER_TENANTS",
            "DECISION_WORKER_ASSERTION_KEY_ID",
            "DECISION_WORKER_ASSERTION_PREVIOUS_KEY",
            "DECISION_WORKER_ASSERTION_PREVIOUS_KEY_ID",
            "DECISION_WORKER_ASSERTION_REDIS_URL",
            "DEPLOY_BUILD_SHA",
            "ENVIRONMENT",
            "FIELD_INSPECTION_PROOF_TOKEN",
            "FIELD_MANAGEMENT_SERVICE_URL",
            "IRR_F01_RESERVATION_ENFORCE_ACTIVATION",
            "RUNTIME_WORK_LEASE_SECONDS",
            "SAHOOL_ENV",
        }
    ),
    "sahool-field-management": frozenset(
        {
            "DATABASE_URL",
            # Owner RPC/proof credentials and shared execution settings: no outbound host.
            "FIELD_INSPECTION_COORDINATOR_TOKEN",
            "FIELD_INSPECTION_DELIVERY_TOKEN_KEY",
            "FIELD_INSPECTION_EXECUTION_ADAPTER_ID",
            "FIELD_INSPECTION_EXECUTION_ENABLED",
            "FIELD_INSPECTION_PROOF_TOKEN",
            "FIELD_SERVICE_ALLOWED_CALLERS",
            "FIELD_SERVICE_ASSERTION_REDIS_URL",
            "FIELD_SERVICE_TENANT_ASSERTION_KEY",
            "FIELD_SERVICE_TENANT_ASSERTION_KEY_ID",
            "FIELD_SERVICE_TENANT_ASSERTION_PREVIOUS_KEY",
            "FIELD_SERVICE_TENANT_ASSERTION_PREVIOUS_KEY_ID",
            "FIELD_TASKS_SERVICE_TOKEN",
            "FM_SCOUTING_VERIFICATION_ENABLED",
            "SAHOOL_AGENT_TOKEN",
            "SAHOOL_ENV",
            "SERVICE_VERSION",
            # Inspection owner bridge sender (#1598); see _GATED_OUTBOUND.
            "VEGETATION_VERIFICATION_SERVICE_TOKEN",
            "VEGETATION_VERIFICATION_TENANT_ASSERTION_KEY",
            "VEGETATION_VERIFICATION_TENANT_ASSERTION_KEY_ID",
            "VEGETATION_VERIFICATION_URL",
        }
    ),
    # SMTP_* and SMS_* name external providers; see _GATED_OUTBOUND.
    "sahool-auth": frozenset(
        {
            "ADMIN_PASSWORD",
            "AUTH_COOKIE_SAMESITE",
            "AUTH_COOKIE_SECURE",
            "AUTH_TILE_COOKIE_NAME",
            "CORS_ORIGINS",
            "DATABASE_URL",
            "ENFORCE_ADMIN_STEPUP_MFA",
            "ENFORCE_SENSITIVE_MFA",
            "FRONTEND_URL",
            "JWT_EXPIRE_MINUTES",
            "JWT_PRIVATE_KEY",
            "JWT_PUBLIC_KEY",
            "JWT_SECRET",
            "LOG_LEVEL",
            "MFA_ALLOW_DERIVED_KEY",
            "MFA_AUDIT_HASH_KEY",
            "OTEL_EXPORTER_OTLP_ENDPOINT",
            "OTP_MAX_REQUESTS",
            "OTP_TTL_SECONDS",
            "REDIS_URL",
            "REFRESH_EXPIRE_DAYS",
            "REQUIRE_MFA_ROLES",
            "SAHOOL_ALLOW_HS256_IN_PROD",
            "SAHOOL_ALLOW_RLS_BYPASS_ROLE",
            "SAHOOL_ENFORCE_RLS_ROLE",
            "SAHOOL_ENV",
            "SMS_API_KEY",
            "SMS_FROM",
            "SMS_PROVIDER_URL",
            "SMTP_FROM",
            "SMTP_HOST",
            "SMTP_PASSWORD",
            "SMTP_PORT",
            "SMTP_USER",
            "UVICORN_ACCESS_LEVEL",
        }
    ),
}

# Modules whose import means the code can open a connection outside the cluster.
_OUTBOUND_MODULES = frozenset(
    {"aiohttp", "aiosmtplib", "boto3", "botocore", "grpc", "httpx", "requests", "smtplib"}
    | {"urllib.request", "websockets"}
)

# Outbound clients a workload without public egress may import, each with the settings that
# switch it on. The chart must render none of those settings, so the client stays off in a Helm
# install and the default-deny policy blocks nothing that runs. Turning one on needs the setting
# and an egress rule together (SMTP is port 587, outside publicHttpsEgress).
_GATED_OUTBOUND: dict[str, dict[str, frozenset[str]]] = {
    "sahool-decision-service": {
        # field_inspection_evidence.py reads the current proof from field-management.
        # read_owner_proof refuses an absent URL or token before constructing AsyncClient.
        # The URL is configurable, so do not assume it names an in-cluster host. The chart
        # renders neither setting: enabling this client requires a reviewed destination
        # and network policy together, without granting this workload public HTTPS.
        "httpx": frozenset({"FIELD_MANAGEMENT_SERVICE_URL", "FIELD_INSPECTION_PROOF_TOKEN"}),
    },
    "sahool-auth": {
        # Password-reset and verification email (services/auth/main.py send_reset_email).
        "aiosmtplib": frozenset({"SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD"}),
        # Phone OTP through an HTTP SMS provider (services/auth/main.py _send_otp_sms).
        "urllib.request": frozenset({"SMS_PROVIDER_URL", "SMS_API_KEY"}),
    },
    "sahool-field-management": {
        # Inspection owner bridge sender (fm_verification_client.py, #1598): POSTs a reviewed
        # inspection result to vegetation-analysis's internal receiver on the service network,
        # never a public host. Off unless FM_SCOUTING_VERIFICATION_ENABLED is on (1/true/yes/on) and the URL and
        # credentials are set. No egress rule is missing: sahool-default-deny already lets every
        # pod reach the cluster (templates/networkpolicy.yaml, `namespaceSelector: {}`), and the
        # chart does not deploy vegetation-analysis yet (values.yaml, W3-09 note), so a Helm
        # install has no receiver to reach. Deploying it there must admit field-management.
        "httpx": frozenset(
            {
                "FM_SCOUTING_VERIFICATION_ENABLED",
                "VEGETATION_VERIFICATION_SERVICE_TOKEN",
                "VEGETATION_VERIFICATION_TENANT_ASSERTION_KEY",
                "VEGETATION_VERIFICATION_TENANT_ASSERTION_KEY_ID",
                "VEGETATION_VERIFICATION_URL",
            }
        ),
    },
}

# Workloads that admit only named callers (no gateway), with those callers.
_EXPECTED_INTERNAL_ONLY: dict[str, list[str]] = {
    # No auth of its own; sahool-platform's weather_service_client is the in-chart caller.
    "sahool-weather-service": ["sahool-platform"],
    # Service token + X-Tenant-Id from the platform's service proxy; every workload holds
    # the token, so only the platform is admitted.
    "sahool-soil-service": ["sahool-platform"],
}


def _production_values() -> dict:
    base = VALIDATOR.load_yaml(CHART / "values.yaml")
    overlay = VALIDATOR.load_yaml(CHART / "values-production.yaml")
    return VALIDATOR.deep_merge(base, overlay)


def test_public_egress_is_exactly_the_declared_set() -> None:
    workloads = _production_values()["workloads"]
    declared = {n for n, s in workloads.items() if s.get("enabled") and s.get("publicHttpsEgress")}
    assert declared == set(_EXPECTED_PUBLIC_EGRESS), (
        "public HTTPS egress is granted per workload, with the provider it reaches; "
        f"declared {sorted(declared)}"
    )


def test_internal_only_workloads_admit_exactly_their_callers() -> None:
    workloads = _production_values()["workloads"]
    internal = {n: s.get("internalCallers") for n, s in workloads.items() if s.get("internalOnly")}
    assert internal == _EXPECTED_INTERNAL_ONLY


def test_the_validator_accepts_the_committed_values() -> None:
    assert VALIDATOR.network_policy_errors(_production_values()) == []


@pytest.mark.parametrize(
    ("change", "expected"),
    [
        ({"internalOnly": True, "gatewayOnly": False, "internalCallers": []}, "internalOnly needs"),
        ({"internalOnly": True, "gatewayOnly": True}, "not both"),
        ({"internalCallers": ["sahool-no-such-workload"]}, "not an enabled workload"),
        ({"publicHttpsEgress": "yes"}, "must be true or false"),
    ],
)
def test_the_validator_refuses_a_broken_policy_declaration(change: dict, expected: str) -> None:
    values = copy.deepcopy(_production_values())
    values["workloads"]["sahool-raster-service"].update(change)
    errors = VALIDATOR.network_policy_errors(values)
    assert any(expected in e for e in errors), errors


def test_internal_callers_without_a_restriction_are_refused() -> None:
    values = copy.deepcopy(_production_values())
    values["workloads"]["sahool-rag-retrieval"]["internalCallers"] = ["sahool-platform"]
    errors = VALIDATOR.network_policy_errors(values)
    assert any("has no effect" in e for e in errors), errors


def test_the_default_policy_carries_no_public_egress() -> None:
    text = TEMPLATE.read_text(encoding="utf-8")
    default, rest = text.split("name: sahool-public-https-egress", 1)
    assert "0.0.0.0/0" not in default, (
        "a public ipBlock in the namespace default policy reopens 443 for every pod, "
        "the gateway and the migration Job included"
    )
    assert "if and .Values.networkPolicy.allowPublicHttpsEgress $publicHttps" in text, (
        "the global flag must still withdraw public egress from every workload"
    )
    assert "$workload.publicHttpsEgress" in text and "operator: In" in rest


def test_the_template_refuses_an_internal_only_workload_without_callers() -> None:
    text = TEMPLATE.read_text(encoding="utf-8")
    assert "internalOnly needs internalCallers" in text and "fail (printf" in text


# Read before the binary lookup: the CI helm-render step sets HELM_RENDER_REQUIRED=1, so a
# missing helm fails these tests there instead of skipping them green.
HELM_RENDER_REQUIRED = os.environ.get("HELM_RENDER_REQUIRED") == "1"


def needs_helm(test):
    skip = pytest.mark.skipif(
        not HELM_RENDER_REQUIRED and shutil.which("helm") is None,
        reason="helm binary not installed",
    )
    return pytest.mark.helm_render(skip(test))


def _render(*extra: str) -> list[dict]:
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
    assert result.returncode == 0, result.stderr
    return [d for d in yaml.safe_load_all(result.stdout) if d]


@needs_helm
def test_helm_render_grants_public_egress_only_to_declared_workloads() -> None:
    policies = {d["metadata"]["name"]: d for d in _render() if d.get("kind") == "NetworkPolicy"}
    default = policies["sahool-default-deny"]["spec"]
    assert all("ipBlock" not in peer for rule in default["egress"] for peer in rule["to"])
    public = policies["sahool-public-https-egress"]["spec"]
    selected = set(public["podSelector"]["matchExpressions"][0]["values"])
    assert selected == set(_EXPECTED_PUBLIC_EGRESS)
    assert public["egress"][0]["ports"] == [{"protocol": "TCP", "port": 443}]


@needs_helm
def test_helm_render_without_public_egress_renders_no_public_policy() -> None:
    docs = _render("--set", "networkPolicy.allowPublicHttpsEgress=false")
    names = {d["metadata"]["name"] for d in docs if d.get("kind") == "NetworkPolicy"}
    assert "sahool-public-https-egress" not in names


@needs_helm
def test_helm_render_internal_only_workloads_admit_only_their_callers() -> None:
    policies = {d["metadata"]["name"]: d for d in _render() if d.get("kind") == "NetworkPolicy"}
    excluded = policies["sahool-internal-allow"]["spec"]["podSelector"]["matchExpressions"][0]
    for name, callers in _EXPECTED_INTERNAL_ONLY.items():
        policy = policies[f"{name}-internal-only"]["spec"]
        sources = {
            peer["podSelector"]["matchLabels"]["app.kubernetes.io/component"]
            for rule in policy["ingress"]
            for peer in rule["from"]
        }
        assert sources == set(callers), f"{name} must admit only {callers}: {sources}"
        assert name in excluded["values"], f"the namespace-wide allow must exclude {name}"


_ENV_READ = re.compile(r"""(?:getenv|environ\.get|environ\[)\(?\s*["']([A-Z][A-Z0-9_]+)["']""")


def _module_file(base: Path, parts: list[str]) -> Path | None:
    target = base.joinpath(*parts)
    for candidate in (target.with_suffix(".py"), target / "__init__.py"):
        if candidate.is_file():
            return candidate
    return None


def _runtime_closure(service_dir: Path) -> tuple[set[Path], set[str]]:
    """The files main.py reaches through service and shared/ imports, and every module imported.

    Absolute imports resolve against the service directory (the image's /app) and ``shared``
    against the repository root (the image copies shared/ to /app/shared); relative imports
    resolve against the importing file. Imports inside functions count: they run too.
    """
    seen: set[Path] = set()
    modules: set[str] = set()
    todo = [service_dir / "main.py"]
    while todo:
        path = todo.pop()
        if path in seen:
            continue
        seen.add(path)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names = [node.module] + [f"{node.module}.{a.name}" for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                base = path.parent
                for _ in range(node.level - 1):
                    base = base.parent
                prefix = node.module.split(".") if node.module else []
                for alias in node.names:
                    for parts in (prefix + [alias.name], prefix):
                        found = _module_file(base, parts) if parts else None
                        if found:
                            todo.append(found)
                continue
            for name in names:
                modules.add(name)
                parts = name.split(".")
                found = _module_file(ROOT if parts[0] == "shared" else service_dir, parts)
                if found:
                    todo.append(found)
    return seen, modules


def _service_dir(workload: str) -> Path:
    dockerfile = _production_values()["workloads"][workload].get("sourceDockerfile")
    assert dockerfile, f"{workload} declares no sourceDockerfile, so its source cannot be read"
    return (ROOT / dockerfile).parent


def test_every_workload_without_public_egress_has_source_evidence() -> None:
    workloads = _production_values()["workloads"]
    unflagged = {
        n for n, s in workloads.items() if s.get("enabled") and not s.get("publicHttpsEgress")
    }
    assert unflagged == set(_NO_PUBLIC_EGRESS_EVIDENCE), (
        "every enabled workload without public egress needs its env closure frozen in "
        f"_NO_PUBLIC_EGRESS_EVIDENCE: missing {sorted(unflagged - set(_NO_PUBLIC_EGRESS_EVIDENCE))}, "
        f"stale {sorted(set(_NO_PUBLIC_EGRESS_EVIDENCE) - unflagged)}"
    )
    assert not set(_GATED_OUTBOUND) - unflagged


@pytest.mark.parametrize("workload", sorted(_NO_PUBLIC_EGRESS_EVIDENCE))
def test_a_workload_without_public_egress_reads_no_new_outbound_setting(workload) -> None:
    """A new env var or outbound client in the closure must be re-judged, not silently cut off."""
    files, modules = _runtime_closure(_service_dir(workload))
    found: set[str] = set()
    for path in files:
        found |= set(_ENV_READ.findall(path.read_text(encoding="utf-8")))
    expected = _NO_PUBLIC_EGRESS_EVIDENCE[workload]
    assert found == expected, (workload, sorted(found ^ expected))
    outbound = {
        m for m in modules if m in _OUTBOUND_MODULES or m.split(".")[0] in _OUTBOUND_MODULES
    }
    outbound = {m if m in _OUTBOUND_MODULES else m.split(".")[0] for m in outbound}
    assert outbound == set(_GATED_OUTBOUND.get(workload, {})), (workload, sorted(outbound))
    assert workload not in _EXPECTED_PUBLIC_EGRESS


@pytest.mark.parametrize("workload", sorted(_GATED_OUTBOUND))
def test_gated_outbound_settings_are_not_rendered_by_the_chart(workload) -> None:
    spec = _production_values()["workloads"][workload]
    rendered = set(spec.get("env") or {}) | set(spec.get("secretEnv") or {})
    for module, settings in _GATED_OUTBOUND[workload].items():
        assert settings <= _NO_PUBLIC_EGRESS_EVIDENCE[workload], (workload, module)
        assert not settings & rendered, (
            f"{workload} renders {sorted(settings & rendered)}, which switches on {module}; "
            "add the egress rule it needs and move it out of _GATED_OUTBOUND"
        )


def test_the_closure_finds_an_outbound_client_planted_in_an_imported_module(tmp_path) -> None:
    """Negative control: a client two imports deep, inside a function, is still found."""
    (tmp_path / "main.py").write_text("from helpers import send\n", encoding="utf-8")
    (tmp_path / "helpers.py").write_text(
        "import os\n\ndef send():\n    import httpx\n    return os.getenv('HOOK_URL')\n",
        encoding="utf-8",
    )
    files, modules = _runtime_closure(tmp_path)
    assert "httpx" in modules
    assert {"HOOK_URL"} == set().union(
        *(_ENV_READ.findall(p.read_text(encoding="utf-8")) for p in files)
    )

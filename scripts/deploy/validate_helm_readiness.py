#!/usr/bin/env python3
"""Static deployment readiness gate for the SAHOOL Helm chart.

This is intentionally dependency-light and does not render Helm templates. It validates
values and template contracts that are easy to break during release packaging.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

try:
    import yaml
except Exception as exc:  # pragma: no cover
    print(f"PyYAML is required for deployment validation: {exc}", file=sys.stderr)
    sys.exit(2)

ROOT = Path(__file__).resolve().parents[2]
CHART = ROOT / "helm" / "sahool"

REQUIRED_TEMPLATES = [
    "Chart.yaml",
    "values.yaml",
    "values-production.yaml",
    "templates/deployments.yaml",
    "templates/services.yaml",
    "templates/persistence.yaml",
    "templates/ingress.yaml",
    "templates/networkpolicy.yaml",
    "templates/migration-job.yaml",
    "templates/gateway.yaml",
]

FORBIDDEN_IMAGE_TAGS = {"latest", "dev", "main", "master"}
FORBIDDEN_SECRET_LITERALS = [
    "password123",
    "changeme",
    "default-secret",
    "postgres://postgres",
    "sslmode=disable",
    "BYPASSRLS",
]


# Environment variables each workload refuses to boot (or to serve) without when
# SAHOOL_ENV=production, with the code that enforces it. W0-04 / deploy-1: the chart
# rendered no REDIS_URL for the platform and no JWT_PUBLIC_KEY for guardrails and raster,
# so a production install could not start. Every name must be rendered by the chart, as a
# plain value or (for secrets) a secretKeyRef to a declared global.secretRefs entry.
PRODUCTION_REQUIRED_ENV: dict[str, dict[str, str]] = {
    "sahool-platform": {
        "DATABASE_URL": "services/sahool-platform/api/main.py (runtime DB, RLS role)",
        "JWT_PUBLIC_KEY": "services/sahool-platform/api/main.py:134 _refuse_hs256_in_production",
        "REDIS_URL": "services/sahool-platform/api/main.py:1096 _build_denylist (fail-closed)",
        # W3-09: without it every decision-service call answers 503 in production.
        "DECISION_SERVICE_TOKEN": "shared/security/decision_service_auth.py:23 required in production",
    },
    "sahool-raster-service": {
        "DATABASE_URL": "services/raster-service/raster_security_context.py:156 ownership",
        "JWT_PUBLIC_KEY": "shared/security/access_tokens.py:89 access_token_verification_key",
    },
    "sahool-guardrails-engine": {
        "JWT_PUBLIC_KEY": "services/guardrails-engine/main.py:421 RS256 required in production",
    },
    "sahool-ai-agronomist": {
        "SAHOOL_AGENT_REDIS_URL": "services/ai_agronomist/agent_stores.py:296 (fail-closed)",
    },
    # W3-09: compose leaves the RS256 pair optional (${JWT_PRIVATE_KEY:-}); production
    # refuses HS256 and refuses to boot without Redis.
    "sahool-auth": {
        "DATABASE_URL": "services/auth/main.py:141 (asyncpg pool, RLS-safe role)",
        "REDIS_URL": "services/auth/main.py:392 Redis required in production (fail-closed)",
        "JWT_PRIVATE_KEY": "services/auth/main.py:337 RS256 required in production",
        "JWT_PUBLIC_KEY": "services/auth/main.py:325 JWT_PRIVATE_KEY needs JWT_PUBLIC_KEY",
    },
    "sahool-decision-service": {
        "DECISION_SERVICE_AUTH_TOKEN": "services/decision-service/main.py:524 refuses to start",
    },
}

# Workloads that derive the tenant from X-Tenant-Id: NetworkPolicy admits only the gateway
# (which injects the verified tenant) and the in-namespace callers they list.
GATEWAY_ONLY_WORKLOADS = ("sahool-raster-service", "sahool-ai-agronomist")


def production_env_errors(values: dict) -> list[str]:
    """Every production-mandatory variable must be rendered for its enabled workload."""
    errors = []
    secret_refs = values.get("global", {}).get("secretRefs", {}) or {}
    workloads = values.get("workloads", {}) or {}
    for name, required in PRODUCTION_REQUIRED_ENV.items():
        spec = workloads.get(name)
        if not spec or not spec.get("enabled"):
            continue
        env = spec.get("env", {}) or {}
        secret_env = spec.get("secretEnv", {}) or {}
        for var, source in required.items():
            if var in secret_env:
                ref = secret_env[var]
                if not secret_refs.get(ref):
                    errors.append(
                        f"{name}: secretEnv {var} -> {ref!r} has no global.secretRefs entry"
                    )
            elif not str(env.get(var, "")).strip():
                errors.append(f"{name}: {var} is required in production ({source})")
    for name, spec in workloads.items():
        for var, ref in (spec.get("secretEnv", {}) or {}).items():
            if not secret_refs.get(ref):
                errors.append(f"{name}: secretEnv {var} -> {ref!r} is not in global.secretRefs")
    return errors


def gateway_errors(values: dict, chart: Path = CHART) -> list[str]:
    """W0-06: the Ingress reaches only the gateway; raster/ai-agronomist only from it."""
    errors = []
    gateway = values.get("gateway", {}) or {}
    if values.get("ingress", {}).get("enabled") and not gateway.get("enabled"):
        errors.append("gateway.enabled must be true while ingress.enabled is true")
    if gateway.get("enabled"):
        if image_tag(str(gateway.get("image", ""))) in FORBIDDEN_IMAGE_TAGS:
            errors.append(f"gateway uses unsafe image tag: {gateway.get('image')}")
        if not (gateway.get("auth", {}) or {}).get("serviceName"):
            errors.append("gateway.auth.serviceName is required (auth_request verifier)")
        if not str(gateway.get("resolver", "")).strip():
            errors.append("gateway.resolver is required (auth is resolved per request)")
        if not (values.get("networkPolicy", {}) or {}).get("trustedIngressNamespaces"):
            errors.append(
                "networkPolicy.trustedIngressNamespaces must not be empty: an empty `from` "
                "admits every source in the cluster to the gateway"
            )
        for rel in ("nginx.conf", "routes.conf", "proxy_params.conf"):
            if not (chart / "files" / "gateway" / rel).is_file():
                errors.append(f"gateway: missing files/gateway/{rel}")
    workloads = values.get("workloads", {}) or {}
    auth = gateway.get("auth", {}) or {}
    auth_spec = workloads.get(auth.get("serviceName", "")) or {}
    if (
        gateway.get("enabled")
        and auth_spec.get("enabled")
        and auth_spec.get("port") != auth.get("port")
    ):
        errors.append(
            f"gateway.auth.port {auth.get('port')} does not match the "
            f"{auth.get('serviceName')} workload port {auth_spec.get('port')}"
        )
    for name in GATEWAY_ONLY_WORKLOADS:
        spec = workloads.get(name) or {}
        if spec.get("enabled") and spec.get("gatewayOnly") is not True:
            errors.append(f"{name} must set gatewayOnly: true (it trusts X-Tenant-Id)")
    ingress_text = (chart / "templates" / "ingress.yaml").read_text(encoding="utf-8")
    if ".Values.workloads" in ingress_text:
        errors.append("templates/ingress.yaml must not route to workloads directly")
    return errors


def network_policy_errors(values: dict) -> list[str]:
    """W3-09: restricted ingress names real callers; public HTTPS egress is opt-in.

    ``gatewayOnly`` admits the gateway plus ``internalCallers``; ``internalOnly`` admits
    only ``internalCallers`` (a workload with no auth of its own and no gateway route).
    A caller that is not an enabled workload admits nobody and hides a broken call path;
    an ``internalOnly`` workload with no caller would render an empty ``from``.
    """
    errors = []
    workloads = values.get("workloads", {}) or {}
    enabled = {name for name, spec in workloads.items() if (spec or {}).get("enabled")}
    for name, spec in workloads.items():
        spec = spec or {}
        if not spec.get("enabled"):
            continue
        callers = spec.get("internalCallers") or []
        if spec.get("gatewayOnly") and spec.get("internalOnly"):
            errors.append(f"{name}: set gatewayOnly or internalOnly, not both")
        if spec.get("internalOnly") and not callers:
            errors.append(f"{name}: internalOnly needs at least one internalCallers entry")
        if callers and not (spec.get("gatewayOnly") or spec.get("internalOnly")):
            errors.append(f"{name}: internalCallers has no effect without gatewayOnly/internalOnly")
        for caller in callers:
            if caller not in enabled:
                errors.append(f"{name}: internalCallers names {caller!r}, not an enabled workload")
        if "publicHttpsEgress" in spec and not isinstance(spec["publicHttpsEgress"], bool):
            errors.append(f"{name}: publicHttpsEgress must be true or false")
    template = (CHART / "templates" / "networkpolicy.yaml").read_text(encoding="utf-8")
    if "cidr: 0.0.0.0/0" in template.split("name: sahool-public-https-egress", 1)[0]:
        errors.append(
            "templates/networkpolicy.yaml: public egress must be rendered only by "
            "sahool-public-https-egress, for workloads that set publicHttpsEgress"
        )
    return errors


def gateway_auth_notice(values: dict) -> str | None:
    """The deploy-path statement when the chart does not deploy the auth verifier.

    W3-09 deploys it as the ``sahool-auth`` workload; the notice remains for values that
    rename the Service away from it or disable it.
    """
    gateway = values.get("gateway", {}) or {}
    if not gateway.get("enabled"):
        return None
    service = (gateway.get("auth", {}) or {}).get("serviceName", "")
    spec = (values.get("workloads", {}) or {}).get(service) or {}
    if spec.get("enabled"):
        return None
    return (
        f"the chart does not deploy the auth Service {service!r} (deploy-3, W3-09). "
        "The gateway starts without it and resolves it per request; until it exists in "
        "the namespace every auth_request route answers 500 and /auth/ answers 502 "
        "(fail closed), and only /api/v1 and /api/guardrails serve."
    )


def dockerfile_ports(text: str) -> set[int]:
    """Ports the image declares (``EXPOSE``) or binds (``CMD``/``ENTRYPOINT`` ``--port N``).

    A Dockerfile whose uvicorn binds a port without ``EXPOSE`` still serves on it, and adding
    ``EXPOSE`` only to satisfy this check would rebuild that service wherever its Dockerfile is
    watched (W3-09: field-management on Railway). The bound port is read from the command the
    image actually runs, not taken from the chart values it is checked against.
    """
    ports = {int(port) for port in re.findall(r"^EXPOSE\s+(\d+)", text, re.M)}
    for line in re.findall(r"^(?:CMD|ENTRYPOINT)\s+(.+)$", text, re.M):
        ports.update(int(port) for port in re.findall(r'--port["\s,=]+"?(\d+)', line))
    return ports


def source_contract_errors(values: dict, root: Path = ROOT) -> list[str]:
    """Compare chart ports with the Dockerfile actually named by each workload."""
    errors = []
    for name, spec in values.get("workloads", {}).items():
        if not spec.get("enabled"):
            continue
        source = root / spec.get("sourceDockerfile", "")
        if not source.is_file():
            errors.append(f"{name}: sourceDockerfile is required")
            continue
        ports = dockerfile_ports(source.read_text(encoding="utf-8"))
        if spec.get("port") not in ports:
            errors.append(
                f"{name}: port {spec.get('port')} does not match {source.relative_to(root)} EXPOSE {sorted(ports)}"
            )
        if name == "sahool-knowledge-graph" and (
            spec.get("replicas") != 1 or not spec.get("persistence")
        ):
            errors.append("knowledge-graph SQLite requires one replica and persistent storage")
    return errors


def migration_job_errors(values: dict, root: Path = ROOT) -> list[str]:
    """The migration Job must run what its image actually contains (I1, audit 2026-11-01).

    It ran ``scripts_v9/migrate.py`` in the platform image, which ships neither that
    script nor ``psql``, so every ``helm install`` failed in the pre-install hook.
    Every absolute path in ``command`` must come from the image named by
    ``sourceDockerfile`` (``/migrations/`` is ``COPY migrations/``) or from the chart's
    ``files/`` ConfigMap mount; and the chart must never bake the apply permission.
    """
    job = values.get("jobs", {}).get("migration", {})
    if not job.get("enabled"):
        return []
    errors = []
    source = root / str(job.get("sourceDockerfile", ""))
    if not job.get("sourceDockerfile") or not source.is_file():
        return ["jobs.migration: sourceDockerfile is required"]
    dockerfile = source.read_text(encoding="utf-8")
    copies_migrations = re.search(r"^COPY\s+migrations/\s+/migrations/\s*$", dockerfile, re.M)
    command = [str(arg) for arg in job.get("command", [])]
    if not command:
        errors.append("jobs.migration: command is required")
    elif not re.search(rf"\b{re.escape(command[0])}\b", dockerfile):
        errors.append(
            f"jobs.migration: interpreter {command[0]!r} is not installed by {source.name}"
        )
    for arg in command[1:]:
        if arg.startswith("/migrations/"):
            if not copies_migrations or not (root / arg.lstrip("/")).is_file():
                errors.append(f"jobs.migration: {arg} is not in the image built from {source.name}")
        elif arg.startswith("/opt/sahool-migrate/"):
            if not (CHART / "files" / arg.rsplit("/", 1)[-1]).is_file():
                errors.append(f"jobs.migration: {arg} has no source under helm/sahool/files/")
        elif "/" in arg or arg.endswith((".py", ".sh", ".sql")):
            errors.append(f"jobs.migration: {arg} is not provided by the image or the chart")
    if image_tag(str(job.get("image", ""))) in FORBIDDEN_IMAGE_TAGS:
        errors.append(f"jobs.migration uses unsafe image tag: {job.get('image')}")
    if job.get("apply") is not False:
        errors.append(
            "jobs.migration.apply must be false in chart values; "
            "grant SAHOOL_MIGRATE_APPLY with --set only at the migration decision"
        )
    return errors


def load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def deep_merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def image_tag(image: str) -> str:
    tail = image.rsplit("/", 1)[-1]
    if ":" not in tail:
        return "latest"
    return tail.rsplit(":", 1)[-1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env", choices=["staging", "production"], default="production")
    args = parser.parse_args()

    failures: list[str] = []
    for rel in REQUIRED_TEMPLATES:
        if not (CHART / rel).exists():
            failures.append(f"missing chart asset: {rel}")

    if failures:
        for item in failures:
            print(f"FAIL: {item}")
        return 1

    values = load_yaml(CHART / "values.yaml")
    overlay = load_yaml(CHART / f"values-{args.env}.yaml")
    merged = deep_merge(values, overlay)
    failures.extend(source_contract_errors(merged))
    failures.extend(migration_job_errors(merged))
    failures.extend(gateway_errors(merged))
    failures.extend(network_policy_errors(merged))
    if args.env == "production":
        failures.extend(production_env_errors(merged))
        if int((merged.get("gateway", {}) or {}).get("replicas", 0)) < 2:
            failures.append("gateway production replicas must be >=2")

    if args.env == "production" and merged.get("global", {}).get("environment") != "production":
        failures.append("production overlay must set global.environment=production")

    if not merged.get("networkPolicy", {}).get("enabled"):
        failures.append("networkPolicy.enabled must be true")

    if not merged.get("ingress", {}).get("tlsSecretName"):
        failures.append("ingress.tlsSecretName is required")

    if merged.get("global", {}).get("runtimeDatabaseRole") != "sahool_app":
        failures.append("runtimeDatabaseRole must be sahool_app")
    if merged.get("global", {}).get("jobsDatabaseRole") != "sahool_jobs":
        failures.append("jobsDatabaseRole must be sahool_jobs")

    workloads = merged.get("workloads", {})
    if not workloads:
        failures.append("no workloads declared")

    for name, spec in workloads.items():
        if not spec.get("enabled", True):
            continue
        image = str(spec.get("image", ""))
        tag = image_tag(image)
        if tag in FORBIDDEN_IMAGE_TAGS:
            failures.append(f"{name} uses unsafe image tag: {image}")
        if (
            args.env == "production"
            and name != "sahool-knowledge-graph"
            and int(spec.get("replicas", 0)) < 2
        ):
            failures.append(f"{name} production replicas must be >=2")
        secret_env = spec.get("secretEnv", {})
        if (
            name in {"sahool-platform", "sahool-raster-service"}
            and "DATABASE_URL" not in secret_env
        ):
            failures.append(f"{name} must source DATABASE_URL from a secret reference")
        for key, value in spec.get("env", {}).items():
            text = f"{key}={value}"
            if any(bad.lower() in text.lower() for bad in FORBIDDEN_SECRET_LITERALS):
                failures.append(f"{name} contains forbidden literal env: {key}")

    template_text = "\n".join(
        (CHART / "templates" / name).read_text(encoding="utf-8")
        for name in ["deployments.yaml", "migration-job.yaml", "networkpolicy.yaml"]
    )
    required_snippets = [
        "readinessProbe",
        "livenessProbe",
        "runAsNonRoot: true",
        "allowPrivilegeEscalation: false",
        "readOnlyRootFilesystem: true",
        'drop: ["ALL"]',
        "helm.sh/hook: pre-install,pre-upgrade",
        "NetworkPolicy",
    ]
    for snippet in required_snippets:
        if snippet not in template_text:
            failures.append(f"template contract missing: {snippet}")

    notice = gateway_auth_notice(merged)
    if notice:
        print(f"WARN: {notice}")

    if failures:
        for item in failures:
            print(f"FAIL: {item}")
        return 1

    print(
        f"Helm deployment readiness validation passed for {args.env}: {len(workloads)} workloads checked"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

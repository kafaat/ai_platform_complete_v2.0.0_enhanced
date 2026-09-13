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
        ports = {
            int(port)
            for port in re.findall(r"^EXPOSE\s+(\d+)", source.read_text(encoding="utf-8"), re.M)
        }
        if spec.get("port") not in ports:
            errors.append(
                f"{name}: port {spec.get('port')} does not match {source.relative_to(root)} EXPOSE {sorted(ports)}"
            )
        if name == "sahool-knowledge-graph" and (
            spec.get("replicas") != 1 or not spec.get("persistence")
        ):
            errors.append("knowledge-graph SQLite requires one replica and persistent storage")
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

#!/usr/bin/env python3
"""Validate SAHOOL production observability assets without requiring Docker."""
from __future__ import annotations

import json
import sys
from pathlib import Path

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None

ROOT = Path(__file__).resolve().parents[2]

REQUIRED_DASHBOARDS = [
    ROOT / "grafana/dashboards/json/sahool-production-overview.json",
    ROOT / "grafana/dashboards/json/sahool-field-imagery-ai-runtime.json",
]
REQUIRED_ALERTS = [
    "SahoolRasterTileJSONUnavailable",
    "SahoolAIAdviceStackDegraded",
    "SahoolOutboxBacklogGrowing",
    "SahoolOutboxPublishFailures",
    "SahoolPluginSandboxViolation",
    "SahoolPhysicalActuationBlocked",
    "SahoolMobileSyncConflictSpike",
    "SahoolModelPromotionFailure",
]
REQUIRED_JOBS = [
    "sahool-platform",
    "raster-service",
    "ai-agronomist",
    "rag-retrieval",
    "knowledge-graph",
    "guardrails-engine",
]


def fail(message: str) -> None:
    print(f"[observability-gate] FAIL: {message}", file=sys.stderr)
    raise SystemExit(1)


def load_yaml(path: Path):
    if yaml is None:
        text = path.read_text(encoding="utf-8")
        return text
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def validate_dashboards() -> None:
    provider = ROOT / "grafana/dashboards/dashboards.yml"
    if not provider.exists():
        fail("missing Grafana dashboards provider")
    provider_text = provider.read_text(encoding="utf-8")
    if "/etc/grafana/provisioning/dashboards/json" not in provider_text:
        fail("Grafana provider does not point to dashboard JSON directory")

    for path in REQUIRED_DASHBOARDS:
        if not path.exists():
            fail(f"missing dashboard {path.relative_to(ROOT)}")
        data = json.loads(path.read_text(encoding="utf-8"))
        if not data.get("uid") or not data.get("title"):
            fail(f"dashboard lacks uid/title: {path.name}")
        panels = data.get("panels", [])
        if len(panels) < 4:
            fail(f"dashboard has too few panels: {path.name}")
        exprs = "\n".join(
            t.get("expr", "")
            for p in panels
            for t in p.get("targets", [])
            if isinstance(t, dict)
        )
        if "up" not in exprs:
            fail(f"dashboard lacks availability query: {path.name}")


def validate_prometheus() -> None:
    prom = ROOT / "prometheus/prometheus.yml"
    alerts = ROOT / "prometheus/alerts.yml"
    if not prom.exists() or not alerts.exists():
        fail("missing prometheus.yml or alerts.yml")
    prom_text = prom.read_text(encoding="utf-8")
    alerts_text = alerts.read_text(encoding="utf-8")
    if "alerts.yml" not in prom_text:
        fail("Prometheus does not load alerts.yml")
    for alert in REQUIRED_ALERTS:
        if f"alert: {alert}" not in alerts_text:
            fail(f"missing alert rule {alert}")
    if "sahool-production-slos" not in alerts_text:
        fail("missing sahool-production-slos alert group")


def validate_compose_mounts() -> None:
    compose = ROOT / "docker-compose.v9.yml"
    text = compose.read_text(encoding="utf-8")
    for required in [
        "./prometheus/prometheus.yml:/etc/prometheus/prometheus.yml:ro",
        "./prometheus/alerts.yml:/etc/prometheus/alerts.yml:ro",
        "./grafana/dashboards:/etc/grafana/provisioning/dashboards:ro",
        "./grafana/datasources:/etc/grafana/provisioning/datasources:ro",
    ]:
        if required not in text:
            fail(f"compose missing observability mount: {required}")
    for service in ["sahool-prometheus", "sahool-alertmanager", "sahool-grafana"]:
        if service not in text:
            fail(f"compose missing service {service}")


def validate_scrape_jobs() -> None:
    prom_text = (ROOT / "prometheus/prometheus.yml").read_text(encoding="utf-8")
    # These may be direct jobs or route-level metrics through platform/nginx; enforce key names in assets.
    assets = prom_text + "\n" + (ROOT / "grafana/dashboards/json/sahool-field-imagery-ai-runtime.json").read_text(encoding="utf-8")
    for job in REQUIRED_JOBS:
        if job not in assets:
            fail(f"observability assets do not mention critical job/domain {job}")


def main() -> None:
    validate_dashboards()
    validate_prometheus()
    validate_compose_mounts()
    validate_scrape_jobs()
    print("[observability-gate] passed")


if __name__ == "__main__":
    main()

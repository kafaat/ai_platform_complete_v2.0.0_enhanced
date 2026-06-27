from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_observability_validation_gate_passes() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/observability/validate_observability_assets.py"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "passed" in result.stdout


def test_grafana_dashboards_are_valid_json_and_have_panels() -> None:
    dashboards = sorted((ROOT / "grafana/dashboards/json").glob("sahool-*.json"))
    assert len(dashboards) >= 2
    for dashboard in dashboards:
        data = json.loads(dashboard.read_text())
        assert data["uid"]
        assert data["title"].startswith("SAHOOL")
        assert len(data.get("panels", [])) >= 4


def test_prometheus_has_sahool_production_alerts() -> None:
    alerts = (ROOT / "prometheus/alerts.yml").read_text()
    for alert in [
        "SahoolRasterTileJSONUnavailable",
        "SahoolAIAdviceStackDegraded",
        "SahoolOutboxPublishFailures",
        "SahoolPluginSandboxViolation",
        "SahoolPhysicalActuationBlocked",
        "SahoolMobileSyncConflictSpike",
        "SahoolModelPromotionFailure",
    ]:
        assert f"alert: {alert}" in alerts


def test_compose_mounts_grafana_and_prometheus_assets() -> None:
    compose = (ROOT / "docker-compose.v9.yml").read_text()
    assert "./grafana/dashboards:/etc/grafana/provisioning/dashboards:ro" in compose
    assert "./grafana/datasources:/etc/grafana/provisioning/datasources:ro" in compose
    assert "./prometheus/alerts.yml:/etc/prometheus/alerts.yml:ro" in compose

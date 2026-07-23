from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]


def _manifest_row(name: str) -> dict:
    manifest = json.loads(
        (ROOT / "config" / "service_feature_ui_contracts.json").read_text(encoding="utf-8")
    )
    return next(row for row in manifest["services"] if row["service"] == name)


def test_remote_sensing_workspace_has_real_ui_and_gateway_consumer() -> None:
    api = (ROOT / "frontend/src/services/api/remoteSensingWorkspace.ts").read_text(encoding="utf-8")
    panel = (ROOT / "frontend/src/sections/FieldWorkspaceImageryPanel.tsx").read_text(
        encoding="utf-8"
    )
    shell = (ROOT / "frontend/src/sections/FieldWorkspaceRouteShell.tsx").read_text(
        encoding="utf-8"
    )
    nginx = (ROOT / "nginx/nginx.v9.conf").read_text(encoding="utf-8")
    frontend_nginx = (ROOT / "frontend/nginx.conf").read_text(encoding="utf-8")

    route = "/api/remote-sensing-workspace/"
    assert route in api
    assert "getRemoteSensingWorkspaceOverview" in panel
    assert "seasonId={seasonId}" in shell
    assert f"location {route}" in nginx
    assert (
        "auth_request /_auth_verify"
        in nginx.split(f"location {route}", 1)[1].split("location ", 1)[0]
    )
    assert "remote_sensing_workspace_backend" in nginx
    assert route in frontend_nginx

    compose = yaml.safe_load((ROOT / "docker-compose.v9.yml").read_text(encoding="utf-8"))
    assert (
        compose["services"]["sahool-nginx"]["depends_on"]["sahool-remote-sensing-workspace-bff"][
            "condition"
        ]
        == "service_healthy"
    )
    assert _manifest_row("remote-sensing-workspace-bff")["classification"] == "ui-bff"


def test_gis_workflow_is_truthfully_a_batch_job_not_live_http_service() -> None:
    row = _manifest_row("gis-workflow-service")
    assert row["classification"] == "batch-job-tool"
    assert row["evidence"][0]["kind"] == "job-contract"

    readme = (ROOT / "services/gis-workflow-service/README.md").read_text(encoding="utf-8")
    source = (ROOT / "services/gis-workflow-service/run_bundle.py").read_text(encoding="utf-8")
    assert "أيّ نقطة HTTP" in readme
    assert "run_workflow_bundle" in source


def test_agriai_is_not_falsely_registered_as_mcp_or_production_certified() -> None:
    unified = (ROOT / "docker-compose.unified.yml").read_text(encoding="utf-8")
    supervisor = (ROOT / "services/supervisor-agent/main.py").read_text(encoding="utf-8")
    capability = (ROOT / "services/agriai-engine/simulation_capability.py").read_text(
        encoding="utf-8"
    )
    row = _manifest_row("agriai-engine")

    assert "MCP_AGRIAI_URL" not in unified
    assert "MCP_AGRIAI_URL" not in supervisor
    assert row["classification"] == "experimental-model-runtime"
    assert row["evidence"][0]["kind"] == "activation-safety-contract"
    assert "uncalibrated_pending_golden" in capability
    assert 'flag="SIM_PCSE_ENABLED"' in capability

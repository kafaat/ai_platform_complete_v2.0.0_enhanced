"""ERP bridge naming contract.

The runtime service is now the generic `erp-bridge`, while legacy Odoo names
remain DNS/env/API aliases to avoid breaking existing deployments.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]


def _load_yaml(name: str) -> dict:
    return yaml.safe_load((ROOT / name).read_text(encoding="utf-8"))


def test_v9_compose_uses_erp_bridge_with_legacy_aliases() -> None:
    compose = _load_yaml("docker-compose.v9.yml")
    services = compose["services"]
    assert "sahool-erp-bridge" in services
    assert "sahool-odoo-bridge" not in services

    aliases = services["sahool-erp-bridge"]["networks"]["sahool-internal"]["aliases"]
    assert "sahool-odoo-bridge" in aliases
    assert "odoo-bridge" in aliases
    assert "erp-bridge" in aliases

    market_env = services["sahool-market-mcp"]["environment"]
    assert market_env["ERP_BRIDGE_URL"] == "http://sahool-erp-bridge:8126"
    assert market_env["ODOO_BRIDGE_URL"].startswith("http://sahool-erp-bridge:")


def test_unified_compose_uses_erp_bridge_with_legacy_aliases() -> None:
    compose = _load_yaml("docker-compose.unified.yml")
    services = compose["services"]
    assert "erp-bridge" in services
    assert "odoo-bridge" not in services
    assert "erp-bridge" in services["nginx"]["depends_on"]

    aliases = services["erp-bridge"]["networks"]["sahool-net"]["aliases"]
    assert "sahool-unified-odoo-bridge" in aliases
    assert "sahool-odoo-bridge" in aliases
    assert "odoo-bridge" in aliases
    assert "erp-bridge" in aliases


def test_market_mcp_prefers_erp_bridge_url() -> None:
    src = (ROOT / "services/mcp_servers/market_server.py").read_text(encoding="utf-8")
    assert 'ERP_BRIDGE_URL = os.getenv("ERP_BRIDGE_URL")' in src
    assert 'os.getenv("ODOO_BRIDGE_URL' in src
    assert "http://sahool-erp-bridge:8126" in src


def test_nginx_unified_exposes_generic_erp_route_and_legacy_odoo_route() -> None:
    src = (ROOT / "nginx/nginx.unified.conf").read_text(encoding="utf-8")
    assert "upstream erp_bridge_backend" in src
    assert "location /api/erp/" in src
    assert "location /api/odoo/" in src
    assert "odoo_bridge_backend" not in src


def test_runtime_title_is_generic_erp_bridge() -> None:
    src = (ROOT / "services/odoo-bridge/main.py").read_text(encoding="utf-8")
    assert 'setup_logging("erp-bridge")' in src
    assert 'FastAPI(title="SAHOOL ERP Bridge"' in src
    assert 'service="erp-bridge"' in src

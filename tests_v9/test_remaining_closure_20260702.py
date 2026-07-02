import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_erp_legacy_aliases_exist_only_on_erp_bridge_service():
    legacy = {"sahool-odoo-bridge", "odoo-bridge", "erp-bridge", "sahool-unified-odoo-bridge"}
    allowed = {"sahool-erp-bridge", "erp-bridge"}
    for compose_name in [
        "docker-compose.v9.yml",
        "docker-compose.fixed.yml",
        "docker-compose.unified.yml",
    ]:
        data = yaml.safe_load((ROOT / compose_name).read_text(encoding="utf-8"))
        for svc_name, svc in data["services"].items():
            aliases = []
            networks = svc.get("networks") if isinstance(svc, dict) else None
            if isinstance(networks, dict):
                for cfg in networks.values():
                    if isinstance(cfg, dict):
                        aliases.extend(cfg.get("aliases") or [])
            leaked = legacy.intersection(aliases)
            assert not leaked or svc_name in allowed, (
                f"{compose_name}:{svc_name} owns leaked ERP aliases {leaked}"
            )


def test_unified_erp_bridge_port_matches_dockerfile_and_nginx():
    compose = yaml.safe_load((ROOT / "docker-compose.unified.yml").read_text(encoding="utf-8"))
    svc = compose["services"]["erp-bridge"]
    assert svc["ports"] == ["127.0.0.1:8126:8126"]
    assert "localhost:8126/healthz" in str(svc["healthcheck"]["test"])
    assert "erp-bridge:8126" in (ROOT / "nginx/nginx.unified.conf").read_text(encoding="utf-8")
    dockerfile = (ROOT / "services/odoo-bridge/Dockerfile").read_text(encoding="utf-8")
    assert "EXPOSE 8126" in dockerfile
    assert '--port", "8126"' in dockerfile


def test_new_static_gates_pass():
    for script in [
        "scripts/ci/nginx_compose_dns_gate.py",
        "scripts/ci/service_port_gate.py",
        "scripts/ci/runtime_contract_gate.py",
    ]:
        subprocess.run([sys.executable, str(ROOT / script)], cwd=ROOT, check=True)


def test_live_tenant_auth_gate_script_covers_reject_paths():
    src = (ROOT / "scripts/e2e/tenant_auth_live_gate.py").read_text(encoding="utf-8")
    for token in [
        "current_field_state",
        "tenant mismatch",
        "/api/rag/ingest",
        "/api/knowledge-graph/nodes",
        "X-Agent-Token",
    ]:
        assert token in src

#!/usr/bin/env python3
"""Static service port contract checks for drift-prone services."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]


def y(path: str) -> dict[str, Any]:
    return yaml.safe_load((ROOT / path).read_text(encoding="utf-8")) or {}


def text(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False)


def main() -> int:
    failures: list[str] = []

    unified = y("docker-compose.unified.yml")
    erp = unified["services"].get("erp-bridge", {})
    if erp.get("ports") != ["127.0.0.1:8126:8126"]:
        failures.append("docker-compose.unified.yml erp-bridge must expose 127.0.0.1:8126:8126")
    if "localhost:8126/healthz" not in text(erp.get("healthcheck", {})):
        failures.append("docker-compose.unified.yml erp-bridge healthcheck must use localhost:8126/healthz")
    if "erp-bridge:8126" not in (ROOT / "nginx/nginx.unified.conf").read_text(encoding="utf-8"):
        failures.append("nginx.unified.conf must proxy erp_bridge_backend to erp-bridge:8126")

    # Legacy Odoo DNS aliases must belong only to the ERP bridge, not every service.
    legacy_aliases = {"sahool-odoo-bridge", "odoo-bridge", "erp-bridge", "sahool-unified-odoo-bridge"}
    allowed = {"sahool-erp-bridge", "erp-bridge"}
    for compose_name in ["docker-compose.v9.yml", "docker-compose.fixed.yml", "docker-compose.unified.yml"]:
        data = y(compose_name)
        for svc_name, svc in (data.get("services") or {}).items():
            aliases: list[str] = []
            networks = svc.get("networks") if isinstance(svc, dict) else None
            if isinstance(networks, dict):
                for cfg in networks.values():
                    if isinstance(cfg, dict):
                        aliases.extend(str(a) for a in (cfg.get("aliases") or []))
            leaked = sorted(legacy_aliases.intersection(aliases))
            if leaked and svc_name not in allowed:
                failures.append(f"{compose_name}:{svc_name} incorrectly owns ERP aliases {leaked}")

    out = ROOT / "docs/backend/service_port_gate.generated.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"gate":"service-port-gate", "passed": not failures, "failures": failures}, indent=2, ensure_ascii=False)+"\n")
    if failures:
        print("service-port-gate: FAIL")
        for f in failures:
            print("  -", f)
        return 1
    print("service-port-gate: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

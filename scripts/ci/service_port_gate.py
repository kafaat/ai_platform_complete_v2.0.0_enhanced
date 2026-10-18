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

    # COMPOSE-ALTERNATES-UNGUARDED-AND-NAME-INCOMPATIBLE-01 (2026-10-17): كانت البوّابة تقيس
    # الجسرَ في docker-compose.unified.yml (اسمُه هناك `erp-bridge`) — مكدّسٌ بديل نُقل إلى
    # docs/history/compose/ بقرار مالك. تقيسه الآن حيث يعمل: `sahool-erp-bridge` في v9.
    v9 = y("docker-compose.v9.yml")
    erp = v9["services"].get("sahool-erp-bridge", {})
    if not erp:
        failures.append("docker-compose.v9.yml must define sahool-erp-bridge")
    for port in erp.get("ports") or []:
        if not str(port).startswith("127.0.0.1:"):
            failures.append(
                f"docker-compose.v9.yml sahool-erp-bridge publishes {port} beyond loopback"
            )
    if "localhost:8126/healthz" not in text(erp.get("healthcheck", {})):
        failures.append(
            "docker-compose.v9.yml sahool-erp-bridge healthcheck must use localhost:8126/healthz"
        )
    callers = 0
    for svc_name, svc in (v9.get("services") or {}).items():
        env = (svc or {}).get("environment") or {}
        if isinstance(env, list):
            env = dict(str(item).partition("=")[::2] for item in env)
        for key, value in env.items():
            if "sahool-erp-bridge" in str(value):
                callers += 1
                if "sahool-erp-bridge:8126" not in str(value):
                    failures.append(f"docker-compose.v9.yml:{svc_name} {key} must reach :8126")
    if not callers:
        failures.append(
            "no v9 service reaches sahool-erp-bridge — the port contract measures nothing"
        )

    # Legacy Odoo DNS aliases must belong only to the ERP bridge, not every service.
    legacy_aliases = {
        "sahool-odoo-bridge",
        "odoo-bridge",
        "erp-bridge",
        "sahool-unified-odoo-bridge",
    }
    allowed = {"sahool-erp-bridge", "erp-bridge"}
    for compose_name in ["docker-compose.v9.yml"]:
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
    out.write_text(
        json.dumps(
            {"gate": "service-port-gate", "passed": not failures, "failures": failures},
            indent=2,
            ensure_ascii=False,
        )
        + "\n"
    )
    if failures:
        print("service-port-gate: FAIL")
        for f in failures:
            print("  -", f)
        return 1
    print("service-port-gate: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

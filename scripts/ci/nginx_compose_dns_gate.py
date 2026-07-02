#!/usr/bin/env python3
"""Validate that nginx upstream hostnames are resolvable in the selected compose file.

This is a static DNS contract gate: it catches compose/nginx drift before Docker starts.
It accepts service names, container_name values, and explicit network aliases as resolvable names.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
UPSTREAM_RE = re.compile(r"server\s+([A-Za-z0-9_.-]+):(\d+)\s*;")


def load_yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text()) or {}


def resolvable_names(compose: dict[str, Any]) -> set[str]:
    names: set[str] = set()
    for svc_name, svc in (compose.get("services") or {}).items():
        names.add(str(svc_name))
        if isinstance(svc, dict):
            if svc.get("container_name"):
                names.add(str(svc["container_name"]))
            networks = svc.get("networks")
            if isinstance(networks, dict):
                for cfg in networks.values():
                    if isinstance(cfg, dict):
                        for alias in cfg.get("aliases") or []:
                            names.add(str(alias))
    return names


def upstream_hosts(nginx_conf: str) -> list[tuple[str, int]]:
    return [(host, int(port)) for host, port in UPSTREAM_RE.findall(nginx_conf)]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--compose", default="docker-compose.unified.yml")
    parser.add_argument("--nginx", default="nginx/nginx.unified.conf")
    parser.add_argument("--json", default="docs/backend/nginx_compose_dns_gate.generated.json")
    args = parser.parse_args()

    compose_path = ROOT / args.compose
    nginx_path = ROOT / args.nginx
    compose = load_yaml(compose_path)
    names = resolvable_names(compose)
    upstreams = upstream_hosts(nginx_path.read_text())
    missing = [f"{host}:{port}" for host, port in upstreams if host not in names]
    result = {
        "gate": "nginx-compose-dns-gate",
        "compose": args.compose,
        "nginx": args.nginx,
        "upstreams": [f"{h}:{p}" for h, p in upstreams],
        "missing": missing,
        "passed": not missing,
    }
    out = ROOT / args.json
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    if missing:
        print("nginx-compose-dns-gate: FAIL")
        for item in missing:
            print(f"  missing: {item}")
        return 1
    print(f"nginx-compose-dns-gate: PASS ({len(upstreams)} upstreams)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

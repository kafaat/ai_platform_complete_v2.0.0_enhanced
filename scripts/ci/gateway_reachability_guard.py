#!/usr/bin/env python3
"""Build a deterministic Nginx/API-gateway reachability and security inventory.

Static evidence only. The guard does not claim that Nginx or upstream services
were started. It highlights externally reachable locations, upstream targets,
and explicit auth/tenant-boundary controls.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "gateway-audit" / "generated"
JSON_PATH = OUT / "gateway_reachability.json"
REPORT_PATH = OUT / "GATEWAY_REACHABILITY_REPORT.md"

CONF_FILES = [
    ROOT / "nginx/nginx.v9.conf",
    ROOT / "nginx/nginx.unified.conf",
    ROOT / "nginx/nginx.light.conf",
    ROOT / "nginx/nginx.fixed.conf",
]
SENSITIVE = (
    "actuator",
    "raster",
    "vegetation",
    "soil",
    "field-forms",
    "segmentation",
    "rag",
    "knowledge-graph",
    "ai-agronomist",
    "seasons",
)


def strip_comments(text: str) -> str:
    return "\n".join(line.split("#", 1)[0] for line in text.splitlines())


def blocks(text: str, keyword: str):
    pat = re.compile(rf"\b{re.escape(keyword)}\s+([^{{]+)\{{")
    for m in pat.finditer(text):
        depth, i = 1, m.end()
        while i < len(text) and depth:
            depth += (text[i] == "{") - (text[i] == "}")
            i += 1
        if depth == 0:
            yield m.group(1).strip(), text[m.end() : i - 1], m.start()


def compose_names() -> set[str]:
    names: set[str] = set()
    for path in sorted(ROOT.glob("docker-compose*.yml")) + sorted(
        ROOT.glob("docker-compose*.yaml")
    ):
        text = path.read_text(encoding="utf-8", errors="ignore")
        for m in re.finditer(r"(?m)^\s{2}([A-Za-z0-9_.-]+):\s*$", text):
            names.add(m.group(1))
        for m in re.finditer(r"(?m)^\s*container_name:\s*['\"]?([^\s'\"]+)", text):
            names.add(m.group(1))
    return names


def analyze_file(path: Path, known: set[str]) -> dict[str, Any]:
    raw = path.read_text(encoding="utf-8", errors="ignore")
    text = strip_comments(raw)
    upstreams: dict[str, list[dict[str, Any]]] = {}
    for name, body, _ in blocks(text, "upstream"):
        key = name.split()[0]
        servers = []
        for host, port in re.findall(r"\bserver\s+([A-Za-z0-9_.-]+)(?::(\d+))?", body):
            servers.append(
                {
                    "host": host,
                    "port": int(port) if port else None,
                    "compose_declared": host in known,
                }
            )
        upstreams[key] = servers

    locations = []
    for selector, body, pos in blocks(text, "location"):
        proxy = re.search(r"\bproxy_pass\s+([^;]+);", body)
        if not proxy:
            continue
        target = proxy.group(1).strip()
        up = None
        mm = re.match(r"https?://([A-Za-z0-9_]+)", target)
        if mm:
            up = mm.group(1)
        auth = bool(re.search(r"\bauth_request\s+", body))
        tenant_clear = (
            bool(re.search(r"proxy_set_header\s+X-Tenant-Id\s+[\"']?[\"']?\s*;", body))
            or "proxy_params.conf" in body
        )
        tenant_set = bool(re.search(r"proxy_set_header\s+X-Tenant-Id\s+\$", body))
        internal = selector.startswith("=") and "/_" in selector or "internal" in body
        sensitive = any(token in selector.lower() for token in SENSITIVE)
        locations.append(
            {
                "selector": selector,
                "proxy_pass": target,
                "upstream": up,
                "upstream_defined": up in upstreams if up else None,
                "auth_request": auth,
                "tenant_header_cleared": tenant_clear,
                "trusted_tenant_injected": tenant_set,
                "internal": internal,
                "sensitive": sensitive,
                "line": raw[:pos].count("\n") + 1,
                "security_class": "authenticated_tenant_bound"
                if auth and tenant_set
                else "authenticated"
                if auth
                else "public_or_service_enforced",
            }
        )
    missing_hosts = sorted(
        {s["host"] for vals in upstreams.values() for s in vals if not s["compose_declared"]}
    )
    review = []
    for loc in locations:
        if loc["sensitive"] and not loc["internal"] and not loc["auth_request"]:
            review.append(
                {
                    "kind": "sensitive_route_without_gateway_auth",
                    "selector": loc["selector"],
                    "line": loc["line"],
                    "note": "May rely on service-level auth; requires review, not an automatic vulnerability finding.",
                }
            )
        if loc["upstream"] and not loc["upstream_defined"]:
            review.append(
                {
                    "kind": "undefined_upstream_reference",
                    "selector": loc["selector"],
                    "line": loc["line"],
                    "upstream": loc["upstream"],
                }
            )
    return {
        "file": path.relative_to(ROOT).as_posix(),
        "profile": path.stem,
        "upstreams": upstreams,
        "locations": locations,
        "missing_compose_hosts": missing_hosts,
        "review_findings": review,
    }


def payload() -> dict[str, Any]:
    known = compose_names()
    files = [analyze_file(p, known) for p in CONF_FILES if p.exists()]
    all_locs = [x for f in files for x in f["locations"]]
    hard = [
        x
        for f in files
        for x in f["review_findings"]
        if x["kind"] == "undefined_upstream_reference"
    ]
    review = [x for f in files for x in f["review_findings"]]
    data = {
        "schema_version": "1.0.0",
        "scope": "nginx-static-gateway-reachability",
        "runtime_verified": False,
        "production_certified": False,
        "compose_name_count": len(known),
        "config_count": len(files),
        "upstream_count": sum(len(f["upstreams"]) for f in files),
        "proxied_location_count": len(all_locs),
        "gateway_authenticated_location_count": sum(1 for x in all_locs if x["auth_request"]),
        "tenant_bound_location_count": sum(
            1 for x in all_locs if x["auth_request"] and x["trusted_tenant_injected"]
        ),
        "hard_configuration_errors": hard,
        "review_finding_count": len(review),
        "files": files,
        "boundary": "Static Nginx and Compose evidence only. Service-level authentication and live route behavior require runtime probes.",
    }
    canonical = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    data["content_sha256"] = hashlib.sha256(canonical.encode()).hexdigest()
    return data


def report(d: dict[str, Any]) -> str:
    lines = [
        "# Gateway Reachability and Security Boundary",
        "",
        "**Static evidence only — no live gateway verification.**",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| Configurations | {d['config_count']} |",
        f"| Upstreams | {d['upstream_count']} |",
        f"| Proxied locations | {d['proxied_location_count']} |",
        f"| Gateway-authenticated locations | {d['gateway_authenticated_location_count']} |",
        f"| Authenticated + trusted tenant injection | {d['tenant_bound_location_count']} |",
        f"| Hard configuration errors | {len(d['hard_configuration_errors'])} |",
        f"| Review findings | {d['review_finding_count']} |",
        "",
        "## Per configuration",
        "",
    ]
    for f in d["files"]:
        lines += [
            f"### `{f['file']}`",
            "",
            f"- Upstreams: {len(f['upstreams'])}",
            f"- Proxied locations: {len(f['locations'])}",
            f"- Review findings: {len(f['review_findings'])}",
            f"- Upstream hosts absent from compose inventory: {', '.join(f['missing_compose_hosts']) or 'none'}",
            "",
        ]
    lines += ["## Boundary", "", d["boundary"], "", f"Content SHA-256: `{d['content_sha256']}`", ""]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--generate", action="store_true")
    g.add_argument("--check", action="store_true")
    a = ap.parse_args()
    d = payload()
    j = json.dumps(d, ensure_ascii=False, indent=2) + "\n"
    r = report(d)
    if a.generate:
        OUT.mkdir(parents=True, exist_ok=True)
        JSON_PATH.write_text(j, encoding="utf-8")
        REPORT_PATH.write_text(r, encoding="utf-8")
    else:
        if (
            not JSON_PATH.exists()
            or JSON_PATH.read_text(encoding="utf-8") != j
            or not REPORT_PATH.exists()
            or REPORT_PATH.read_text(encoding="utf-8") != r
        ):
            print("FAIL: gateway inventory drift; run --generate")
            return 1
    print(
        f"PASS: {d['proxied_location_count']} proxied locations; {len(d['hard_configuration_errors'])} hard config errors; {d['review_finding_count']} review findings"
    )
    return 1 if d["hard_configuration_errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())

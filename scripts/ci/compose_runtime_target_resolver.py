#!/usr/bin/env python3
"""Resolve runtime probe targets to internal Docker Compose service URLs.

The resolver is static and conservative: it only emits a target when it can map a
runtime-contract service to one compose service and infer an HTTP port from the
compose definition. It never marks a service runtime verified.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_COMPOSE = ROOT / "docker-compose.v9.yml"
PLAN = ROOT / "runtime-verification/generated/runtime_probe_plan.json"
OUT_DIR = ROOT / "runtime-verification/generated"
OUT_JSON = OUT_DIR / "compose_runtime_targets.json"
OUT_ENV = OUT_DIR / "compose_runtime_targets.env"
OUT_MD = OUT_DIR / "COMPOSE_RUNTIME_TARGETS.md"

URL_RE = re.compile(r"https?://(?:localhost|127\.0\.0\.1):(?P<port>\d+)(?:/[^\s'\"\\)]*)?")
PORT_RE = re.compile(r"(?<!\d)(?P<port>\d{2,5})(?!\d)")

FANOUT_OVERRIDES = {
    "mcp_servers": [
        "sahool-sentinel-hub-mcp",
        "sahool-weather-mcp",
        "sahool-wofost-mcp",
        "sahool-market-mcp",
    ],
}
BUILD_CONTEXT_OVERRIDES = {
    "model-registry-adapter": "services/model-registry-adapter",
}
PORT_OVERRIDES = {
    "model-registry-adapter": 8099,
}


def canonical(value: str) -> str:
    value = value.lower().replace("_", "-")
    value = re.sub(r"^sahool-", "", value)
    value = re.sub(r"-service$", "", value)
    return re.sub(r"[^a-z0-9]", "", value)


def flatten(value: Any) -> str:
    if isinstance(value, list):
        return " ".join(flatten(item) for item in value)
    if isinstance(value, dict):
        return " ".join(f"{k}={flatten(v)}" for k, v in value.items())
    return str(value or "")


def infer_http_port(service: dict[str, Any]) -> tuple[int | None, str | None]:
    health = flatten(service.get("healthcheck", {}).get("test"))
    match = URL_RE.search(health)
    if match:
        return int(match.group("port")), "healthcheck_url"

    for raw in service.get("expose") or []:
        text = str(raw).split("/")[0]
        if text.isdigit():
            return int(text), "expose"

    for raw in service.get("ports") or []:
        if isinstance(raw, dict):
            target = raw.get("target")
            if isinstance(target, int):
                return target, "published_target"
            continue
        text = str(raw).split("/")[0]
        target = text.rsplit(":", 1)[-1]
        if target.isdigit():
            return int(target), "published_target"

    environment = service.get("environment") or {}
    if isinstance(environment, list):
        environment = dict(
            item.split("=", 1) for item in environment if isinstance(item, str) and "=" in item
        )
    for key in ("PORT", "HTTP_PORT", "SERVICE_PORT"):
        value = environment.get(key) if isinstance(environment, dict) else None
        if str(value or "").isdigit():
            return int(value), f"environment:{key}"

    command = flatten(service.get("command"))
    match = re.search(r"(?:--port|--bind|:)[=\s:]*(\d{2,5})", command)
    if match:
        return int(match.group(1)), "command"
    return None, None


def match_compose_service(
    plan_item: dict[str, Any], compose_services: dict[str, Any]
) -> tuple[str | None, list[str]]:
    candidates = {
        canonical(plan_item["service"]),
        canonical(plan_item.get("source_service", "")),
    }
    aliases = {
        "erpbridge": "erpbridge",
        "odoo-bridge": "erpbridge",
        "aiagronomist": "aiagronomist",
    }
    candidates |= {canonical(aliases.get(c, c)) for c in list(candidates)}

    scored: list[tuple[int, str]] = []
    for name in compose_services:
        normalized = canonical(name)
        score = 0
        if normalized in candidates:
            score = 100
        elif any(c and (c in normalized or normalized in c) for c in candidates):
            score = 50
        if score:
            scored.append((score, name))
    scored.sort(key=lambda item: (-item[0], item[1]))
    if not scored:
        return None, []
    best = scored[0][0]
    tied = [name for score, name in scored if score == best]
    return (tied[0] if len(tied) == 1 else None), tied


def digest(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def match_by_build_context(service_name: str, compose_services: dict[str, Any]) -> str | None:
    expected = BUILD_CONTEXT_OVERRIDES.get(service_name)
    if not expected:
        return None
    matches = []
    for name, spec in compose_services.items():
        build = spec.get("build")
        context = build.get("context") if isinstance(build, dict) else build
        if str(context or "").rstrip("/") == expected.rstrip("/"):
            matches.append(name)
    return matches[0] if len(matches) == 1 else None


def build(compose_path: Path = DEFAULT_COMPOSE) -> tuple[dict[str, Any], str, str]:
    compose = yaml.safe_load(compose_path.read_text(encoding="utf-8")) or {}
    services = compose.get("services") or {}
    plan = json.loads(PLAN.read_text(encoding="utf-8"))

    targets: list[dict[str, Any]] = []
    for item in plan["services"]:
        if not item.get("probes"):
            continue
        service_name = item["service"]
        member_names = FANOUT_OVERRIDES.get(service_name, [])
        if member_names:
            members = []
            for name in member_names:
                spec = services.get(name) or {}
                port, source = infer_http_port(spec)
                members.append(
                    {
                        "compose_service": name,
                        "port": port,
                        "port_source": source,
                        "base_url": f"http://{name}:{port}" if port else None,
                        "profiles": spec.get("profiles") or [],
                        "resolved": bool(port),
                    }
                )
            resolved = bool(members) and all(m["resolved"] for m in members)
            compose_name = None
            matches = member_names
            port = source = None
            base_url = None
            profiles = sorted({p for m in members for p in m["profiles"]})
        else:
            compose_name, matches = match_compose_service(item, services)
            if not compose_name:
                compose_name = match_by_build_context(service_name, services)
                if compose_name:
                    matches = [compose_name]
            port = source = None
            if compose_name:
                port, source = infer_http_port(services[compose_name])
                if port is None and service_name in PORT_OVERRIDES:
                    port, source = PORT_OVERRIDES[service_name], "contract_override"
            resolved = bool(compose_name and port)
            base_url = f"http://{compose_name}:{port}" if resolved else None
            profiles = (
                (services.get(compose_name, {}).get("profiles") or []) if compose_name else []
            )
            members = []
        targets.append(
            {
                "service": service_name,
                "source_service": item.get("source_service"),
                "base_url_env": item["base_url_env"],
                "compose_service": compose_name,
                "candidate_matches": matches,
                "port": port,
                "port_source": source,
                "base_url": base_url,
                "members": members,
                "profiles": profiles,
                "resolved": resolved,
                "runtime_verified": False,
                "production_certified": False,
            }
        )

    core = {
        "schema_version": 1,
        "compose_file": str(compose_path.relative_to(ROOT)),
        "source_plan_sha256": plan["plan_sha256"],
        "targets": targets,
        "fail_closed": True,
        "runtime_verified": False,
        "production_certified": False,
    }
    payload = {**core, "targets_sha256": digest(core)}
    env_lines = []
    for row in targets:
        if not row["resolved"]:
            continue
        urls = [m["base_url"] for m in row.get("members", [])] or [row["base_url"]]
        env_lines.append(f"{row['base_url_env']}={','.join(urls)}")
    env = "\n".join(env_lines) + "\n"
    resolved = sum(1 for row in targets if row["resolved"])
    unresolved = [row for row in targets if not row["resolved"]]
    report = (
        "\n".join(
            [
                "# Compose Runtime Targets",
                "",
                f"- Planned HTTP services: **{len(targets)}**",
                f"- Resolved internal targets: **{resolved}**",
                f"- Unresolved targets: **{len(unresolved)}**",
                "- Runtime verified: **0**",
                "- Production certified: **0**",
                "",
                "## Unresolved",
                "",
                *(
                    ["None."]
                    if not unresolved
                    else [
                        f"- `{row['service']}`: compose match={row['candidate_matches'] or 'none'}, port={row['port'] or 'unknown'}"
                        for row in unresolved
                    ]
                ),
                "",
                "Static target resolution is not runtime evidence.",
            ]
        )
        + "\n"
    )
    return payload, env, report


def write(compose_path: Path = DEFAULT_COMPOSE) -> dict[str, Any]:
    payload, env, report = build(compose_path)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    OUT_ENV.write_text(env, encoding="utf-8")
    OUT_MD.write_text(report, encoding="utf-8")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--compose-file", default=str(DEFAULT_COMPOSE))
    parser.add_argument("--generate", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--require-complete", action="store_true")
    args = parser.parse_args()
    compose_path = Path(args.compose_file)
    if not compose_path.is_absolute():
        compose_path = ROOT / compose_path
    payload, env, report = build(compose_path)
    if args.generate:
        write(compose_path)
    if args.check:
        stored = json.loads(OUT_JSON.read_text(encoding="utf-8"))
        if (
            stored != payload
            or OUT_ENV.read_text(encoding="utf-8") != env
            or OUT_MD.read_text(encoding="utf-8") != report
        ):
            print("Compose runtime target drift", flush=True)
            return 1
    unresolved = [row["service"] for row in payload["targets"] if not row["resolved"]]
    print(
        f"Compose runtime targets: {len(payload['targets']) - len(unresolved)}/{len(payload['targets'])} resolved"
    )
    if args.require_complete and unresolved:
        print("Unresolved: " + ", ".join(unresolved))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

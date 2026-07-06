#!/usr/bin/env python3
"""Fail-closed contract gate for docker-compose ↔ .env compatibility.

Checks:
- every ${VAR} referenced by compose files is declared in .env.example or frontend/.env.example
- no duplicate keys inside env example files
- MinIO/S3 aliases use one coherent local value
- MinIO root user is not hardcoded differently from .env
- risky nested S3 interpolation is avoided
- services that persist/read rasters have the required storage env contract
"""

from __future__ import annotations

import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
ENV_FILES = [ROOT / ".env.example", ROOT / "frontend" / ".env.example"]
COMPOSE_FILES = sorted(ROOT.glob("docker-compose*.yml")) + sorted(
    (ROOT / "frontend").glob("docker-compose*.yml")
)
VAR_RE = re.compile(
    r"(?<!\$)\$\{([A-Za-z_][A-Za-z0-9_]*)(?:(?::-|:-|\?|:\?|-)[^}]*)?\}|(?<!\$)\$([A-Za-z_][A-Za-z0-9_]*)"
)


def parse_env(path: Path) -> tuple[dict[str, str], list[str]]:
    values: dict[str, str] = {}
    keys: list[str] = []
    if not path.exists():
        return values, keys
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        values[key] = value.strip()
        keys.append(key)
    return values, keys


def compose_env_map(service: dict[str, Any]) -> dict[str, str]:
    env = service.get("environment") or {}
    if isinstance(env, dict):
        return {str(k): "" if v is None else str(v) for k, v in env.items()}
    if isinstance(env, list):
        out: dict[str, str] = {}
        for item in env:
            if not isinstance(item, str):
                continue
            if "=" in item:
                k, v = item.split("=", 1)
                out[k] = v
            else:
                out[item] = ""
        return out
    return {}


def main() -> int:
    errors: list[str] = []
    warnings: list[str] = []

    env_values: dict[str, str] = {}
    all_env_keys: list[str] = []
    per_file_dups: dict[str, list[str]] = {}
    for path in ENV_FILES:
        values, keys = parse_env(path)
        env_values.update(values)
        all_env_keys.extend(keys)
        dups = sorted(k for k, c in Counter(keys).items() if c > 1)
        if dups:
            per_file_dups[str(path.relative_to(ROOT))] = dups

    if per_file_dups:
        for rel, dups in per_file_dups.items():
            errors.append(f"duplicate keys in {rel}: {', '.join(dups)}")

    compose_refs: dict[str, set[str]] = defaultdict(set)
    for path in COMPOSE_FILES:
        text = path.read_text(encoding="utf-8")
        for match in VAR_RE.finditer(text):
            var = match.group(1) or match.group(2)
            compose_refs[var].add(str(path.relative_to(ROOT)))

    missing = sorted(set(compose_refs) - set(env_values))
    if missing:
        for var in missing:
            errors.append(
                f"compose variable ${var} is not declared in env examples; referenced by {sorted(compose_refs[var])}"
            )

    # MinIO/S3 single source of truth for local/dev. Dedicated production service
    # accounts are still possible by intentionally changing all aliases together.
    equality_groups = [
        ["MINIO_ROOT_USER", "MINIO_ACCESS_KEY", "S3_ACCESS_KEY"],
        ["MINIO_ROOT_PASSWORD", "MINIO_SECRET_KEY", "S3_SECRET_KEY"],
    ]
    for group in equality_groups:
        present = {k: env_values.get(k) for k in group if k in env_values}
        non_empty = {k: v for k, v in present.items() if v not in (None, "")}
        if len(set(non_empty.values())) > 1:
            errors.append(f"credential alias mismatch: {non_empty}")

    # Compose-level service contract checks.
    for path in COMPOSE_FILES:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        services = data.get("services") or {}
        for name, service in services.items():
            env = compose_env_map(service)
            if name == "sahool-minio":
                root = env.get("MINIO_ROOT_USER", "")
                if root and "${MINIO_ROOT_USER" not in root:
                    errors.append(f"{path.name}:{name} hardcodes MINIO_ROOT_USER={root!r}")
                if "MINIO_ROOT_PASSWORD" not in env:
                    errors.append(f"{path.name}:{name} missing MINIO_ROOT_PASSWORD")
            if name in {
                "sahool-raster-service",
                "sahool-raster-backfill-scan-worker",
                "sahool-raster-cache-invalidation-worker",
            }:
                required = [
                    "RASTER_UPLOAD_DIR",
                    "S3_ENDPOINT",
                    "S3_BUCKET",
                    "S3_ACCESS_KEY",
                    "S3_SECRET_KEY",
                    "S3_REGION",
                    "S3_USE_SSL",
                    "S3_ALLOW_FILE_FALLBACK",
                ]
                missing_env = [k for k in required if k not in env]
                if missing_env:
                    errors.append(
                        f"{path.name}:{name} missing storage env: {', '.join(missing_env)}"
                    )
            if name == "sahool-titiler":
                required = [
                    "AWS_S3_ENDPOINT",
                    "AWS_ACCESS_KEY_ID",
                    "AWS_SECRET_ACCESS_KEY",
                    "AWS_DEFAULT_REGION",
                ]
                missing_env = [k for k in required if k not in env]
                if missing_env:
                    errors.append(
                        f"{path.name}:{name} missing TiTiler S3 env: {', '.join(missing_env)}"
                    )
                vols = "\n".join(str(v) for v in service.get("volumes", []) or [])
                if "raster-data" not in vols:
                    warnings.append(
                        f"{path.name}:{name} does not mount raster-data; OK only if using S3 exclusively"
                    )

    # Avoid nested S3/MinIO interpolation: Docker Compose interpolation semantics are
    # easy to misread and drift across implementations.
    risky = []
    for path in COMPOSE_FILES:
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if (
                any(
                    token in line
                    for token in (
                        "S3_ACCESS_KEY",
                        "S3_SECRET_KEY",
                        "AWS_ACCESS_KEY_ID",
                        "AWS_SECRET_ACCESS_KEY",
                    )
                )
                and "${" in line
            ):
                if line.count("${") > 1:
                    risky.append(f"{path.relative_to(ROOT)}:{lineno}: {line.strip()}")
    if risky:
        errors.append("nested S3/MinIO interpolation found:\n" + "\n".join(risky))

    if errors:
        print("compose-env contract: FAIL", file=sys.stderr)
        for err in errors:
            print(f"- {err}", file=sys.stderr)
        for warn in warnings:
            print(f"warning: {warn}", file=sys.stderr)
        return 1

    print("compose-env contract: OK")
    print(
        f"checked {len(COMPOSE_FILES)} compose files, {len(set(all_env_keys))} env keys, {len(compose_refs)} compose references"
    )
    for warn in warnings:
        print(f"warning: {warn}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""SAHOOL runtime bootstrap and environment doctor.

Dependency-free preflight/runtime checker for local Docker Compose and Kubernetes
operators. It never mutates the environment; it reports blocking failures,
warnings, and next actions as JSON or text.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import urlparse

ROOT_MARKERS = ["docker-compose.v9.yml", "migrations/MANIFEST.txt"]
REQUIRED_FILES = [
    "docker-compose.v9.yml",
    ".env.example",
    "scripts/production_validation_gate.sh",
    "scripts/security_audit.sh",
    "scripts/security/rls_runtime_gate.py",
    "scripts/check_gateway_routes.sh",
    "scripts/runtime_smoke.sh",
    "scripts/observability/validate_observability_assets.py",
    "scripts/release/validate_release_package.py",
    "scripts/ci/local_quality_gate.sh",
    "scripts/ci/minio_s3_contract_gate.py",
    "scripts/migrations/validate_migration_manifest.py",
]
REQUIRED_MIGRATIONS = [
    "v106_phase9_10_runtime_strengthening.sql",
    "v107_phase9_10_event_drift_hardening.sql",
    "v108_phase10_feature_store_model_registry_runtime.sql",
    "v109_phase9_iot_execution_adapters.sql",
    "v110_phase12_plugin_sandbox_runtime.sql",
    "v111_phase11_federated_agent_runtime.sql",
    "v112_mobile_offline_sync_runtime.sql",
]
REQUIRED_ENV = [
    "DATABASE_URL",
    "JOBS_DATABASE_URL",
    "JWT_PUBLIC_KEY",
    "JWT_ISSUER",
    "JWT_AUDIENCE",
    "X_AGENT_TOKEN",
    "REDIS_URL",
    "NATS_URL",
    "MINIO_ROOT_USER",
    "MINIO_ROOT_PASSWORD",
    "MINIO_ACCESS_KEY",
    "MINIO_SECRET_KEY",
]
DEFAULT_SECRET_PATTERNS = [
    re.compile(r"changeme", re.I),
    re.compile(r"placeholder", re.I),
    re.compile(r"example", re.I),
    re.compile(r"dev-secret", re.I),
    re.compile(r"default", re.I),
]
COMPOSE_SERVICES = [
    "sahool-platform",
    "sahool-nginx",
    "sahool-raster-service",
    "sahool-titiler",
    "sahool-rag-retrieval",
    "sahool-knowledge-graph",
    "sahool-ai-agronomist",
    "sahool-guardrails-engine",
    "sahool-phase-runtime-outbox-worker",
    "sahool-plugin-runtime-worker",
    "sahool-model-registry-worker",
    "sahool-actuator-dispatch-worker",
]
HEALTH_PATHS = [
    "/healthz",
    "/api/v1/healthz",
    "/api/raster/healthz",
    "/api/ai-agronomist/healthz",
    "/api/rag/healthz",
    "/api/knowledge-graph/healthz",
]
METRICS_PATHS = [
    "/metrics",
    "/api/ai-agronomist/metrics",
    "/api/rag/metrics",
    "/api/knowledge-graph/metrics",
]


@dataclass
class Check:
    name: str
    status: str  # pass, warn, fail, skip
    message: str
    detail: dict[str, object] | None = None


def find_root(start: Path) -> Path:
    cur = start.resolve()
    while True:
        if all((cur / marker).exists() for marker in ROOT_MARKERS):
            return cur
        if cur.parent == cur:
            return start.resolve()
        cur = cur.parent


def add(
    checks: list[Check],
    name: str,
    status: str,
    message: str,
    detail: dict[str, object] | None = None,
) -> None:
    checks.append(Check(name=name, status=status, message=message, detail=detail or {}))


def load_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        values[k.strip()] = v.strip().strip('"').strip("'")
    return values


def merged_env(root: Path) -> dict[str, str]:
    vals = load_env_file(root / ".env.example")
    vals.update(load_env_file(root / ".env"))
    runtime_keys = set(REQUIRED_ENV) | {"S3_ACCESS_KEY"}
    vals.update({k: v for k, v in os.environ.items() if k in runtime_keys or k.endswith("_URL")})
    return vals


def check_required_files(root: Path, checks: list[Check]) -> None:
    missing = [rel for rel in REQUIRED_FILES if not (root / rel).exists()]
    add(
        checks,
        "required-files",
        "fail" if missing else "pass",
        "required bootstrap assets present" if not missing else "missing bootstrap assets",
        {"missing": missing},
    )


def check_env(root: Path, checks: list[Check]) -> None:
    env = merged_env(root)
    missing = [k for k in REQUIRED_ENV if not env.get(k)]
    defaults = [
        k
        for k, v in env.items()
        if k in REQUIRED_ENV and any(p.search(v) for p in DEFAULT_SECRET_PATTERNS)
    ]
    db_url = env.get("DATABASE_URL", "")
    jobs_url = env.get("JOBS_DATABASE_URL", "")
    db_user = urlparse(db_url).username or ""
    jobs_user = urlparse(jobs_url).username or ""
    db_role_ok = (not db_url) or db_user == "sahool_app"
    jobs_role_ok = (not jobs_url) or jobs_user == "sahool_jobs"
    status = "pass"
    issues = []
    if missing:
        status = "warn"
        issues.append("missing environment variables")
    if defaults:
        status = "fail"
        issues.append("default or placeholder secrets present")
    if db_url and not db_role_ok:
        status = "fail"
        issues.append("DATABASE_URL must use sahool_app runtime role")
    minio_root = env.get("MINIO_ROOT_USER", "")
    minio_access = env.get("MINIO_ACCESS_KEY", "")
    s3_access = env.get("S3_ACCESS_KEY", "")
    if minio_root and minio_access and minio_access not in {"${MINIO_ROOT_USER}", minio_root}:
        status = "fail"
        issues.append(
            "MINIO_ACCESS_KEY must match MINIO_ROOT_USER unless a dedicated service account is documented"
        )
    if (
        minio_root
        and s3_access
        and s3_access not in {"${MINIO_ACCESS_KEY}", "${MINIO_ROOT_USER}", minio_root, minio_access}
    ):
        status = "fail"
        issues.append("S3_ACCESS_KEY must resolve from MINIO_ACCESS_KEY/MINIO_ROOT_USER by default")
    if jobs_url and not jobs_role_ok:
        status = "fail"
        issues.append("JOBS_DATABASE_URL must use sahool_jobs")
    add(
        checks,
        "environment",
        status,
        "; ".join(issues) if issues else "environment contract looks safe",
        {
            "missing": missing,
            "default_like": defaults,
            "database_user": db_user,
            "jobs_user": jobs_user,
            "database_role_ok": db_role_ok,
            "jobs_role_ok": jobs_role_ok,
            "minio_root_user": minio_root,
            "minio_access_key": minio_access,
            "s3_access_key": s3_access,
        },
    )


def check_migrations(root: Path, checks: list[Check]) -> None:
    manifest_path = root / "migrations/MANIFEST.txt"
    manifest = (
        manifest_path.read_text(encoding="utf-8", errors="replace")
        if manifest_path.exists()
        else ""
    )
    missing = [m for m in REQUIRED_MIGRATIONS if m not in manifest]
    add(
        checks,
        "migrations",
        "fail" if missing else "pass",
        "runtime migrations registered" if not missing else "missing runtime migrations",
        {"missing": missing},
    )


def check_compose_static(root: Path, checks: list[Check]) -> None:
    path = root / "docker-compose.v9.yml"
    text = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
    missing_services = [svc for svc in COMPOSE_SERVICES if svc not in text]
    forbidden = []
    if re.search(r"POSTGRES_USER\s*[:=]\s*postgres\b", text):
        forbidden.append("POSTGRES_USER=postgres")
    if re.search(r"SAHOOL_ALLOW_RLS_BYPASS_ROLE\s*[:=]", text):
        forbidden.append("SAHOOL_ALLOW_RLS_BYPASS_ROLE")
    if re.search(r"image:\s*[^\n:]+:latest\b", text, re.I):
        forbidden.append("image:latest")
    status = "fail" if missing_services or forbidden else "pass"
    add(
        checks,
        "compose-static",
        status,
        "compose service/security contract satisfied"
        if status == "pass"
        else "compose static contract failed",
        {"missing_services": missing_services, "forbidden": forbidden},
    )


def command_available(name: str) -> bool:
    """Return True when an executable is discoverable on PATH.

    Some hardened CI/container environments include PATH entries that are not
    readable by the current user. Path.exists() can raise PermissionError for
    those entries, so the doctor must treat them as unavailable and continue
    scanning instead of crashing the whole preflight.
    """
    for raw_dir in os.environ.get("PATH", "").split(os.pathsep):
        if not raw_dir:
            continue
        try:
            candidate = Path(raw_dir) / name
            if candidate.is_file() and os.access(candidate, os.X_OK):
                return True
        except (OSError, PermissionError):
            continue
    return False


def run_command(cmd: list[str], cwd: Path, timeout: int = 30) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
        )
        return proc.returncode, proc.stdout[-4000:]
    except FileNotFoundError as exc:
        return 127, str(exc)
    except subprocess.TimeoutExpired as exc:
        return 124, (exc.stdout or "")[-4000:] + "\nTIMEOUT"


def check_compose_config(root: Path, checks: list[Check]) -> None:
    if not command_available("docker"):
        add(checks, "docker-compose-config", "skip", "docker not available in this environment")
        return
    code, output = run_command(
        ["docker", "compose", "-f", "docker-compose.v9.yml", "config", "--quiet"], root, timeout=45
    )
    add(
        checks,
        "docker-compose-config",
        "pass" if code == 0 else "fail",
        "docker compose config passed" if code == 0 else "docker compose config failed",
        {"exit_code": code, "output": output},
    )


def check_ports(
    checks: list[Check],
    host: str = "127.0.0.1",
    ports: Iterable[int] = (80, 443, 8000, 8080, 8090, 8092, 5432, 6379, 4222, 9000),
) -> None:
    occupied: list[int] = []
    for port in ports:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.2)
            if sock.connect_ex((host, port)) == 0:
                occupied.append(port)
    add(
        checks,
        "local-port-scan",
        "warn" if occupied else "pass",
        "ports currently occupied; verify they belong to SAHOOL"
        if occupied
        else "default ports are available",
        {"occupied": occupied},
    )


def http_get(url: str, timeout: float = 3.0) -> tuple[int | None, str]:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "sahool-env-doctor/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read(2048).decode("utf-8", errors="replace")
            return int(resp.status), body
    except urllib.error.HTTPError as exc:
        return int(exc.code), exc.read(1024).decode("utf-8", errors="replace")
    except Exception as exc:  # network not available / service not started
        return None, str(exc)


def check_http_runtime(checks: list[Check], base_url: str) -> None:
    health = {}
    for path in HEALTH_PATHS:
        status, body = http_get(base_url.rstrip("/") + path)
        health[path] = {"status": status, "sample": body[:160]}
    reachable = [
        p for p, r in health.items() if isinstance(r["status"], int) and int(r["status"]) < 500
    ]
    add(
        checks,
        "runtime-health-http",
        "pass" if reachable else "skip",
        "runtime health endpoints reachable"
        if reachable
        else "runtime not reachable or not started",
        {"reachable": reachable, "results": health},
    )

    metrics = {}
    for path in METRICS_PATHS:
        status, body = http_get(base_url.rstrip("/") + path)
        metrics[path] = {"status": status, "sample": body[:160]}
    metrics_ok = [
        p for p, r in metrics.items() if isinstance(r["status"], int) and int(r["status"]) < 500
    ]
    add(
        checks,
        "runtime-metrics-http",
        "pass" if metrics_ok else "skip",
        "metrics endpoints reachable"
        if metrics_ok
        else "metrics not reachable or runtime not started",
        {"reachable": metrics_ok, "results": metrics},
    )


def check_static_gates(root: Path, checks: list[Check]) -> None:
    gates = [
        ("production-gate", ["bash", "scripts/production_validation_gate.sh"]),
        (
            "observability-gate",
            [
                sys.executable,
                "scripts/observability/validate_observability_assets.py",
                "--root",
                ".",
            ],
        ),
        (
            "helm-gate",
            [sys.executable, "scripts/deploy/validate_helm_readiness.py", "--env", "production"],
        ),
        (
            "release-gate",
            [sys.executable, "scripts/release/validate_release_package.py", "--root", "."],
        ),
        ("ci-gate", [sys.executable, "scripts/ci/validate_ci_gates.py", "--root", "."]),
        (
            "migration-manifest-gate",
            [sys.executable, "scripts/migrations/validate_migration_manifest.py", "--root", "."],
        ),
    ]
    for name, cmd in gates:
        if not (root / cmd[-1]).exists() and cmd[-1].endswith(".py"):
            add(checks, name, "skip", f"gate asset not present: {cmd[-1]}")
            continue
        code, output = run_command(cmd, root, timeout=90)
        add(
            checks,
            name,
            "pass" if code == 0 else "fail",
            f"{name} passed" if code == 0 else f"{name} failed",
            {"exit_code": code, "output": output},
        )


def summarize(checks: list[Check]) -> dict[str, object]:
    counts = {"pass": 0, "warn": 0, "fail": 0, "skip": 0}
    for c in checks:
        counts[c.status] = counts.get(c.status, 0) + 1
    readiness = (
        "blocked" if counts.get("fail", 0) else ("attention" if counts.get("warn", 0) else "ready")
    )
    return {"readiness": readiness, "counts": counts, "generated_at_epoch": int(time.time())}


def render_text(summary: dict[str, object], checks: list[Check]) -> str:
    lines = [
        "SAHOOL Runtime Bootstrap Doctor",
        f"readiness: {summary['readiness']}",
        f"counts: {summary['counts']}",
        "",
    ]
    icon = {"pass": "OK", "warn": "WARN", "fail": "FAIL", "skip": "SKIP"}
    for c in checks:
        lines.append(f"[{icon.get(c.status, c.status)}] {c.name}: {c.message}")
        if c.detail:
            compact = {k: v for k, v in c.detail.items() if v not in (None, {}, [], "")}
            if compact:
                lines.append("  " + json.dumps(compact, ensure_ascii=False, sort_keys=True)[:1000])
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="SAHOOL runtime bootstrap/environment doctor")
    parser.add_argument("--root", default=".")
    parser.add_argument("--base-url", default=os.environ.get("BASE_URL", "http://localhost"))
    parser.add_argument("--mode", choices=["preflight", "runtime", "full"], default="preflight")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    parser.add_argument("--output", default="")
    parser.add_argument("--fail-on-warn", action="store_true")
    args = parser.parse_args()

    root = find_root(Path(args.root))
    checks: list[Check] = []
    check_required_files(root, checks)
    check_env(root, checks)
    check_migrations(root, checks)
    check_compose_static(root, checks)
    check_compose_config(root, checks)
    check_ports(checks)
    if args.mode in {"runtime", "full"}:
        check_http_runtime(checks, args.base_url)
    if args.mode == "full":
        check_static_gates(root, checks)

    summary = summarize(checks)
    payload = {"summary": summary, "checks": [asdict(c) for c in checks]}
    output = (
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        if args.format == "json"
        else render_text(summary, checks)
    )
    if args.output:
        Path(args.output).write_text(output, encoding="utf-8")
    print(output, end="")
    if summary["readiness"] == "blocked":
        return 1
    if args.fail_on_warn and summary["readiness"] == "attention":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

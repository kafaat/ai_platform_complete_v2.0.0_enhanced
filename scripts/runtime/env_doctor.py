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


# MINIO-IMAGES-DELETED-FROM-DOCKER-HUB-01: MinIO deleted `minio/minio` and `minio/mc` from Docker Hub
# (2026-09-11..14). #1139 moved the compose defaults and `.env.example` to a digest-pinned mirror, but
# the old template set MINIO_IMAGE / MINIO_MC_IMAGE explicitly to the deleted repositories, and compose
# lets the shell and `.env` override the default. A `.env` copied from the old template therefore keeps
# `docker compose up` failing with "pull access denied for minio/mc" after the code is updated — and
# `.env` is untracked, so no CI gate can see it. Same pattern as `_DELETED_REPO` in
# scripts/ci/minio_s3_contract_gate.py, kept local because this doctor is dependency-free.
_DELETED_MINIO_REPO = re.compile(r"^(?:docker\.io/)?minio/(?:minio|mc)(?=[:@]|$)")
MINIO_IMAGE_KEYS = ("MINIO_IMAGE", "MINIO_MC_IMAGE")


def check_minio_images(root: Path, checks: list[Check]) -> None:
    template = load_env_file(root / ".env.example")
    local = load_env_file(root / ".env")
    effective: dict[str, str] = {}
    for key in MINIO_IMAGE_KEYS:
        # Compose interpolation order: the shell, then `.env`, then the compose default. A shell
        # value wins even when empty, and `${VAR:-pin}` then selects the pin (Copilot on #1162).
        value = os.environ[key] if key in os.environ else local.get(key, "")
        if value:
            effective[key] = value
    stale = {k: v for k, v in effective.items() if _DELETED_MINIO_REPO.match(v)}
    drift = {
        k: v
        for k, v in effective.items()
        if k not in stale and template.get(k) and v != template[k]
    }
    if stale:
        status = "fail"
        message = (
            "MinIO image in .env or the shell names a repository MinIO deleted from Docker Hub "
            "(pull access denied for minio/mc); copy MINIO_IMAGE and MINIO_MC_IMAGE from "
            ".env.example or delete both lines from .env"
        )
    elif drift:
        status = "warn"
        message = "MinIO image overridden away from the digest pin in .env.example"
    else:
        status = "pass"
        message = "MinIO images resolve to the digest pin from .env.example or the compose default"
    add(
        checks,
        "minio-images",
        status,
        message,
        {
            "stale": stale,
            "differs_from_template": drift,
            "template": {k: template.get(k, "") for k in MINIO_IMAGE_KEYS},
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


# COMPOSE-REQUIRED-VARS-ONE-AT-A-TIME-01: Compose interpolates every service of every file it is
# given (profiles included) before `config`, `build` or `up`, and stops at the FIRST `${VAR:?}`
# with no value. A GPU build on a fresh machine therefore fails ~57 times, one secret per try.
# This check reads the same files and reports every missing required variable in one pass.
# It compares names only: values are never read into the report.
_COMPOSE_TOKEN = re.compile(r"\$\$|\$\{")
_COMPOSE_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_COMPOSE_OPS = (":?", "?", ":-", "-", ":+", "+")


@dataclass
class RequiredVar:
    name: str
    rule: str  # "unset-or-empty" (`:?`) or "unset" (`?`)
    message: str
    location: str


def strip_compose_comments(text: str) -> str:
    """Blank YAML comments so a `${VAR:?}` written inside one is not counted.

    Line-based: a `#` at the start of a line or after whitespace, outside quotes on that line,
    starts a comment. Line numbers are preserved.
    """
    out: list[str] = []
    for line in text.split("\n"):
        quote = ""
        cut = len(line)
        for i, ch in enumerate(line):
            if quote:
                if ch == quote:
                    quote = ""
            elif ch in "'\"" and (i == 0 or line[i - 1] in " \t:[{,-"):
                quote = ch
            elif ch == "#" and (i == 0 or line[i - 1] in " \t"):
                cut = i
                break
        out.append(line[:cut])
    return "\n".join(out)


def _closing_brace(text: str, start: int) -> int:
    """Index of the `}` closing the `${` whose body starts at ``start`` (nesting-aware)."""
    depth = 1
    i = start
    while i < len(text):
        if text.startswith("$$", i):
            i += 2
            continue
        if text.startswith("${", i):
            depth += 1
            i += 2
            continue
        if text[i] == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def _present(env: dict[str, str], name: str, empty_counts: bool) -> bool:
    if name not in env:
        return False
    return bool(env[name]) or not empty_counts


def _compose_substitute(
    text: str,
    env: dict[str, str],
    origin: int,
    locate,
    found: list[RequiredVar],
    missing: list[RequiredVar],
) -> None:
    """Walk ``text`` with Compose's interpolation rules, recording required variables.

    Like Compose, a nested default is evaluated only when the outer variable needs it
    (``${DATABASE_URL:-...${APP_DB_PASSWORD:?}...}`` requires APP_DB_PASSWORD only while
    DATABASE_URL is unset or empty). Unlike Compose, it does not stop at the first miss.
    """
    pos = 0
    while True:
        m = _COMPOSE_TOKEN.search(text, pos)
        if not m:
            return
        if m.group(0) == "$$":
            pos = m.end()
            continue
        body_start = m.end()
        end = _closing_brace(text, body_start)
        if end < 0:
            return
        body = text[body_start:end]
        pos = end + 1
        nm = _COMPOSE_NAME.match(body)
        if not nm:
            continue
        name = nm.group(0)
        rest = body[nm.end() :]
        op = next((o for o in _COMPOSE_OPS if rest.startswith(o)), "")
        arg = rest[len(op) :]
        arg_origin = origin + body_start + nm.end() + len(op)
        if op in (":?", "?"):
            req = RequiredVar(
                name=name,
                rule="unset-or-empty" if op == ":?" else "unset",
                message=" ".join(arg.split()),
                location=locate(origin + m.start()),
            )
            found.append(req)
            if not _present(env, name, empty_counts=op == ":?"):
                missing.append(req)
        elif op in (":-", "-"):
            if not _present(env, name, empty_counts=op == ":-"):
                _compose_substitute(arg, env, arg_origin, locate, found, missing)
        elif op in (":+", "+"):
            if _present(env, name, empty_counts=op == ":+"):
                _compose_substitute(arg, env, arg_origin, locate, found, missing)


def _service_locator(path_label: str, text: str):
    """Map a character offset to `file:line (service)` using the YAML's indentation."""
    line_starts = [0]
    owners: list[str] = []
    top = ""
    child = ""
    child_indent = -1
    for line in text.split("\n"):
        stripped = line.lstrip(" ")
        indent = len(line) - len(stripped)
        key = stripped.split(":", 1)[0].strip() if ":" in stripped else ""
        if stripped and not stripped.startswith("#"):
            if indent == 0 and key:
                top, child, child_indent = key, "", -1
            elif key and (child_indent < 0 or indent <= child_indent) and indent > 0:
                child, child_indent = key, indent
        owners.append(f"{top}.{child}" if top == "services" and child else top)
        line_starts.append(line_starts[-1] + len(line) + 1)

    def locate(offset: int) -> str:
        lo, hi = 0, len(line_starts) - 1
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if line_starts[mid] <= offset:
                lo = mid
            else:
                hi = mid - 1
        owner = owners[lo] if lo < len(owners) else ""
        owner = owner.split(".", 1)[1] if owner.startswith("services.") else owner
        return f"{path_label}:{lo + 1}" + (f" ({owner})" if owner else "")

    return locate


def load_compose_env_file(path: Path) -> dict[str, str]:
    """Read a Compose `.env` file: `KEY=VALUE`, optional `export`, quotes, inline ` #` comments."""
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if line.startswith("export "):
            line = line[len("export ") :].lstrip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if value[:1] in {"'", '"'} and value.find(value[0], 1) > 0:
            value = value[1 : value.find(value[0], 1)]
        else:
            hash_at = value.find(" #")
            value = (value[:hash_at] if hash_at >= 0 else value).rstrip()
        if _COMPOSE_NAME.fullmatch(key):
            values[key] = value
    return values


def scan_compose_required(
    compose_files: list[Path], env: dict[str, str], root: Path | None = None
) -> tuple[list[RequiredVar], list[RequiredVar]]:
    """Return (every required reference, the ones with no value) across ``compose_files``."""
    found: list[RequiredVar] = []
    missing: list[RequiredVar] = []
    for path in compose_files:
        try:
            label = str(path.resolve().relative_to(root.resolve())) if root else str(path)
        except ValueError:
            label = str(path)
        text = strip_compose_comments(path.read_text(encoding="utf-8", errors="replace"))
        _compose_substitute(text, env, 0, _service_locator(label, text), found, missing)
    return found, missing


def check_compose_required_vars(
    root: Path,
    checks: list[Check],
    compose_files: list[str],
    env_file: str = "",
    environ: dict[str, str] | None = None,
) -> None:
    paths = [p if p.is_absolute() else root / p for p in (Path(f) for f in compose_files)]
    absent = [str(p) for p in paths if not p.is_file()]
    if absent:
        add(checks, "compose-required-vars", "fail", "compose file not found", {"absent": absent})
        return
    env_path = Path(env_file) if env_file else root / ".env"
    if not env_path.is_absolute():
        env_path = root / env_path
    # Compose's precedence: the shell environment, then the env file (a shell value wins even
    # when empty). Only names and emptiness are compared below.
    env = load_compose_env_file(env_path)
    env.update(os.environ if environ is None else environ)
    found, missing = scan_compose_required(paths, env, root)
    rules: dict[str, str] = {}
    messages: dict[str, str] = {}
    locations: dict[str, list[str]] = {}
    for req in missing:
        if rules.get(req.name) != "unset-or-empty":
            rules[req.name] = req.rule
        messages.setdefault(req.name, req.message)
        locations.setdefault(req.name, []).append(req.location)
    report = [
        {"name": n, "rule": rules[n], "message": messages[n], "locations": locations[n]}
        for n in sorted(locations)
    ]
    lines = []
    for n in sorted(locations):
        need = "must be non-empty" if rules[n] == "unset-or-empty" else "may be empty"
        more = f" (+{len(locations[n]) - 1} more)" if len(locations[n]) > 1 else ""
        lines.append(f"  {n}  [{need}]  first: {locations[n][0]}{more}")
    add(
        checks,
        "compose-required-vars",
        "fail" if report else "pass",
        (
            f"{len(report)} required variable(s) have no value; Compose would stop at the first"
            if report
            else "every required `${VAR:?}` in these compose files has a value"
        ),
        {
            "compose_files": [
                str(p.relative_to(root)) if p.is_relative_to(root) else str(p) for p in paths
            ],
            "env_file": str(env_path),
            "env_file_found": env_path.is_file(),
            "required_names": len({r.name for r in found}),
            "missing_names": [item["name"] for item in report],
            "missing": report,
            "report_lines": lines,
        },
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
        "docker compose config passed"
        if code == 0
        else (
            "docker compose config failed (it stops at the first missing variable; "
            "`--mode compose-vars` lists them all)"
        ),
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
            report_lines = c.detail.get("report_lines")
            hidden = (
                {"report_lines", "missing", "missing_names"}
                if isinstance(report_lines, list)
                else set()
            )
            compact = {
                k: v for k, v in c.detail.items() if k not in hidden and v not in (None, {}, [], "")
            }
            if compact:
                lines.append("  " + json.dumps(compact, ensure_ascii=False, sort_keys=True)[:1000])
            if isinstance(report_lines, list):
                lines.extend(str(line) for line in report_lines)
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="SAHOOL runtime bootstrap/environment doctor")
    parser.add_argument("--root", default=".")
    parser.add_argument("--base-url", default=os.environ.get("BASE_URL", "http://localhost"))
    parser.add_argument(
        "--mode",
        choices=["preflight", "runtime", "full", "compose-vars"],
        default="preflight",
        help="compose-vars: report every required `${VAR:?}` with no value, then stop",
    )
    parser.add_argument(
        "-f",
        "--compose-file",
        action="append",
        default=[],
        help="compose file for --mode compose-vars (repeatable; default docker-compose.v9.yml)",
    )
    parser.add_argument(
        "--env-file",
        default="",
        help="env file for --mode compose-vars (default <root>/.env, as Compose reads it)",
    )
    parser.add_argument("--format", choices=["text", "json"], default="text")
    parser.add_argument("--output", default="")
    parser.add_argument("--fail-on-warn", action="store_true")
    args = parser.parse_args()

    root = find_root(Path(args.root))
    checks: list[Check] = []
    if args.mode == "compose-vars":
        check_compose_required_vars(
            root, checks, args.compose_file or ["docker-compose.v9.yml"], args.env_file
        )
        return emit(args, checks)
    check_required_files(root, checks)
    check_env(root, checks)
    check_minio_images(root, checks)
    check_migrations(root, checks)
    check_compose_static(root, checks)
    check_compose_config(root, checks)
    check_ports(checks)
    if args.mode in {"runtime", "full"}:
        check_http_runtime(checks, args.base_url)
    if args.mode == "full":
        check_static_gates(root, checks)
    return emit(args, checks)


def emit(args: argparse.Namespace, checks: list[Check]) -> int:
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

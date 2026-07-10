#!/usr/bin/env python3
"""Docker build matrix verifier for Sahool services.

This script is intentionally evidence-producing, not evidence-fabricating.
It only writes verified build/health/security evidence for phases that actually run.

Typical usage:
  python scripts/ci/docker_build_matrix_verifier.py \
      --services raster-service weather-service edge-inference sam2-inference \
      --write

  python scripts/ci/docker_build_matrix_verifier.py --all --write
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE_DIR = ROOT / "certification" / "evidence"
DEFAULT_COMPOSE_FILE = ROOT / "docker-compose.v9.yml"

# The edge service currently uses an ARM64-specific Dockerfile name in this repository.
DOCKERFILE_OVERRIDES: dict[str, str] = {
    "edge-inference": "services/edge-inference/Dockerfile.arm64",
}

# Internal ports reflect current Dockerfiles, not generic examples.
SERVICE_CONFIG: dict[str, dict[str, Any]] = {
    "raster-service": {
        "dockerfile": "services/raster-service/Dockerfile",
        "internal_port": 8001,
        "health_path": "/healthz",
        "readyz_path": "/readyz",
        "env": {"RASTER_RUNTIME_MODE": "ci", "FIELD_DEM_PATH": ""},
        "required_files": [
            "/app/main.py",
            "/app/raw_data_processing.py",
            "/app/raster_pixel_processing.py",
            "/app/raster_cloud_mask_strategies.py",
            "/app/raster_validated_product.py",
            "/app/raster_topographic_qa.py",
        ],
    },
    "weather-service": {
        "dockerfile": "services/weather-service/Dockerfile",
        "internal_port": 8000,
        "health_path": "/healthz",
        "readyz_path": "/readyz",
        "env": {"WEATHER_REDIS_URL": "", "WEATHER_CACHE_BACKEND": "memory"},
        "required_files": [
            "/app/main.py",
            "/app/weather_runtime.py",
            "/app/raw_weather_processing.py",
            "/app/open_meteo.py",
            "/app/cache.py",
        ],
    },
    "edge-inference": {
        "dockerfile": "services/edge-inference/Dockerfile.arm64",
        "internal_port": 8100,
        "health_path": "/healthz",
        "readyz_path": "/readyz",
        "env": {
            "EDGE_PRODUCTION_REQUIRED": "true",
            "EDGE_READINESS_MODE": "strict",
            "EDGE_MODEL_DIR": "/models",
        },
        "required_files": [
            "/app/main.py",
            "/app/models_manifest/edge_models.required.json",
        ],
        "model_required_for_ready": True,
    },
    "sam2-inference": {
        "dockerfile": "services/sam2-inference/Dockerfile",
        "internal_port": 8080,
        "health_path": "/healthz",
        "readyz_path": "/readyz",
        "env": {
            "SAM2_PRODUCTION_REQUIRED": "true",
            "SAM2_READINESS_MODE": "strict",
            "SAM2_MODEL_DIR": "/models/sam2",
        },
        "required_files": ["/app/main.py", "/app/sam2_runtime.py"],
        "model_required_for_ready": True,
    },
    "auth": {
        "dockerfile": "services/auth/Dockerfile",
        "internal_port": 8000,
        "health_path": "/healthz",
        "readyz_path": "/readyz",
        "env": {"JWT_PRIVATE_KEY_PATH": "/app/keys/jwt.pem"},
        "required_files": [
            "/app/main.py",
            "/app/mfa_runtime.py",
            "/app/routers/mfa.py",
        ],
    },
    "sahool-platform": {
        "dockerfile": "services/sahool-platform/Dockerfile",
        "internal_port": 8000,
        "health_path": "/healthz",
        "readyz_path": "/readyz",
        "env": {
            "DATABASE_URL": "postgresql://platform:platform@postgres:5432/platform",
            "REDIS_URL": "redis://redis:6379/0",
            "NATS_URL": "nats://nats:4222",
        },
        "required_files": ["/app/api/main.py", "/app/api/routers"],
    },
    "odoo-bridge": {
        "dockerfile": "services/odoo-bridge/Dockerfile",
        "internal_port": 8126,
        "health_path": "/healthz",
        "readyz_path": "/readyz",
        "env": {
            "ODOO_URL": "http://odoo:8069",
            "ODOO_DB": "production",
            "ODOO_API_KEY": "dummy",
        },
        "required_files": ["/app/main.py", "/app/erp_runtime.py"],
    },
}

CRITICAL_SERVICES = [
    "raster-service",
    "weather-service",
    "edge-inference",
    "sam2-inference",
]
EXTENDED_SERVICES = CRITICAL_SERVICES + ["auth", "sahool-platform", "odoo-bridge"]


@dataclass
class BuildResult:
    service: str
    dockerfile: str | None
    build_status: str  # pass | fail | skipped
    build_time_sec: float
    image_size_mb: float | None
    image_size_raw: str | None
    layers: int | None
    error: str | None = None


@dataclass
class FileCheckResult:
    service: str
    status: str  # pass | fail | skipped
    missing_files: list[str]
    error: str | None = None


@dataclass
class HealthResult:
    service: str
    status: str  # pass | fail | skipped
    health_http_status: int | None
    readyz_status: str | None
    response_time_ms: float | None
    error: str | None = None


@dataclass
class SecurityResult:
    service: str
    status: str  # pass | fail | skipped
    critical_count: int
    high_count: int
    medium_count: int
    report_path: str | None
    error: str | None = None


@dataclass
class ComposeResult:
    status: str  # pass | fail | skipped
    compose_file: str | None
    all_services_up: bool
    cross_service_connectivity: bool
    errors: list[str]


def run_command(
    cmd: list[str], *, cwd: Path | None = None, timeout: int = 300
) -> tuple[int, str, str]:
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd or ROOT,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", f"Command timed out after {timeout}s: {' '.join(cmd)}"
    except Exception as exc:  # pragma: no cover - defensive shell boundary
        return -1, "", str(exc)


def discover_services() -> list[str]:
    services: set[str] = set()
    for dockerfile in (ROOT / "services").glob("*/Dockerfile"):
        services.add(dockerfile.parent.name)
    for service, dockerfile in DOCKERFILE_OVERRIDES.items():
        if (ROOT / dockerfile).exists():
            services.add(service)
    return sorted(services)


def dockerfile_for(service: str) -> Path | None:
    configured = SERVICE_CONFIG.get(service, {}).get("dockerfile") or DOCKERFILE_OVERRIDES.get(
        service
    )
    if configured:
        candidate = ROOT / configured
        return candidate if candidate.exists() else candidate
    candidate = ROOT / "services" / service / "Dockerfile"
    if candidate.exists():
        return candidate
    return None


def internal_port_for(service: str) -> int:
    config = SERVICE_CONFIG.get(service, {})
    if "internal_port" in config:
        return int(config["internal_port"])
    dockerfile = dockerfile_for(service)
    if dockerfile and dockerfile.exists():
        text = dockerfile.read_text(encoding="utf-8", errors="ignore")
        match = re.search(r"^EXPOSE\s+(\d+)", text, flags=re.MULTILINE)
        if match:
            return int(match.group(1))
    return 8000


def image_ref(service: str) -> str:
    return f"sahool/{service}:ci"


def parse_image_size(raw: str) -> float | None:
    raw = raw.strip()
    if not raw:
        return None
    try:
        if raw.endswith("GB"):
            return float(raw[:-2]) * 1024.0
        if raw.endswith("MB"):
            return float(raw[:-2])
        if raw.endswith("kB"):
            return float(raw[:-2]) / 1024.0
        if raw.endswith("B"):
            return float(raw[:-1]) / (1024.0 * 1024.0)
    except ValueError:
        return None
    return None


def get_image_metadata(service: str) -> tuple[float | None, str | None, int | None]:
    rc, stdout, _ = run_command(
        ["docker", "images", image_ref(service), "--format", "{{.Size}}"], timeout=30
    )
    size_raw = stdout.strip() if rc == 0 and stdout.strip() else None
    size_mb = parse_image_size(size_raw or "")
    rc, stdout, _ = run_command(
        ["docker", "history", image_ref(service), "--format", "{{.ID}}"], timeout=30
    )
    layers = len([line for line in stdout.splitlines() if line.strip()]) if rc == 0 else None
    return size_mb, size_raw, layers


def build_service(service: str) -> BuildResult:
    dockerfile = dockerfile_for(service)
    if dockerfile is None or not dockerfile.exists():
        return BuildResult(
            service,
            str(dockerfile) if dockerfile else None,
            "skipped",
            0.0,
            None,
            None,
            None,
            "Dockerfile not found",
        )
    start = time.time()
    rc, _, stderr = run_command(
        ["docker", "build", "-f", str(dockerfile.relative_to(ROOT)), "-t", image_ref(service), "."],
        timeout=900,
    )
    elapsed = time.time() - start
    if rc != 0:
        return BuildResult(
            service,
            str(dockerfile.relative_to(ROOT)),
            "fail",
            elapsed,
            None,
            None,
            None,
            stderr[-1200:],
        )
    size_mb, size_raw, layers = get_image_metadata(service)
    return BuildResult(
        service, str(dockerfile.relative_to(ROOT)), "pass", elapsed, size_mb, size_raw, layers
    )


def check_required_files(service: str) -> FileCheckResult:
    required = SERVICE_CONFIG.get(service, {}).get("required_files", [])
    if not required:
        return FileCheckResult(service, "skipped", [])
    script = " && ".join(f"test -e {path}" for path in required)
    rc, _, stderr = run_command(
        ["docker", "run", "--rm", "--entrypoint", "sh", image_ref(service), "-c", script],
        timeout=120,
    )
    if rc == 0:
        return FileCheckResult(service, "pass", [])
    missing = []
    for path in required:
        rc_one, _, _ = run_command(
            [
                "docker",
                "run",
                "--rm",
                "--entrypoint",
                "sh",
                image_ref(service),
                "-c",
                f"test -e {path}",
            ],
            timeout=60,
        )
        if rc_one != 0:
            missing.append(path)
    return FileCheckResult(service, "fail", missing, stderr[-500:])


def healthcheck_service(service: str, host_port: int) -> HealthResult:
    config = SERVICE_CONFIG.get(service, {})
    internal_port = internal_port_for(service)
    container = f"sahool-{service.replace('_', '-').replace('/', '-')}-ci"
    run_command(["docker", "rm", "-f", container], timeout=30)

    cmd = ["docker", "run", "--rm", "-d", "--name", container, "-p", f"{host_port}:{internal_port}"]
    for key, value in config.get("env", {}).items():
        cmd.extend(["-e", f"{key}={value}"])
    cmd.append(image_ref(service))

    rc, _, stderr = run_command(cmd, timeout=120)
    if rc != 0:
        return HealthResult(
            service, "fail", None, None, None, f"container start failed: {stderr[-800:]}"
        )

    health_path = config.get("health_path", "/healthz")
    readyz_path = config.get("readyz_path", "/readyz")
    start = time.time()
    health_rc = -1
    health_out = ""
    health_err = ""
    for _ in range(30):
        health_rc, health_out, health_err = run_command(
            ["curl", "-fsS", f"http://localhost:{host_port}{health_path}"], timeout=8
        )
        if health_rc == 0:
            break
        time.sleep(2)
    response_ms = (time.time() - start) * 1000.0

    readyz_status = "skipped"
    readyz_rc, _, _ = run_command(
        ["curl", "-fsS", f"http://localhost:{host_port}{readyz_path}"], timeout=8
    )
    if readyz_rc == 0:
        readyz_status = "pass"
    else:
        readyz_status = "degraded_or_unavailable"

    logs_rc, logs_out, _ = run_command(["docker", "logs", container, "--tail", "200"], timeout=30)
    run_command(["docker", "stop", container], timeout=60)

    if health_rc != 0:
        return HealthResult(
            service,
            "fail",
            None,
            readyz_status,
            response_ms,
            f"healthz failed: {health_err[-500:]} {health_out[-500:]}",
        )
    if logs_rc == 0 and re.search(r"ModuleNotFoundError|ImportError|Traceback", logs_out):
        return HealthResult(
            service,
            "fail",
            200,
            readyz_status,
            response_ms,
            "startup logs contain import error or traceback",
        )
    return HealthResult(service, "pass", 200, readyz_status, response_ms)


def trivy_scan(service: str) -> SecurityResult:
    rc, _, _ = run_command(["which", "trivy"], timeout=20)
    if rc != 0:
        return SecurityResult(service, "skipped", 0, 0, 0, None, "trivy not installed")
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    report = EVIDENCE_DIR / f"trivy-{service}.json"
    rc, _, stderr = run_command(
        ["trivy", "image", "--format", "json", "--output", str(report), image_ref(service)],
        timeout=600,
    )
    if rc != 0:
        return SecurityResult(service, "fail", 0, 0, 0, None, stderr[-800:])
    try:
        data = json.loads(report.read_text(encoding="utf-8"))
    except Exception as exc:
        return SecurityResult(service, "fail", 0, 0, 0, None, f"failed to parse trivy json: {exc}")
    counts = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0}
    for result in data.get("Results", []):
        for vuln in result.get("Vulnerabilities", []) or []:
            sev = str(vuln.get("Severity", "")).upper()
            if sev in counts:
                counts[sev] += 1
    status = "pass" if counts["CRITICAL"] == 0 else "fail"
    return SecurityResult(
        service,
        status,
        counts["CRITICAL"],
        counts["HIGH"],
        counts["MEDIUM"],
        str(report.relative_to(ROOT)),
    )


def compose_check(compose_file: Path) -> ComposeResult:
    if not compose_file.exists():
        return ComposeResult("skipped", str(compose_file), False, False, ["compose file not found"])
    rc, _, stderr = run_command(
        ["docker", "compose", "-f", str(compose_file), "config"], timeout=120
    )
    if rc != 0:
        return ComposeResult(
            "fail", str(compose_file.relative_to(ROOT)), False, False, [stderr[-1000:]]
        )
    return ComposeResult("pass", str(compose_file.relative_to(ROOT)), True, False, [])


def build_evidence(
    *,
    services: list[str],
    builds: list[BuildResult],
    file_checks: list[FileCheckResult],
    health: list[HealthResult],
    security: list[SecurityResult],
    compose: ComposeResult,
    phases_run: dict[str, bool],
) -> dict[str, Any]:
    build_map = {item.service: asdict(item) for item in builds}
    file_map = {item.service: asdict(item) for item in file_checks}
    health_map = {item.service: asdict(item) for item in health}
    security_map = {item.service: asdict(item) for item in security}

    build_pass = (
        all(item.build_status == "pass" for item in builds) if phases_run.get("build") else False
    )
    files_pass = (
        all(item.status in {"pass", "skipped"} for item in file_checks)
        if phases_run.get("file_check")
        else False
    )
    health_pass = (
        all(item.status == "pass" for item in health) if phases_run.get("health") else False
    )
    security_pass = (
        all(item.status in {"pass", "skipped"} and item.critical_count == 0 for item in security)
        if phases_run.get("security")
        else True
    )
    compose_pass = compose.status in {"pass", "skipped"}
    verified = build_pass and files_pass and health_pass and security_pass and compose_pass

    return {
        "schema_version": 3,
        "status": "verified" if verified else "not_verified",
        "production_certified": False,
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "services": services,
        "phases_run": phases_run,
        "summary": {
            "service_count": len(services),
            "built": sum(1 for item in builds if item.build_status == "pass"),
            "build_failed": sum(1 for item in builds if item.build_status == "fail"),
            "health_passed": sum(1 for item in health if item.status == "pass"),
            "health_failed": sum(1 for item in health if item.status == "fail"),
            "critical_vulnerabilities": sum(item.critical_count for item in security),
            "compose_status": compose.status,
        },
        "build": build_map,
        "required_files": file_map,
        "health": health_map,
        "security": security_map,
        "compose": asdict(compose),
        "pcert_mapping": {
            "P-CERT-1": "Docker build matrix evidence produced only when build/file/health phases pass.",
            "P-CERT-3": "Redis live integration remains separate unless WEATHER_REDIS_INTEGRATION_URL test is run.",
            "P-CERT-4": "Model readiness requires strict edge/SAM2 artifact-present smoke, not just /healthz.",
        },
    }


def write_evidence(evidence: dict[str, Any]) -> None:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    matrix_path = EVIDENCE_DIR / "docker_build_matrix_full.json"
    matrix_path.write_text(json.dumps(evidence, indent=2, ensure_ascii=False), encoding="utf-8")

    ci_summary = {
        "status": evidence["status"],
        "production_certified": False,
        "jobs": evidence["summary"],
        "timestamp_utc": evidence["timestamp_utc"],
    }
    (EVIDENCE_DIR / "ci_summary.json").write_text(
        json.dumps(ci_summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    model_services = {
        key: evidence["health"].get(key, {}) for key in ("edge-inference", "sam2-inference")
    }
    model_summary = {
        "status": "not_verified",
        "reason": "artifact-present strict readiness must be run separately and cannot be inferred from /healthz",
        "services": model_services,
        "timestamp_utc": evidence["timestamp_utc"],
    }
    (EVIDENCE_DIR / "model_provisioning_summary.json").write_text(
        json.dumps(model_summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Docker build matrix verifier for Sahool services")
    parser.add_argument("--services", nargs="*", help="Explicit service names to verify")
    parser.add_argument("--critical", action="store_true", help="Verify the four critical services")
    parser.add_argument(
        "--extended", action="store_true", help="Verify critical services plus auth/platform/odoo"
    )
    parser.add_argument(
        "--all", action="store_true", help="Verify all discovered Dockerfile-backed services"
    )
    parser.add_argument("--skip-build", action="store_true")
    parser.add_argument("--skip-health", action="store_true")
    parser.add_argument("--skip-files", action="store_true")
    parser.add_argument("--skip-security", action="store_true")
    parser.add_argument("--compose-file", default=str(DEFAULT_COMPOSE_FILE.relative_to(ROOT)))
    parser.add_argument("--skip-compose", action="store_true")
    parser.add_argument("--write", action="store_true", help="Write evidence JSON files")
    parser.add_argument("--host-port-base", type=int, default=18000)
    return parser.parse_args()


def selected_services(args: argparse.Namespace) -> list[str]:
    if args.all:
        return discover_services()
    if args.extended:
        return EXTENDED_SERVICES
    if args.critical:
        return CRITICAL_SERVICES
    if args.services:
        return args.services
    return CRITICAL_SERVICES


def main() -> int:
    args = parse_args()
    services = selected_services(args)
    unknown = [
        svc for svc in services if dockerfile_for(svc) is None or not dockerfile_for(svc).exists()
    ]
    if unknown:
        print(f"Unknown or Dockerfile-less services: {', '.join(unknown)}", file=sys.stderr)
        return 2

    builds: list[BuildResult] = []
    file_checks: list[FileCheckResult] = []
    health: list[HealthResult] = []
    security: list[SecurityResult] = []

    phases_run = {
        "build": not args.skip_build,
        "file_check": not args.skip_files,
        "health": not args.skip_health,
        "security": not args.skip_security,
        "compose_config": not args.skip_compose,
    }

    print(f"Services: {', '.join(services)}")

    if not args.skip_build:
        for svc in services:
            print(f"BUILD {svc}")
            result = build_service(svc)
            print(f"  {result.build_status}: {result.error or result.image_size_raw or ''}")
            builds.append(result)
    else:
        builds = [
            BuildResult(
                svc, str(dockerfile_for(svc).relative_to(ROOT)), "skipped", 0.0, None, None, None
            )
            for svc in services
        ]

    if not args.skip_files:
        for svc in services:
            print(f"FILES {svc}")
            result = check_required_files(svc)
            print(
                f"  {result.status}: {', '.join(result.missing_files) if result.missing_files else ''}"
            )
            file_checks.append(result)
    else:
        file_checks = [FileCheckResult(svc, "skipped", []) for svc in services]

    if not args.skip_health:
        for idx, svc in enumerate(services):
            host_port = args.host_port_base + idx
            print(f"HEALTH {svc} on localhost:{host_port}")
            result = healthcheck_service(svc, host_port)
            print(f"  {result.status}: readyz={result.readyz_status} {result.error or ''}")
            health.append(result)
    else:
        health = [HealthResult(svc, "skipped", None, None, None) for svc in services]

    if not args.skip_security:
        for svc in services:
            print(f"SECURITY {svc}")
            result = trivy_scan(svc)
            print(
                f"  {result.status}: C={result.critical_count} H={result.high_count} M={result.medium_count}"
            )
            security.append(result)
    else:
        security = [
            SecurityResult(svc, "skipped", 0, 0, 0, None, "skipped by user") for svc in services
        ]

    compose = ComposeResult("skipped", None, False, False, ["skipped by user"])
    if not args.skip_compose:
        compose = compose_check(ROOT / args.compose_file)
        print(f"COMPOSE {compose.status}: {compose.errors}")

    evidence = build_evidence(
        services=services,
        builds=builds,
        file_checks=file_checks,
        health=health,
        security=security,
        compose=compose,
        phases_run=phases_run,
    )

    if args.write:
        write_evidence(evidence)
        print(f"Evidence written to {EVIDENCE_DIR.relative_to(ROOT)}")

    print(json.dumps(evidence["summary"], indent=2, ensure_ascii=False))
    return 0 if evidence["status"] == "verified" else 1


if __name__ == "__main__":
    raise SystemExit(main())

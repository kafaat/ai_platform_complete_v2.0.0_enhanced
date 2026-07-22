#!/usr/bin/env python3
"""Fail closed on MinIO/S3 credential drift in docker-compose/.env templates.

The local incident this gate prevents:
- MinIO container was hardcoded with MINIO_ROOT_USER=sahool-admin.
- .env advertised MINIO_ROOT_USER=sahool and MINIO_ACCESS_KEY=${MINIO_ROOT_USER}.
- Network/health passed, but any backend using .env S3 credentials would fail auth.

This static gate keeps the credential source-of-truth explicit and aligned.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMPOSE = ROOT / "docker-compose.v9.yml"
ENV_EXAMPLE = ROOT / ".env.example"


def fail(msg: str) -> None:
    print(f"❌ {msg}")
    sys.exit(1)


def load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def main() -> int:
    if not COMPOSE.exists():
        fail("docker-compose.v9.yml is missing")
    if not ENV_EXAMPLE.exists():
        fail(".env.example is missing")

    compose = COMPOSE.read_text(encoding="utf-8", errors="replace")
    env = load_env(ENV_EXAMPLE)

    # MinIO root user must be interpolated from env, not hardcoded to a value that
    # can diverge from MINIO_ACCESS_KEY/S3_ACCESS_KEY.
    for line in compose.splitlines():
        stripped = line.strip()
        if stripped.startswith("MINIO_ROOT_USER:"):
            value = stripped.split(":", 1)[1].strip()
            if not value.startswith("${MINIO_ROOT_USER"):
                fail(
                    "docker-compose.v9.yml must not hardcode MINIO_ROOT_USER; use ${MINIO_ROOT_USER:-...}"
                )

    root = env.get("MINIO_ROOT_USER", "")
    access = env.get("MINIO_ACCESS_KEY", "")
    s3_access = env.get("S3_ACCESS_KEY", "")
    if not root:
        fail(".env.example must define MINIO_ROOT_USER")
    if access not in {"${MINIO_ROOT_USER}", root}:
        fail(
            "MINIO_ACCESS_KEY must resolve from MINIO_ROOT_USER unless a dedicated documented service account is used"
        )
    if s3_access and s3_access not in {"${MINIO_ACCESS_KEY}", "${MINIO_ROOT_USER}", root, access}:
        fail(
            "S3_ACCESS_KEY must resolve from MINIO_ACCESS_KEY/MINIO_ROOT_USER in the default template"
        )

    required_env = [
        "S3_ENDPOINT",
        "S3_ENDPOINT_HOST",
        "S3_BUCKET",
        "S3_ACCESS_KEY",
        "S3_SECRET_KEY",
        "S3_REGION",
        "S3_USE_SSL",
        "S3_ALLOW_FILE_FALLBACK",
    ]
    missing = [k for k in required_env if k not in env]
    if missing:
        fail(f".env.example missing S3 contract keys: {', '.join(missing)}")

    required_compose_keys = [
        "S3_ENDPOINT:",
        "S3_BUCKET:",
        "S3_ACCESS_KEY:",
        "S3_SECRET_KEY:",
        "S3_REGION:",
        "S3_USE_SSL:",
        "S3_ALLOW_FILE_FALLBACK:",
    ]
    missing_compose = [k for k in required_compose_keys if k not in compose]
    if missing_compose:
        fail(
            f"docker-compose.v9.yml missing raster S3 environment keys: {', '.join(missing_compose)}"
        )

    for required in (
        "sahool-minio-init:", "deploy/minio/policies", "scripts/minio/provision.sh",
        "SCOUT_INGEST_S3_ACCESS_KEY:", "RASTER_S3_ACCESS_KEY:",
    ):
        if required not in compose:
            fail(f"docker-compose.v9.yml missing MinIO least-privilege provisioning: {required}")
    provision = (ROOT / "scripts/minio/provision.sh").read_text(encoding="utf-8")
    for denial in ("scout/sahool-rasters", "raster/sahool-scout-ingest"):
        if denial not in provision:
            fail(f"MinIO provisioning lacks cross-scope negative check: {denial}")

    # MinIO version pin: the community admin console was gutted in RELEASE.2025-05-24,
    # the repo was archived (2026-04), and later Docker Hub images carry a HIGH CVE and
    # were pulled. This deployment relies on the console (--console-address :9001), so we
    # pin the LAST full-console release and forbid drift/bare hardcodes across compose.
    # Operators may still override via MINIO_IMAGE. See COMPOSE_ENV_CONTRACT report.
    FULL_CONSOLE_PIN = "minio/minio:RELEASE.2025-04-22T22-12-26Z"
    env_pin = env.get("MINIO_IMAGE", "")
    if env_pin != FULL_CONSOLE_PIN:
        fail(
            f".env.example MINIO_IMAGE must pin the last full-console release "
            f"{FULL_CONSOLE_PIN} (got {env_pin!r}); newer community images removed the admin UI"
        )
    for cf in sorted(ROOT.glob("docker-compose*.yml")):
        for raw in cf.read_text(encoding="utf-8", errors="replace").splitlines():
            s = raw.strip()
            if "image:" in s and "minio/minio:" in s:
                # Must use the ${MINIO_IMAGE:-...} override form with the pinned default —
                # a bare hardcode risks shipping a console-stripped / CVE image.
                if "${MINIO_IMAGE" not in s or FULL_CONSOLE_PIN not in s:
                    fail(
                        f"{cf.name}: MinIO image must be ${{MINIO_IMAGE:-{FULL_CONSOLE_PIN}}} "
                        f"(no bare hardcode / no post-console-removal tag) — got: {s}"
                    )

    # TiTiler should be able to inspect local file COGs in dev and S3 COGs in prod.
    if "sahool-titiler:" in compose:
        titiler_block = compose.split("\n  sahool-titiler:", 1)[1].split("\n  sahool-", 1)[0]
        if "raster-data:/data/rasters:ro" not in titiler_block:
            fail(
                "sahool-titiler must mount raster-data read-only for local file:// COG diagnostics"
            )
        if "AWS_S3_ENDPOINT:" not in titiler_block:
            fail("sahool-titiler must receive AWS_S3_ENDPOINT for MinIO/S3 COG diagnostics")

    print("✓ MinIO/S3 credential and storage contract is consistent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Generate a deployment identity manifest from Docker Compose and immutable OCI config."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "runtime-verification/generated/functional_deployment_manifest.json"
SERVICES = {
    "weather-service": "sahool-weather-service",
    "soil-service": "sahool-soil-service",
    "sahool-platform": "sahool-platform",
}
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def run(args: list[str]) -> str:
    return subprocess.run(args, cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()


def inspect(
    compose_args: list[str], compose_service: str, expected_image: str | None = None
) -> dict:
    cid = run(compose_args + ["ps", "-q", compose_service])
    if not cid:
        raise ValueError(f"{compose_service}: running container not found")
    obj = json.loads(run(["docker", "inspect", cid]))[0]
    image_id = str(obj.get("Image") or "")
    labels = (obj.get("Config") or {}).get("Labels") or {}
    repo_digests = list(obj.get("RepoDigests") or [])
    registry_digest = ""
    if expected_image:
        if expected_image not in repo_digests:
            raise ValueError(
                f"{compose_service}: running image does not match attested pull-by-digest reference"
            )
        registry_digest = expected_image.rsplit("@", 1)[1]
    if not DIGEST_RE.fullmatch(image_id):
        raise ValueError(f"{compose_service}: invalid Docker image ID {image_id!r}")
    return {
        "compose_service": compose_service,
        "container_id": cid,
        "service": str(labels.get("io.sahool.service") or ""),
        "git_sha": str(labels.get("org.opencontainers.image.revision") or ""),
        "build_id": str(labels.get("io.sahool.build-id") or ""),
        "image_digest": registry_digest or image_id,
        "docker_config_digest": image_id,
        "registry_reference": expected_image or "",
        "source_repository": str(labels.get("org.opencontainers.image.source") or ""),
        "source_ref": str(labels.get("org.opencontainers.image.ref.name") or ""),
        "identity_source": "docker-inspect-oci-config",
    }


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--tested-sha", required=True)
    p.add_argument("--compose-file", action="append", required=True)
    p.add_argument("--image-manifest")
    p.add_argument("--output", default=str(OUT))
    a = p.parse_args(argv)
    if not SHA_RE.fullmatch(a.tested_sha):
        print("tested SHA must be full 40-char lowercase hex", file=sys.stderr)
        return 1
    compose_args = ["docker", "compose"]
    for f in a.compose_file:
        compose_args += ["-f", f]
    entries = {}
    expected = {}
    if a.image_manifest:
        try:
            im = json.loads(Path(a.image_manifest).read_text())
            if im.get("source_sha") != a.tested_sha:
                raise ValueError("attested image manifest SHA mismatch")
            expected = {k: v.get("image", "") for k, v in im.get("images", {}).items()}
        except Exception as ex:
            print(f"image manifest invalid: {ex}", file=sys.stderr)
            return 1
    try:
        for service, compose_service in SERVICES.items():
            x = inspect(compose_args, compose_service, expected.get(service))
            if x["service"] != service or x["git_sha"] != a.tested_sha or not x["build_id"]:
                raise ValueError(f"{service}: immutable OCI identity mismatch")
            entries[service] = x
    except (subprocess.CalledProcessError, ValueError, json.JSONDecodeError) as ex:
        print(f"deployment manifest generation failed: {ex}", file=sys.stderr)
        return 1
    out = Path(a.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    body = {
        "schema_version": "1.0",
        "tested_sha": a.tested_sha,
        "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "services": entries,
    }
    out.write_text(json.dumps(body, sort_keys=True, indent=2) + "\n")
    print(
        f"deployment_manifest_ok services={len(entries)} sha256={hashlib.sha256(out.read_bytes()).hexdigest()} path={out}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Accept a built Vegetation image, not an import from the source checkout.

Only the Raster fixture script is mounted into its own container. The application
has no source bind mounts and uses the Dockerfile CMD/user. Expected imports and
HTTP methods come from the independently reviewed host contract. No cloud access.
The receipt records a local Docker image ID; it is NOT a registry manifest digest
or a production deployment approval.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import time
import urllib.error
import urllib.request
import uuid
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
WEEKLY = "/v1/reports/weekly-field-insights"


def docker(*args, check=True):
    return subprocess.run(
        ["docker", *args], check=check, capture_output=True, text=True, timeout=120
    )


def get(base, path):
    try:
        with urllib.request.urlopen(base + path, timeout=5) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as exc:
        return exc.code, json.load(exc)


def check_routes(schema, expected):
    missing = [
        f"{method.upper()} {path}"
        for path, methods in expected.items()
        for method in methods
        if method not in schema.get("paths", {}).get(path, {})
    ]
    if missing:
        raise AssertionError(f"Missing externally expected routes: {missing}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expect-missing-weekly", action="store_true")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    contract = json.loads((HERE / "vegetation_smoke_contract.json").read_text())
    suffix = uuid.uuid4().hex[:12]
    network, raster, app = (
        f"vegetation-smoke-{kind}-{suffix}" for kind in ("net", "raster", "app")
    )
    receipt = {
        "started_at": datetime.now(UTC).isoformat(),
        "accepted": False,
        "mutation": args.expect_missing_weekly,
        "contract_version": contract["version"],
        "scope": "isolated_container_fixture_not_deployment",
    }
    try:
        # Resolve once, then run both fixture and app by immutable LOCAL image ID.
        image_id = docker("image", "inspect", "--format", "{{.Id}}", args.image).stdout.strip()
        receipt["local_image_id"] = image_id
        public_key = docker(
            "run",
            "--rm",
            "--network",
            "none",
            "--entrypoint",
            "python",
            image_id,
            "-c",
            "from cryptography.hazmat.primitives.asymmetric import rsa; "
            "from cryptography.hazmat.primitives import serialization as s; "
            "print(rsa.generate_private_key(public_exponent=65537,key_size=2048)"
            ".public_key().public_bytes(s.Encoding.PEM,s.PublicFormat.SubjectPublicKeyInfo).decode())",
        ).stdout.strip()
        docker("network", "create", "--internal", network)
        docker(
            "run",
            "-d",
            "--name",
            raster,
            "--network",
            network,
            "--network-alias",
            "raster",
            "--mount",
            f"type=bind,source={HERE / 'vegetation_smoke_raster.py'},target=/fixture.py,readonly",
            "--entrypoint",
            "python",
            image_id,
            "/fixture.py",
        )
        docker(
            "run",
            "-d",
            "--name",
            app,
            "--network",
            network,
            "-p",
            "127.0.0.1::8000",
            "-e",
            "SAHOOL_ENV=production",
            "-e",
            "VEGETATION_REAL_ONLY=1",
            "-e",
            "VEGETATION_PREFER_RASTER=1",
            "-e",
            "RASTER_SERVICE_URL=http://raster:8001",
            "-e",
            "SAHOOL_AGENT_TOKEN=disposable-smoke-raster-token",
            "-e",
            "FIELD_SERVICE_TENANT_ASSERTION_KEY=disposable-smoke-assertion-key-000000000",
            "-e",
            f"JWT_PUBLIC_KEY={public_key}",
            image_id,
        )
        address = docker("port", app, "8000/tcp").stdout.strip()
        base = f"http://{address}"
        deadline = time.monotonic() + 60
        while True:
            try:
                status, _ = get(base, "/healthz")
                if status == 200:
                    break
            except (OSError, ValueError):
                pass
            if time.monotonic() >= deadline:
                raise AssertionError("Container did not become live in 60 seconds")
            time.sleep(0.5)
        receipt["healthz"] = status
        status, schema = get(base, "/openapi.json")
        assert status == 200
        ready_status, ready = get(base, "/readyz")
        receipt["initial_readiness"] = {"status": ready_status, "body": ready}
        if args.expect_missing_weekly:
            # Do not count an arbitrary Docker/build/network failure as a killed mutation.
            assert ready_status == 503
            assert ready["router_import_failures"] == {"insights": "ModuleNotFoundError"}
            assert ready["dependencies"]["raster_service"] == "ready"
            assert WEEKLY not in schema["paths"]
            check_routes(schema, {p: m for p, m in contract["routes"].items() if p != WEEKLY})
            receipt["mutation_detected"] = "weekly_module_missing_but_build_and_liveness_succeed"
        else:
            check_routes(schema, contract["routes"])
            imports = docker(
                "exec",
                app,
                "python",
                "-c",
                "import importlib,json,main; "
                f"[importlib.import_module(m) for m in {contract['imports']!r}]; "
                "assert not main.app.state.router_import_failures; print('imports_ok')",
            )
            assert imports.stdout.strip().endswith("imports_ok")
            assert ready_status == 200 and ready["ready"]
            assert ready["runtime_mode"] == "authoritative-raster-only"
            docker("exec", raster, "touch", "/tmp/raster-unready")
            status, body = get(base, "/readyz")
            assert status == 503 and not body["ready"]
            assert body["dependencies"]["raster_service"] == "http_503"
            assert get(base, "/healthz")[0] == 200
            receipt["raster_outage_readiness"] = status
            docker("exec", raster, "rm", "/tmp/raster-unready")
            status, body = get(base, "/readyz")
            assert status == 200 and body["ready"]
            receipt["raster_recovery_readiness"] = status
            receipt["imports_checked"] = contract["imports"]
            receipt["route_methods_checked"] = sum(map(len, contract["routes"].values()))
        receipt["accepted"] = True
    finally:
        for name in (app, raster):
            logs = docker("logs", name, check=False)
            (args.output / f"{name}.log").write_text(logs.stdout + logs.stderr)
            if not receipt["accepted"]:
                print(logs.stdout + logs.stderr)
            docker("rm", "-f", name, check=False)
        docker("network", "rm", network, check=False)
        receipt["finished_at"] = datetime.now(UTC).isoformat()
        (args.output / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()

"""Legacy TiTiler entry gate: GDAL's S3 variables come only from the shared endpoint decision.

TITILER-LEGACY-S3-BYPASSES-ENDPOINT-POLICY-01. No network; the exec path runs a real
child interpreter through the gate.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "shared/storage/gdal_s3_env_gate.py"


def _gate():
    spec = importlib.util.spec_from_file_location("sahool_gdal_s3_env_gate_under_test", GATE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    ("environ", "expected"),
    [
        (
            {"S3_ENDPOINT": "https://objects.example.test", "S3_USE_SSL": ""},
            {
                "AWS_S3_ENDPOINT": "objects.example.test",
                "AWS_HTTPS": "YES",
                "AWS_VIRTUAL_HOSTING": "FALSE",
            },
        ),
        (
            {"S3_ENDPOINT": "objects.example.test:8443"},
            {
                "AWS_S3_ENDPOINT": "objects.example.test:8443",
                "AWS_HTTPS": "YES",
                "AWS_VIRTUAL_HOSTING": "FALSE",
            },
        ),
        (
            {
                "S3_ENDPOINT": "http://sahool-minio:9000",
                "S3_ALLOW_PLAINTEXT_INTERNAL": "true",
            },
            {
                "AWS_S3_ENDPOINT": "sahool-minio:9000",
                "AWS_HTTPS": "NO",
                "AWS_VIRTUAL_HOSTING": "FALSE",
            },
        ),
        ({"S3_ENDPOINT": ""}, {}),
    ],
)
def test_gate_derives_gdal_env_from_the_shared_decision(environ, expected):
    assert _gate().derive_gdal_env(environ) == expected


@pytest.mark.parametrize(
    ("environ", "code"),
    [
        # The old Compose wiring's hole: an external host with S3_USE_SSL=false.
        (
            {"S3_ENDPOINT": "http://objects.example.test", "S3_USE_SSL": "false"},
            "plaintext_external_forbidden",
        ),
        ({"S3_ENDPOINT": "http://sahool-minio:9000"}, "plaintext_internal_requires_opt_in"),
        (
            {"S3_ENDPOINT": "https://objects.example.test", "S3_USE_SSL": "false"},
            "scheme_flag_conflict",
        ),
        (
            {"S3_ENDPOINT": "https://rasters.objects.example.test", "S3_BUCKET": "rasters"},
            "bucket_prefixed_endpoint_forbidden_in_path_style",
        ),
        ({"S3_BUCKET": "rasters"}, "bucket_without_endpoint"),
    ],
)
def test_gate_rejects_what_the_adapters_reject(environ, code):
    gate = _gate()
    with pytest.raises(gate.EndpointPolicyError, match=code):
        gate.derive_gdal_env(environ)


def test_gate_discards_gdal_values_the_environment_carried():
    gate = _gate()
    environ = {
        "S3_ENDPOINT": "https://objects.example.test",
        "AWS_S3_ENDPOINT": "evil.example.test",
        "AWS_HTTPS": "NO",
        "AWS_VIRTUAL_HOSTING": "TRUE",
    }
    gate.apply_gdal_env(environ)
    assert environ["AWS_S3_ENDPOINT"] == "objects.example.test"
    assert environ["AWS_HTTPS"] == "YES"
    assert environ["AWS_VIRTUAL_HOSTING"] == "FALSE"

    no_s3 = {"AWS_S3_ENDPOINT": "evil.example.test", "AWS_HTTPS": "NO"}
    gate.apply_gdal_env(no_s3)
    assert "AWS_S3_ENDPOINT" not in no_s3 and "AWS_HTTPS" not in no_s3


def _run_gate(env, *command):
    return subprocess.run(
        [sys.executable, str(GATE), *command],
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
        check=False,
    )


def test_gate_execs_the_command_with_the_derived_env():
    probe = "import os; print(os.environ['AWS_S3_ENDPOINT'], os.environ['AWS_HTTPS'])"
    result = _run_gate(
        {"S3_ENDPOINT": "https://objects.example.test", "AWS_HTTPS": "NO"},
        sys.executable,
        "-c",
        probe,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.split() == ["objects.example.test", "YES"]


def test_gate_refuses_before_exec_without_echoing_the_input():
    marker = "secret-marker-host.example.test"
    result = _run_gate(
        {"S3_ENDPOINT": f"http://{marker}", "S3_USE_SSL": "false"},
        sys.executable,
        "-c",
        "print('server started')",
    )
    assert result.returncode == 78
    assert "server started" not in result.stdout
    assert "unsafe S3 endpoint configuration: plaintext_external_forbidden" in result.stderr
    assert marker not in result.stderr


def test_gate_without_a_command_is_a_usage_error():
    assert _run_gate({}).returncode == 2


def test_compose_starts_legacy_titiler_through_the_gate_only():
    compose = yaml.safe_load((ROOT / "docker-compose.v9.yml").read_text(encoding="utf-8"))
    service = compose["services"]["sahool-titiler"]
    # Entrypoint, not command: overriding `command` must still pass through the gate.
    assert service["entrypoint"] == ["python", "/opt/sahool/storage/gdal_s3_env_gate.py"]
    assert service["command"][0] == "uvicorn"
    env = service["environment"]
    for raw in ("AWS_S3_ENDPOINT", "AWS_HTTPS", "AWS_VIRTUAL_HOSTING"):
        assert raw not in env, f"{raw} must come from the gate, not from Compose"
    assert env["S3_ENDPOINT"] == "${S3_ENDPOINT:-http://sahool-minio:9000}"
    assert env["S3_USE_SSL"] == "${S3_USE_SSL:-}"
    assert env["S3_ALLOW_PLAINTEXT_INTERNAL"] == "${S3_ALLOW_PLAINTEXT_INTERNAL:-false}"
    mounts = {}
    for volume in service["volumes"]:
        parts = str(volume).split(":")
        if parts[0].startswith("./"):
            mounts[parts[1]] = (parts[0], parts[2:])
    for name in ("gdal_s3_env_gate.py", "s3_endpoint_security.py"):
        source, mode = mounts[f"/opt/sahool/storage/{name}"]
        assert mode == ["ro"]
        assert (ROOT / source).is_file()

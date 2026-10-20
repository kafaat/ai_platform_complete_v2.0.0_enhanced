"""Offline contract for the disposable legacy-TiTiler gate lab (no Docker calls here)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / "tests/integration/s3_titiler_gate.compose.yml"
RUNNER = ROOT / "scripts/ci/run_s3_titiler_gate_live.sh"
SCRIPT = ROOT / "scripts/ci/s3_titiler_gate_live_acceptance.py"
GATE_ENTRYPOINT = ["python", "/opt/sahool/storage/gdal_s3_env_gate.py"]


def _services():
    return yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))["services"]


def _script():
    spec = importlib.util.spec_from_file_location("sahool_titiler_gate_live", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_lab_mirrors_production_titiler_start_through_the_gate():
    lab = _services()["sahool-titiler"]
    prod = yaml.safe_load((ROOT / "docker-compose.v9.yml").read_text(encoding="utf-8"))["services"][
        "sahool-titiler"
    ]
    assert lab["entrypoint"] == prod["entrypoint"] == GATE_ENTRYPOINT
    assert lab["command"] == prod["command"]
    # The lab names MinIO as production Compose does, so the gate sees the same host.
    assert lab["environment"]["S3_ENDPOINT"] == "http://sahool-minio:9000"
    assert set(_services()) == {"sahool-minio", "sahool-titiler", "sahool-endpoint-sentinel"}


def test_lab_carries_stale_gdal_values_the_gate_must_discard():
    env = _services()["sahool-titiler"]["environment"]
    assert env["AWS_S3_ENDPOINT"].endswith(".invalid")
    assert env["AWS_HTTPS"] == "YES"
    assert env["AWS_VIRTUAL_HOSTING"] == "TRUE"


def test_lab_is_disposable_pinned_and_loopback_only():
    for name, service in _services().items():
        assert "@sha256:" in service["image"], name
        assert service["restart"] == "no", name
        for port in service.get("ports", []):
            assert port.startswith("127.0.0.1:"), (name, port)
    assert _services()["sahool-minio"]["tmpfs"] == ["/data:size=128m"]
    assert "volumes" not in _services()["sahool-minio"]
    mounts = _services()["sahool-titiler"]["volumes"]
    assert len(mounts) == 2
    for mount in mounts:
        source, target, mode = mount.split(":")
        assert mode == "ro" and target.startswith("/opt/sahool/storage/")
        assert (COMPOSE.parent / source).resolve().is_file()


def test_sentinel_answers_for_refused_hosts_without_exposure():
    sentinel = _services()["sahool-endpoint-sentinel"]
    assert sentinel["profiles"] == ["sentinel"]
    assert "ports" not in sentinel and "volumes" not in sentinel
    aliases = sentinel["networks"]["default"]["aliases"]
    assert set(aliases) == {"sahool-minio", "objects.example.test"}
    assert sentinel["image"] == _services()["sahool-titiler"]["image"]


def test_runner_proves_refusal_exec_and_no_secret():
    text = RUNNER.read_text(encoding="utf-8")
    for needle in (
        "NOT_RUN_DOCKER_UNAVAILABLE",
        "NOT_RUN_DOCKER_DAEMON_UNAVAILABLE",
        "NOT_RUN_UNPINNED_IMAGE",
        "@sha256:[0-9a-f]{64}$",
        "trap cleanup EXIT INT TERM",
        'if [[ "$status" != "78" ]]',
        "expect_refusal plaintext_internal_requires_opt_in",
        "expect_refusal plaintext_external_forbidden",
        "expect_refusal scheme_flag_conflict",
        "expect_refusal endpoint_must_be_host_only",
        "TITILER_IMAGE_DIGEST_MISMATCH",
        "TITILER_IMAGE_PLATFORM_MISMATCH",
        "TITILER_SENTINEL_BLIND",
        "TITILER_REFUSED_HOST_CONTACTED",
        "TITILER_SENTINEL_NOT_READY",
        "TITILER_SENTINEL_DNS_MISMATCH",
        "TITILER_SENTINEL_PRECONTACTED",
        "TITILER_SENTINEL_COUNT_UNSTABLE",
        "S3_ENDPOINT=http://objects.example.test:9000",
        "TITILER_GATE_CONTROL_FAILED",
        "TITILER_GATE_ECHOED_INPUT",
        "TITILER_GATE_NOT_EXECED",
        "TITILER_SIGTERM_NOT_FORWARDED",
        "TITILER_SECRET_IN_EVIDENCE",
        "--volumes --remove-orphans",
        "SAHOOL_S3_ACCEPTANCE_DISPOSABLE=1",
    ):
        assert needle in text, needle


@pytest.mark.parametrize(
    ("uri", "disposable", "reason"),
    [
        ("http://127.0.0.1:19057", False, "disposable_lab_opt_in_missing"),
        ("https://127.0.0.1:19057", True, "test_endpoint_must_be_exact_loopback"),
        ("http://sahool-minio:9000", True, "test_endpoint_must_be_exact_loopback"),
        ("http://user:pass@127.0.0.1:19057", True, "test_endpoint_must_be_exact_loopback"),
        ("http://127.0.0.1:80", True, "test_endpoint_must_be_exact_loopback"),
    ],
)
def test_acceptance_refuses_non_lab_targets(uri, disposable, reason):
    with pytest.raises(ValueError, match=reason):
        _script().validate_loopback(uri, disposable)


def test_ci_runs_the_titiler_gate_lab():
    jobs = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8"))["jobs"]
    steps = [
        (job, step)
        for job in jobs.values()
        for step in job.get("steps", [])
        if "scripts/ci/run_s3_titiler_gate_live.sh" in str(step.get("run", ""))
    ]
    assert len(steps) == 1
    job, step = steps[0]
    assert str(job["runs-on"]).startswith("ubuntu-")
    assert "continue-on-error" not in job and "continue-on-error" not in step

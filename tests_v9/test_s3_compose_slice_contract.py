"""Offline contract for the S3 Compose-slice acceptance (no Docker calls here).

The incident freeze forbids running the migrator or any migration, even against a
disposable database; this test keeps the runner unable to start one.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts/ci/run_s3_compose_slice_acceptance.sh"
SLICE = {
    "sahool-minio",
    "sahool-minio-init",
    "sahool-raster-service",
    "sahool-scout-ingest",
    "sahool-titiler",
}


def _text() -> str:
    return RUNNER.read_text(encoding="utf-8")


def test_runner_never_names_a_database_or_migration_service():
    text = _text()
    for forbidden in (
        "sahool-migrate",
        "sahool-postgres",
        "SAHOOL_MIGRATE_APPLY",
        "apply_in_compose",
    ):
        assert forbidden not in text, forbidden


def test_every_started_service_is_in_the_slice_and_dependencies_are_not_pulled_in():
    starts = re.findall(r"\bdc\b[^\n]*?\b(up|run)\b([^\n]*)", _text())
    assert starts
    for verb, rest in starts:
        services = [tok for tok in rest.split() if tok.startswith("sahool-")]
        assert services, (verb, rest)
        for service in services:
            assert service in SLICE, service
            if service != "sahool-minio":
                # minio has no dependencies; every other start must not pull the stack in.
                assert "--no-deps" in rest, (verb, rest)


def test_runner_is_fail_closed_and_keeps_secrets_out():
    text = _text()
    for needle in (
        "NOT_RUN_DOCKER_UNAVAILABLE",
        "NOT_RUN_DOCKER_DAEMON_UNAVAILABLE",
        "trap cleanup EXIT INT TERM",
        "down --volumes --remove-orphans",
        "secrets.token_hex",
        "S3_SLICE_BREAK_NOT_OBSERVED",
        "S3_SLICE_SCOPE_NOT_ENFORCED",
        "S3_SLICE_TITILER_REFUSAL_FAILED",
        "S3_SLICE_SCOUT_EXTERNAL_NOT_REFUSED",
        "S3_SLICE_RASTER_EXTERNAL_NOT_REFUSED",
        "S3_SLICE_REFUSAL_ECHOED_INPUT",
        "S3_SLICE_SECRET_IN_EVIDENCE",
        "S3_SLICE_STORAGE_NETWORK_NOT_ISOLATED",
        "S3_SLICE_STORAGE_NETWORK_PROBE_FAILED",
        "S3_SLICE_STORAGE_NETWORK_CONTROL_FAILED",
        "S3_SLICE_LOOPBACK_PORT_UNAVAILABLE",
        "S3_SLICE_ANONYMOUS_ACCESS_NOT_REFUSED",
        "S3_SLICE_WRONG_SECRET_NOT_REFUSED",
        '"tested_sha": sha',
    ):
        assert needle in text, needle


def _step(text: str, start: str, end: str) -> str:
    assert start in text and end in text, (start, end)
    return text.split(start, 1)[1].split(end, 1)[0]


def test_isolation_probe_runs_off_the_storage_network_with_a_control_on_it():
    """MINIO-COMMUNITY-EDITION-RECEIVES-NO-SECURITY-FIXES-01: the negative probe sits on
    sahool-internal only; the same probe on the storage network is the control, so a refusal
    caused by anything other than isolation cannot pass."""
    block = _step(_text(), "# 5b) Network isolation", "# 5c)")
    probes = re.findall(r"docker run ([^\n]*)", block)
    assert len(probes) == 2, probes
    negative, control = probes
    for probe in probes:
        # The slice's own raster image, never a pull, and nothing kept afterwards.
        assert "--rm" in probe and "--pull never" in probe and '"$raster_image"' in probe
    assert '--network "$INTERNAL_NET"' in negative and "STORAGE_NET" not in negative
    assert '--network "$STORAGE_NET"' in control
    assert 'INTERNAL_NET="${PROJECT}_sahool-internal"' in block
    assert 'STORAGE_NET="${PROJECT}_sahool-object-storage"' in block
    # MinIO's attachments are measured, not assumed: exactly the storage and loopback networks,
    # the storage network internal, and every MinIO address (not only the name) probed.
    assert '[[ "$minio_nets" == "$STORAGE_NET $LOOPBACK_NET" ]]' in block
    assert "{{.Internal}}" in block and '"$STORAGE_NET")" == "true"' in block
    assert "$minio_ips" in negative
    assert 'getaddrinfo("sahool-minio", 9000)' in block
    assert "! grep -q ' OPEN$'" in block


def test_unauthorized_access_and_loopback_ports_are_measured():
    block = _step(_text(), "# 5c)", "# 6)")
    assert "http://127.0.0.1:9000/minio/health/live" in block
    assert "http://127.0.0.1:9001/" in block
    # Host-side requests never go through a proxy that could answer for MinIO.
    assert "ProxyHandler({})" in block
    assert "grep -c '^ANONYMOUS .* 403$'" in block and "== 4 ]]" in block
    assert "WRONG_SECRET DENIED SignatureDoesNotMatch" in block


def test_the_slice_is_compose_s_own_isolated_topology():
    doc = yaml.safe_load((ROOT / "docker-compose.v9.yml").read_text(encoding="utf-8"))
    services = doc["services"]
    assert doc["networks"]["sahool-object-storage"]["internal"] is True
    assert services["sahool-minio"]["networks"] == [
        "sahool-object-storage",
        "sahool-object-storage-loopback",
    ]
    for name in SLICE - {"sahool-minio"}:
        assert "sahool-object-storage" in services[name]["networks"], name
    # The probe needs sahool-internal to exist in the slice: raster-service creates it.
    assert "sahool-internal" in services["sahool-raster-service"]["networks"]


def test_slice_services_exist_with_the_internal_opt_in_defaulting_off():
    services = yaml.safe_load((ROOT / "docker-compose.v9.yml").read_text(encoding="utf-8"))[
        "services"
    ]
    assert SLICE <= set(services)
    for name in ("sahool-raster-service", "sahool-scout-ingest", "sahool-titiler"):
        env = services[name]["environment"]
        assert env["S3_ALLOW_PLAINTEXT_INTERNAL"] == "${S3_ALLOW_PLAINTEXT_INTERNAL:-false}", name
    assert services["sahool-minio-init"]["depends_on"] == {
        "sahool-minio": {"condition": "service_healthy"}
    }


def test_ci_runs_the_slice_acceptance():
    jobs = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8"))["jobs"]
    steps = [
        (job, step)
        for job in jobs.values()
        for step in job.get("steps", [])
        if "scripts/ci/run_s3_compose_slice_acceptance.sh" in str(step.get("run", ""))
    ]
    assert len(steps) == 1
    job, step = steps[0]
    assert str(job["runs-on"]).startswith("ubuntu-")
    assert "continue-on-error" not in job and "continue-on-error" not in step


def test_ci_build_uses_the_official_index_and_is_bounded():
    """Run 40657966716: the slice build pulled from Compose's Alibaba default and stalled until
    the job timeout. The runner must default the index before any Compose call, keep an explicit
    value, and bound the build with a named failure."""
    text = _text()
    export = 'export PIP_INDEX_URL="${PIP_INDEX_URL:-https://pypi.org/simple}"'
    assert export in text
    assert text.index(export) < text.index("dc config --quiet")
    build = _step(text, "build_rc=0", "S3_SLICE_BUILD_FAILED")
    assert 'timeout --kill-after=30 "$BUILD_TIMEOUT"' in build
    assert "build -q sahool-raster-service sahool-scout-ingest" in build
    assert "S3_SLICE_BUILD_TIMEOUT" in build
    assert "dc build" not in text

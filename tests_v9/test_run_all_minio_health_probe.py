"""``scripts_v9/run_all.sh health`` must probe MinIO on its real health path.

MinIO serves neither ``/healthz`` nor ``/readyz``; its unauthenticated liveness
endpoint is ``/minio/health/live`` (the path the S3 lane already gates on in
``scripts/ci/run_s3_minio_gdal_live.sh``). The old probe asked MinIO for
``/healthz`` then ``/readyz`` and so reported a healthy MinIO as NOT READY.

The second defect pinned here: the counters used ``((passed++))``, which exits 1
when the counter is 0, so under ``set -euo pipefail`` the ``health`` command
aborted after the first service instead of reporting all of them.

The script is executed for real against stub ``curl``/``pg_isready``/``redis-cli``
placed first on ``PATH`` — no network, no Docker, no live service.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
RUN_ALL = ROOT / "scripts_v9" / "run_all.sh"
MINIO_LIVE = "http://localhost:9000/minio/health/live"
SERVICE_COUNT = 13

_CURL_STUB = """#!/usr/bin/env bash
url="${@: -1}"
printf '%s\\n' "$url" >> "$CURL_LOG"
case "$CURL_MODE" in
  all_ok) exit 0 ;;
  minio_only) [[ "$url" == "$MINIO_URL" ]] && exit 0 || exit 22 ;;
esac
exit 22
"""


def _run_health(tmp_path: Path, mode: str) -> tuple[subprocess.CompletedProcess[str], list[str]]:
    bash = shutil.which("bash")
    if bash is None:  # pragma: no cover - bash is present on every CI runner
        pytest.fail("bash is required to execute scripts_v9/run_all.sh")
    stub_dir = tmp_path / "bin"
    stub_dir.mkdir()
    curl = stub_dir / "curl"
    curl.write_text(_CURL_STUB, encoding="utf-8")
    ok = "#!/usr/bin/env bash\nexit 0\n"
    fail = "#!/usr/bin/env bash\nexit 1\n"
    (stub_dir / "pg_isready").write_text(ok if mode == "all_ok" else fail, encoding="utf-8")
    (stub_dir / "redis-cli").write_text(ok if mode == "all_ok" else fail, encoding="utf-8")
    for stub in stub_dir.iterdir():
        stub.chmod(0o755)
    log = tmp_path / "curl.log"
    log.touch()
    env = {
        "PATH": f"{stub_dir}{os.pathsep}{os.environ.get('PATH', '/usr/bin:/bin')}",
        "HOME": str(tmp_path),
        "CURL_LOG": str(log),
        "CURL_MODE": mode,
        "MINIO_URL": MINIO_LIVE,
    }
    proc = subprocess.run(
        [bash, str(RUN_ALL), "health"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        timeout=60,
        check=False,
    )
    return proc, log.read_text(encoding="utf-8").splitlines()


def test_minio_is_probed_on_minio_health_live_only(tmp_path: Path) -> None:
    proc, urls = _run_health(tmp_path, "minio_only")
    out = proc.stdout + proc.stderr
    assert "✓ sahool-minio (port 9000)" in out, out
    minio_urls = [u for u in urls if ":9000/" in u]
    assert minio_urls == [MINIO_LIVE], minio_urls
    # Every other service is down in this mode: the run must still report all of
    # them (not abort at the first counter increment) and exit non-zero.
    assert f"1 passed, {SERVICE_COUNT - 1} failed" in out, out
    assert proc.returncode == 1, out


def test_health_reports_every_service_when_all_are_up(tmp_path: Path) -> None:
    proc, _ = _run_health(tmp_path, "all_ok")
    out = proc.stdout + proc.stderr
    assert f"{SERVICE_COUNT} passed, 0 failed" in out, out
    assert "All systems operational!" in out, out
    assert proc.returncode == 0, out


def test_powershell_twin_probes_minio_on_its_liveness_path() -> None:
    """scripts_v9/run_all.ps1 carries the same health table; it must not probe MinIO on /healthz."""
    text = (ROOT / "scripts_v9" / "run_all.ps1").read_text(encoding="utf-8-sig")
    assert (
        "$paths = if ($svc.Port -eq 9000) { @('/minio/health/live') } else { @('/healthz', '/readyz') }"
        in text
    )
    assert "foreach ($path in $paths)" in text

"""صورةُ MinIO تُسحَب فعلاً: لا مستودعَ محذوف، ودايجستٌ مثبَّت، وفحصُ صحّةٍ بلا curl.

``MINIO-IMAGES-DELETED-FROM-DOCKER-HUB-01`` (2026-10-05): حذفت MinIO ``minio/minio`` و``minio/mc``
من Docker Hub (2026-09-11..14) وصار quay.io يشترط الدخول، فكلّ ``docker compose up`` جديد فشل
بـ``pull access denied for minio/mc``. الإصدارُ نفسُه (آخرُ إصدارٍ بالواجهة الكاملة) صار من مرآةٍ
مثبَّتةٍ بالدايجست. وقِيس من طبقاتها أنّها تحمل ``minio`` و``mc`` وbash **بلا curl ولا wget** —
ففحصُ الصحّة ``mc ready local``، وخدمةُ التهيئة تعمل على الصورة نفسها.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
PIN = (
    "coollabsio/minio:2025-04-22T22-12-26Z"
    "@sha256:a4938f37f1be1841b8e7b627ad0207b265345fd0d063e42d7410c78af0e63e68"
)
COMPOSE = sorted(ROOT.glob("docker-compose*.yml"))


def test_the_contract_gate_passes_on_the_tree():
    proc = subprocess.run(
        [sys.executable, "scripts/ci/minio_s3_contract_gate.py"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


@pytest.mark.parametrize("compose", COMPOSE, ids=lambda p: p.name)
def test_no_compose_file_pulls_a_deleted_docker_hub_repository(compose):
    for line in compose.read_text(encoding="utf-8").splitlines():
        if "image:" in line:
            assert not re.search(r"[\s:-](docker\.io/)?minio/(minio|mc):", line), (
                f"{compose.name}: {line.strip()} — مستودعٌ حُذِف من Docker Hub"
            )


def test_every_minio_image_reference_is_the_digest_pin():
    refs = [
        line.strip()
        for compose in COMPOSE
        for line in compose.read_text(encoding="utf-8").splitlines()
        if "image:" in line and ("MINIO_IMAGE" in line or "MINIO_MC_IMAGE" in line)
    ]
    assert refs, "لا مرجعَ لصورة MinIO — الشاهد بلا عين"
    assert all(PIN in ref for ref in refs), refs
    env = (ROOT / ".env.example").read_text(encoding="utf-8")
    assert f"MINIO_IMAGE={PIN}" in env and f"MINIO_MC_IMAGE={PIN}" in env


def test_the_minio_healthcheck_does_not_need_curl():
    """الصورة بلا curl: فحصٌ به يُبقي الخادم unhealthy فلا تبدأ ``sahool-minio-init`` أبداً."""
    v9 = (ROOT / "docker-compose.v9.yml").read_text(encoding="utf-8")
    block = v9.split("\n  sahool-minio:", 1)[1].split("\n  sahool-", 1)[0]
    assert "- mc\n      - ready\n      - local" in block
    health = block.split("healthcheck:", 1)[1]
    code = [ln for ln in health.splitlines() if not ln.strip().startswith("#")]
    assert not any("curl" in ln for ln in code), "فحصُ الصحّة يستدعي curl"

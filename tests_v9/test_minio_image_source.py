"""صورةُ MinIO تُسحَب فعلاً: لا مستودعَ محذوف، ودايجستٌ مثبَّت، وفحصُ صحّةٍ بلا curl.

``MINIO-IMAGES-DELETED-FROM-DOCKER-HUB-01`` (2026-10-05): حذفت MinIO ``minio/minio`` و``minio/mc``
من Docker Hub (2026-09-11..14) وصار quay.io يشترط الدخول، فكلّ ``docker compose up`` جديد فشل
بـ``pull access denied for minio/mc``. الإصدارُ نفسُه (آخرُ إصدارٍ بالواجهة الكاملة) صار من مرآةٍ
مثبَّتةٍ بالدايجست. وقِيس من طبقاتها أنّها تحمل ``minio`` و``mc`` وbash **بلا curl ولا wget** —
ففحصُ الصحّة ``mc ready local``، وخدمةُ التهيئة تعمل على الصورة نفسها.
"""

from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
PIN = (
    "coollabsio/minio:2025-04-22T22-12-26Z"
    "@sha256:a4938f37f1be1841b8e7b627ad0207b265345fd0d063e42d7410c78af0e63e68"
)
COMPOSE = sorted(ROOT.glob("docker-compose*.yml"))
DELETED = re.compile(r"[\s:'\"-](docker\.io/)?minio/(minio|mc)(?=[:@'\"]|\s*$)")


def _gate():
    spec = importlib.util.spec_from_file_location(
        "minio_gate", ROOT / "scripts/ci/minio_s3_contract_gate.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


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
            assert not DELETED.search(line), (
                f"{compose.name}: {line.strip()} — مستودعٌ حُذِف من Docker Hub"
            )


DELETED_FORMS = [
    "minio/minio:RELEASE.2025-04-22T22-12-26Z",
    "minio/minio@sha256:" + "a" * 64,
    "docker.io/minio/mc@sha256:" + "b" * 64,
    "minio/mc",
    '"minio/mc:latest"',
]
KEPT_FORMS = [PIN, "minio/minio-extra:1", "coollabsio/minio/mc:1", "quay.io/minio/minio:x"]


@pytest.mark.parametrize("ref", DELETED_FORMS)
def test_the_deleted_repository_is_rejected_in_every_reference_form(ref):
    """مراجعة Copilot على #1139: البادئة ``minio/minio:`` كانت تُفلت الدايجست ``minio/minio@sha256:…``."""
    assert _gate().is_deleted_repo(ref)
    assert DELETED.search(f"    image: {ref}")


@pytest.mark.parametrize("ref", KEPT_FORMS)
def test_other_repositories_are_not_mistaken_for_the_deleted_one(ref):
    assert not _gate().is_deleted_repo(ref)
    assert not DELETED.search(f"    image: {ref}")


def test_service_blocks_stop_at_the_next_top_level_key():
    """مراجعة Copilot على #1139: الكتلةُ الأخيرة كانت تبتلع ``volumes:`` وما بعده."""
    lines = [
        "services:",
        "  sahool-minio:",
        "    image: ${MINIO_IMAGE:-x}",
        "volumes:",
        "  minio-data:",
        "    driver: local",
        "x-health:",
        "  probe:",
        "    test: curl http://minio/health",
    ]
    blocks = _gate().service_blocks(lines)
    assert blocks == [["  sahool-minio:", "    image: ${MINIO_IMAGE:-x}"]]


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
    """الصورة بلا curl: فحصٌ به يُبقي الخادم unhealthy فلا تبدأ ``sahool-minio-init`` أبداً.

    يُقرأ بنيويّاً (YAML) لا بتقطيع النصّ — إعادةُ ترتيب الملفّ أو تسميةُ الخدمة تُفشِل الشاهدَ
    برسالةٍ تقول ما الناقص لا بـIndexError (مراجعة Copilot على #1139)."""
    services = yaml.safe_load((ROOT / "docker-compose.v9.yml").read_text(encoding="utf-8"))[
        "services"
    ]
    minio = [
        name
        for name, svc in services.items()
        if str(svc.get("image", "")).startswith("${MINIO_IMAGE:-")
    ]
    assert minio == ["sahool-minio"], f"خدمةُ خادم MinIO في v9 غير متعيّنة: {minio}"
    test = services["sahool-minio"].get("healthcheck", {}).get("test")
    assert test == ["CMD", "mc", "ready", "local"], test


# ── توسيعٌ 2026-10-11: صورةُ MinIO من أيّ سجلٍّ أو مساحة يجب أن تكون الإبرة، وفحصُ الصحّة بلا curl ولا wget ──
# ``quay.io/minio/minio`` يبقى في ``KEPT_FORMS`` أعلاه: ليس «محذوفاً» بل يشترط الدخول، فيُرفَض هنا
# لأنّه ليس الإبرةَ المثبَّتة، لا لأنّه محذوف.
MINIO_FORMS = [
    PIN,
    "quay.io/minio/minio:RELEASE.2025-04-22T22-12-26Z",
    "quay.io/minio/mc:RELEASE.2025-04-16T18-13-26Z",
    "bitnami/minio:2025.4.22",
    "bitnami/minio-client:2025.4.16",
    "coollabsio/minio:2025-04-22T22-12-26Z",
    "minio/mc",
]
NOT_MINIO_FORMS = [
    "postgres:16",
    "redis:7-alpine",
    "minio/minio-extra:1",
    "mcr.microsoft.com/dotnet/runtime:8.0",
    "itzg/minecraft-server",
]


@pytest.mark.parametrize("ref", MINIO_FORMS)
def test_a_minio_image_is_recognised_from_any_registry_or_namespace(ref):
    assert _gate().is_minio_image(ref)


@pytest.mark.parametrize("ref", NOT_MINIO_FORMS)
def test_unrelated_images_are_not_taken_for_minio(ref):
    assert not _gate().is_minio_image(ref)


def _gate_on_probe_tree(tmp_path, capsys, services_yaml):
    """``main()`` الحارسِ نفسُه على شجرةٍ دنيا: ملفّاته الثلاثة الحقيقيّة + ملفّ compose مِسبارٌ واحد.

    داخل العمليّة لا عبر subprocess (الشجرةُ الحقيقيّة يغطّيها ``test_the_contract_gate_passes_on_the_tree``):
    ``fail()`` يرفع ``SystemExit(1)`` ويطبع السبب، و``main()`` يُرجع 0 عند المرور."""
    for rel in ("scripts/minio/provision.sh", "docker-compose.v9.yml", ".env.example"):
        dst = tmp_path / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes((ROOT / rel).read_bytes())
    (tmp_path / "docker-compose.probe.yml").write_text(
        "services:\n" + services_yaml, encoding="utf-8"
    )
    gate = _gate()
    gate.ROOT = tmp_path
    gate.COMPOSE = tmp_path / "docker-compose.v9.yml"
    gate.ENV_EXAMPLE = tmp_path / ".env.example"
    try:
        code = gate.main()
    except SystemExit as exc:
        code = exc.code
    return code, capsys.readouterr().out


def test_the_probe_tree_passes_with_the_pinned_image_and_an_mc_healthcheck(tmp_path, capsys):
    """ضابط: المِسبارُ السليم يمرّ — فكلُّ حمرةٍ أدناه سببُها المرجعُ أو الفحصُ وحده لا الشجرةُ المصغّرة."""
    code, out = _gate_on_probe_tree(
        tmp_path,
        capsys,
        f"  probe-minio:\n    image: ${{MINIO_IMAGE:-{PIN}}}\n"
        '    healthcheck:\n      test: ["CMD", "mc", "ready", "local"]\n',
    )
    assert code == 0, out


@pytest.mark.parametrize("ref", [r for r in MINIO_FORMS if r != PIN])
def test_the_gate_rejects_a_minio_image_that_is_not_the_pin(tmp_path, capsys, ref):
    code, out = _gate_on_probe_tree(tmp_path, capsys, f"  probe-minio:\n    image: {ref}\n")
    assert code == 1, out
    assert "docker-compose.probe.yml" in out, out


@pytest.mark.parametrize(
    "probe",
    [
        '["CMD", "wget", "-q", "--spider", "http://localhost:9000/minio/health/live"]',
        '["CMD", "curl", "-f", "http://localhost:9000/"]',
        '["CMD-SHELL", "curl -fsS http://localhost:9000/minio/health/ready || exit 1"]',
    ],
    ids=["wget-on-health-path", "curl-on-root-path", "curl-in-shell-form"],
)
def test_the_gate_rejects_an_http_client_healthcheck_on_minio(tmp_path, capsys, probe):
    code, out = _gate_on_probe_tree(
        tmp_path,
        capsys,
        f"  probe-minio:\n    image: ${{MINIO_IMAGE:-{PIN}}}\n    healthcheck:\n      test: {probe}\n",
    )
    assert code == 1, out
    assert "healthcheck" in out, out


def test_a_comment_about_curl_inside_the_healthcheck_is_not_a_probe():
    """``sahool-minio`` في v9 يشرح غيابَ curl بتعليقٍ داخل قسم الفحص نفسه — لا يُقرأ فحصاً."""
    block = [
        "  sahool-minio:",
        "    image: ${MINIO_IMAGE:-x}",
        "    healthcheck:",
        "      # الصورة بلا curl ولا wget",
        '      test: ["CMD", "mc", "ready", "local"]  # not curl',
        "      interval: 30s",
        "    volumes:",
        "    - curl-cache:/x",
    ]
    gate = _gate()
    probe = gate.healthcheck_probe(block)
    assert "ready" in probe and "interval" in probe, probe
    assert not gate._HTTP_CLIENT.search(probe), probe

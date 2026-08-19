"""عقد توفير عميل PostgreSQL: **من الصورة المسحوبة، لا من مرآة Ubuntu**.

العطل المؤسِّس مقيس مرّتين في تشغيلٍ واحد (32274613475): `apt-get` تجمّد ثلاث
محاولاتٍ مع تبديل مرآة، فغاب `psql`، فلم تعمل خطوة إنشاء `sahool_app`، فطبع حارس
الإغلاق ``RESTRICTED_ROLE_NOT_FOUND`` — رسالةً **عن schema** عن قاعدةٍ لم تُقَس.

وحالتان منها ليستا نظريّتين: **أسقطتا أوّل صيغةٍ كتبتُها** في تشغيل 32280469751،
فهما مُثبتتان بالتاريخ لا بالتخيّل.

  ① `docker exec` داخل حاوية الخادم ⇒ ``psql: error: migrations/init_v8.sql:
     No such file or directory``. الرايةُ `-f` يحلّها **العميل** من نظام ملفّاته،
     وشجرةُ المستودع لا وجود لها داخل الحاوية. فالعلاج حاويةٌ عابرة من الصورة
     نفسها مع تركيب شجرة العمل.
  ② `export PATH` داخل سكربتٍ مُستدعىً بـ`bash` يموت مع عمليّته، و`GITHUB_PATH`
     يخدم الخطوات **التالية** وحدها. فبقيت `pg_isready` مفقودةً في الخطوة نفسها
     وسقطت `Integration Tests` — وكانت خضراء قبل تغييري.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "ci" / "provision_pg_client.sh"
CI = ROOT / ".github/workflows/ci.yml"


def _fake_docker(tmp_path: Path, *, image: str | None) -> Path:
    log = tmp_path / "calls.log"
    docker = tmp_path / "docker"
    # `docker` المزيّف **يستنزف stdin عند `-i`** كما يفعل الحقيقيّ. بدون ذلك كانت
    # حالةُ استنزاف المجرى تمرّ خضراء على الطفرة نفسها — تؤكّد خاصّيّةً لا تقيسها.
    body = f'#!/usr/bin/env bash\necho "$@" >> "{log}"\nif [ "$1" = "inspect" ]; then\n'
    body += "  exit 1\nfi\n" if image is None else f'  echo "{image}"\n  exit 0\nfi\n'
    body += 'for a in "$@"; do [ "$a" = "-i" ] && cat >/dev/null; done\n'
    body += "exit 0\n"
    docker.write_text(body, encoding="utf-8")
    docker.chmod(0o755)
    return log


def _run(tmp_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = {"PATH": f"{tmp_path}:/usr/bin:/bin", "RUNNER_TEMP": str(tmp_path / "runner")}
    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        cwd=tmp_path,
    )


def _shim(tmp_path: Path, tool: str) -> Path:
    return tmp_path / "runner" / "pg-client-shims" / tool


def test_the_client_is_derived_from_the_pulled_image_and_never_from_apt(tmp_path):
    log = _fake_docker(tmp_path, image="postgis/postgis:16-3.4")
    result = _run(tmp_path, "sahool-pg16")
    assert result.returncode == 0, result.stderr
    calls = log.read_text(encoding="utf-8")
    assert "inspect" in calls
    assert "pull" not in calls, "لا سحبَ إضافيّاً: الصورة محلّيّة أصلاً"
    for tool in ("psql", "pg_isready"):
        shim = _shim(tmp_path, tool)
        assert shim.is_file() and shim.stat().st_mode & 0o111
        assert "apt" not in shim.read_text(encoding="utf-8")


def test_a_container_that_is_not_running_fails_provisioning_immediately(tmp_path):
    """وإلّا رُكِّب غلافٌ يفشل لاحقاً برسالةٍ لا تسمّي سببها."""
    _fake_docker(tmp_path, image=None)
    result = _run(tmp_path, "sahool-pg16")
    assert result.returncode != 0
    assert "sahool-pg16" in result.stdout + result.stderr
    assert not _shim(tmp_path, "psql").exists()


def test_the_workspace_is_mounted_so_client_side_file_flags_resolve(tmp_path):
    """الرايةُ `-f migrations/…` تُحلّ من جانب العميل — بلا تركيبٍ يفشل بـNo such file.

    هذا العطل بعينه أسقط أوّل صيغة: `docker exec` في حاوية الخادم لا ترى المستودع.
    """
    log = _fake_docker(tmp_path, image="postgres:15")
    assert _run(tmp_path, "ds-pg").returncode == 0
    log.write_text("", encoding="utf-8")
    subprocess.run(
        [str(_shim(tmp_path, "psql")), "-h", "localhost", "-p", "5434", "-f", "migrations/x.sql"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={"PATH": f"{tmp_path}:/usr/bin:/bin"},
        cwd=tmp_path,
    )
    forwarded = log.read_text(encoding="utf-8").strip()
    assert f"-v {tmp_path}:{tmp_path}" in forwarded, "شجرة العمل غير مركَّبة"
    assert f"-w {tmp_path}" in forwarded
    # الوسائط تُمرَّر كما هي: `--network host` تجعل عنوان المضيف صحيحاً بلا إعادة كتابة.
    assert "--network host" in forwarded
    assert "-h localhost -p 5434 -f migrations/x.sql" in forwarded


def test_every_call_site_exports_the_shim_directory_in_its_own_step():
    """المتغيّر `GITHUB_PATH` يخدم الخطوات التالية وحدها؛ وبلا تصديرٍ هنا تبقى الأداة مفقودة.

    سقوطُ `Integration Tests` في 32280469751 كان هذا بعينه — وكانت خضراء قبله.
    """
    ci = CI.read_text(encoding="utf-8")
    assert "resilient_apt_install.sh postgresql-client" not in ci, (
        "عودةُ طريق apt تُعيد رهان الشبكة الذي سقط خمس مرّات مقيسة، وتترك مصدرَي "
        "حقيقةٍ لكيفيّة وصول `psql`: الصورة المسحوبة ومرآةُ Ubuntu — فيصير أيّ عطلٍ "
        "لاحق قابلاً للنسبة إلى أيّهما بلا قياس"
    )
    lines = ci.splitlines()
    sites = [i for i, line in enumerate(lines) if "provision_pg_client.sh" in line]
    assert len(sites) == 3, f"مواضع الاستدعاء = {len(sites)}"
    for i in sites:
        assert 'export PATH="${RUNNER_TEMP:-/tmp}/pg-client-shims:$PATH"' in lines[i + 1], (
            f"السطر {i + 1} لا يُصدِّر دليل الأغلفة في الخطوة نفسها"
        )


# ملاحظة: كانت هنا حالةٌ تفرض أنّ الغلاف لا يصل `-i` مع `-f`. ورفض المالك ذلك
# التصميم بحقّ: الغلاف **عميلٌ عامّ**، وشرطٌ كهذا يكسر `psql -f -` ويُقيّد
# استعمالاتٍ مشروعة (`psql < file.sql` · `\copy`). فبقي `-i` كما هو، وانتقل
# العقد إلى مالك التعداد — `test_apply_migration_manifest.py::
# test_a_client_that_reads_stdin_cannot_truncate_the_manifest` — حيث يُقاس
# بـ`psql` مزيّفٍ **يقرأ stdin عمداً**. فصلُ سلطاتٍ لا ترقيع عميل.


def test_the_integration_job_fails_loudly_when_migrations_create_nothing():
    """وحتّى لو عاد استنزافٌ بصيغةٍ أخرى، لا يمرّ الصمت: العدّ يحجب في موضعه."""
    ci = CI.read_text(encoding="utf-8")
    assert "MIGRATIONS_APPLIED_NOTHING" in ci
    assert "information_schema.tables" in ci


def test_the_harness_verdict_derives_its_primary_error_instead_of_asserting_one():
    """سببٌ ثابتٌ في النصّ يُنتِج نسبةً كاذبة كالتي جاء ليُصلحها.

    كُتِب أوّلاً `primary_error=POSTGRES_CLIENT_PROVISIONING_FAILED` ثابتاً، فطُبِع
    في 32285597465 **والتوفير ناجح**: `psql` عمل وطبّق `init_v8.sql` كاملةً،
    والعطل كان اقتطاع حلقة الهجرات باستنزاف stdin. فصار السبب يُقاس من حالة
    العالم لا يُدَّعى.
    """
    ci = CI.read_text(encoding="utf-8")
    assert "primary_error=$primary" in ci, "السبب ما زال مكتوباً بيد"
    for branch in (
        "POSTGRES_CLIENT_PROVISIONING_FAILED",
        "POSTGRES_UNREACHABLE",
        "PREREQUISITE_STEP_FAILED_SEE_EARLIER_ERROR",
    ):
        assert branch in ci, f"فرعُ التشخيص «{branch}» غائب"
    # ولا يبقى الثابت القديم **مطبوعاً** بلا اشتقاق. والفحص على سطور الطباعة
    # وحدها: ذكرُ الاسم في تعليقٍ يشرح العطل توثيقٌ لا ارتكاب.
    printed = [ln for ln in ci.splitlines() if "echo" in ln and "primary_error" in ln]
    assert printed, "لا سطر طباعةٍ للسبب"
    assert all("$primary" in ln for ln in printed), printed


def test_playwright_dependency_install_is_retried_and_still_fails_closed():
    """محاولةٌ واحدة تُسقِط وظيفةً على انقطاعةٍ لا على عطل.

    مقيس في 32294898446: `exit code 124` بعد 4.5د على `apt-get update` داخل
    `playwright install --with-deps`، والأمرُ نفسه نجح في 2م55ث على رأسٍ آخر.
    والمهلة وحدها تُحوّل التعليق إلى فشلٍ مقروء ولا تُنجح التثبيت — فتُعاد ثلاثاً،
    ويبقى استنفادُها حاجباً باسمٍ يقول سببه.
    """
    ci = CI.read_text(encoding="utf-8")
    assert "for attempt in 1 2 3; do" in ci
    assert "PLAYWRIGHT_DEPS_INSTALL_FAILED" in ci
    # ولا يُلَيَّن العقد: لا `|| true` ولا `continue-on-error` على هذه الخطوة.
    block = ci[ci.index("Install Playwright browser") : ci.index("npx playwright test")]
    assert "continue-on-error" not in block
    assert "exit 1" in block
    # والحدّ **أوّلُ ما يُنفَّذ في سطره**: `ci_unbounded_wait_guard` يُثبِّت نمطه على
    # بداية الأمر، وخبْؤه داخل `if` أخفاه عنه فاحمرّ في 32296898767. وهو محقّ:
    # حدٌّ لا يظهر في المقدّمة يسهل أن يزول بإعادة صياغة.
    invocation = next(ln for ln in block.splitlines() if "playwright install --with-deps" in ln)
    assert invocation.strip().startswith("timeout "), invocation

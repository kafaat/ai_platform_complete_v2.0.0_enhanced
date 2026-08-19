"""العقد التنفيذيّ لتثبيت متصفّح Playwright — **علاج APT مُعمَّماً، ومقيساً كما نُفِّذ**.

وقع العطل مرّتين: تعليقٌ ٨٠+ دقيقة بلا سقف (تشغيل 32160054946)، ثمّ — بعد إضافة
السقف — سقوطٌ بـ`exit 124` (تشغيل 32269598189). والثانية هي حجّة هذا السكربت: السقف
عمل كما صُمِّم، لكنّه **يحوّل الحرق إلى فشل ولا يُنجِح التثبيت**، وهو الدرس نفسه الذي
عولج في APT.

يُزيَّف `npx`/`sudo`/`sed` ويُسجَّل كلّ استدعاء، فيُقاس الفرعُ المُنفَّذ لا نصُّه.
"""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.security]

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "ci" / "resilient_playwright_install.sh"


def _fake_bin(tmp_path: Path, *, succeed_on: int | None) -> Path:
    log = tmp_path / "calls.log"
    counter = tmp_path / "n"
    counter.write_text("0", encoding="utf-8")
    on = "" if succeed_on is None else str(succeed_on)

    npx = tmp_path / "npx"
    npx.write_text(
        "#!/usr/bin/env bash\n"
        f'echo "npx $*" >> "{log}"\n'
        f'n=$(cat "{counter}"); n=$((n + 1)); echo "$n" > "{counter}"\n'
        f'[ -n "{on}" ] && [ "$n" -ge "{on}" ] && exit 0\n'
        "exit 1\n",
        encoding="utf-8",
    )
    npx.chmod(npx.stat().st_mode | stat.S_IEXEC)

    for name in ("sudo", "sed"):
        p = tmp_path / name
        body = 'exec "$@"\n' if name == "sudo" else "exit 0\n"
        p.write_text(
            f'#!/usr/bin/env bash\necho "{name} $*" >> "{log}"\n{body}',
            encoding="utf-8",
        )
        p.chmod(p.stat().st_mode | stat.S_IEXEC)
    return log


def _run(tmp_path: Path, **env_extra: str) -> tuple[subprocess.CompletedProcess, str]:
    env = os.environ.copy()
    env["PATH"] = f"{tmp_path}:{env['PATH']}"
    env.setdefault("PW_BACKOFF", "0")
    env.update(env_extra)
    proc = subprocess.run(
        ["bash", str(SCRIPT), "chromium"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        timeout=120,
    )
    log = tmp_path / "calls.log"
    return proc, (log.read_text(encoding="utf-8") if log.exists() else "")


def _attempts(log: str) -> int:
    """المحاولات = أسطر `npx` **المباشرة**، لا أيّ ذكرٍ للاسم.

    الدرس مأخوذٌ من اختبار APT: هناك عدَّ التأكيدُ الغلافَ مع المغلَّف فأعطى الضعف.
    """
    return sum(1 for x in log.splitlines() if x.startswith("npx playwright install"))


def test_the_script_parses_as_bash():
    r = subprocess.run(
        ["bash", "-n", str(SCRIPT)], capture_output=True, text=True, encoding="utf-8"
    )
    assert r.returncode == 0, r.stderr


def test_a_first_attempt_success_neither_retries_nor_switches_the_mirror(tmp_path):
    """المسار السعيد لا يدفع ثمن العلاج — والمقيس الطبيعيّ ~٣ دقائق."""
    _fake_bin(tmp_path, succeed_on=1)
    proc, log = _run(tmp_path)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert _attempts(log) == 1, log
    assert "sed" not in log, "تبديل المرآة على نجاحٍ من أوّل محاولة تغييرٌ بلا سبب"


def test_a_transient_failure_is_retried_and_the_apt_mirror_is_switched_first(tmp_path):
    """`--with-deps` يستدعي apt من جوفه، فالمرآة متّجهٌ مشترك مع APT — تُبدَّل قبل النوم."""
    _fake_bin(tmp_path, succeed_on=2)
    proc, log = _run(tmp_path)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert _attempts(log) == 2, log
    lines = log.splitlines()
    first_sed = next(i for i, x in enumerate(lines) if x.startswith("sed"))
    second = [i for i, x in enumerate(lines) if x.startswith("npx playwright install")][1]
    assert first_sed < second, "المرآة تُبدَّل قبل المحاولة التالية لا بعدها"


def test_exhausting_every_attempt_fails_closed_and_names_the_cdn_limit(tmp_path):
    """الرسالة تقول ما جُرِّب **وما لم يُجرَّب**.

    المرآة تُبدَّل؛ ولا مرآة بديلة مُعدّة لـCDN متصفّحات Playwright في هذا المستودع.
    وإخفاءُ ذلك يجعل قارئ الأحمر يظنّ أنّ كلّ المصادر جُرِّبت.
    """
    _fake_bin(tmp_path, succeed_on=None)
    proc, log = _run(tmp_path, PW_ATTEMPTS="3")
    assert proc.returncode != 0
    assert _attempts(log) == 3, log
    assert "::error::" in proc.stderr, proc.stderr
    assert "CDN" in proc.stderr, "حدُّ العلاج يُعلَن حيث يُقرأ الفشل"


def test_no_browser_requested_is_a_usage_error_not_a_silent_success(tmp_path):
    _fake_bin(tmp_path, succeed_on=1)
    env = os.environ.copy()
    env["PATH"] = f"{tmp_path}:{env['PATH']}"
    proc = subprocess.run(
        ["bash", str(SCRIPT)], capture_output=True, text=True, encoding="utf-8", env=env
    )
    assert proc.returncode == 2, proc.stdout + proc.stderr


def test_the_workflow_delegates_and_keeps_the_job_capped():
    """الخطوة تُفوِّض، **والوظيفة تبقى مسقوفة** — والثاني ليس تحصيل حاصل.

    نقلُ `--with-deps` إلى السكربت أخرج علامةَ «تجهيزٌ شبكيّ» من متن الوظيفة، فعميت
    القاعدة ① عن `frontend-e2e` وبقي سقفها قائماً **بلا حارس**. مقيس بالزرع قبل
    إضافة علامة `scripts/ci/resilient_`. هذا التأكيد يمنع عودة العمى بصمت.
    """
    ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "scripts/ci/resilient_playwright_install.sh chromium" in ci
    assert "timeout -k 10 300 npx playwright install" not in ci, (
        "السطر المباشر أُزيل، وإلّا بقي مصدران للحقيقة"
    )
    head = ci.index("  frontend-e2e:")
    assert "timeout-minutes:" in ci[head : ci.index("    steps:", head)], (
        "الوظيفة تبقى مسقوفة: السكربت يحدّ المحاولة، والسقف يحدّ الوظيفة كلّها"
    )


def test_the_mirror_fallback_is_shared_not_copied():
    """نسختان من تبديل المرآة تنحرفان عند أوّل تعديل — الدرس المُسجَّل ثلاث مرّات."""
    shared = ROOT / "scripts/ci/apt_mirror_fallback.sh"
    assert shared.is_file()
    for caller in ("resilient_apt_install.sh", "resilient_playwright_install.sh"):
        text = (ROOT / "scripts/ci" / caller).read_text(encoding="utf-8")
        assert "apt_mirror_fallback.sh" in text, f"{caller} لا يشترك في الدالّة"
        assert "sources.list.d/ubuntu.sources" not in text, (
            f"{caller} يحمل نسخةً ثانية من منطق التبديل"
        )

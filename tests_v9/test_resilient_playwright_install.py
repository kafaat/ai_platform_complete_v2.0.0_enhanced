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

    for name in ("sudo", "sed", "pgrep"):
        p = tmp_path / name
        # pgrep مزيّف «لا apt حيّ»: وإلّا قاس الاختبارُ عملياتِ المُشغِّل لا السكربت.
        body = {"sudo": 'exec "$@"\n', "sed": "exit 0\n", "pgrep": "exit 1\n"}[name]
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
    env.setdefault("APT_SOURCE_FILES", _apt_sources(tmp_path))
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


def _apt_sources(tmp_path: Path) -> str:
    """ملفّ مصادر APT **اصطناعيّ** يُحقَن، فلا يُقاس نظام ملفّات المُشغِّل.

    كانت المسارات مُصلَّبة في `switch_apt_mirror`، فصار هذا الاختبار يمرّ أو يسقط
    بحسب وجود `/etc/apt` على الآلة: يزيّف `sed` لكنّه لا يُستدعى أصلاً إن لم يوجد
    الملفّ. أمسكها مراجعٌ خارجيّ على مُشغِّلٍ بلا `/etc/apt`، ومرّت هنا لأنّه موجود —
    أي أنّ الاختبار كان **يقيس البيئة لا السكربت**.
    """
    src = tmp_path / "ubuntu.sources"
    src.write_text("URIs: http://azure.archive.ubuntu.com/ubuntu/\n", encoding="utf-8")
    return str(src)


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


# ── سجلّ CI 2026-09-30 (تثبيت Playwright بعد دمج b0c14b6d): عطلان مقيسان من السجلّ نفسه ──


def _script_with(tmp_path: Path, name: str, body: str) -> None:
    p = tmp_path / name
    p.write_text("#!/usr/bin/env bash\n" + body, encoding="utf-8")
    p.chmod(p.stat().st_mode | stat.S_IEXEC)


def test_a_retry_waits_for_the_orphaned_apt_that_still_holds_the_dpkg_lock(tmp_path):
    """المحاولةُ المنتهية تركت `apt-get` حيّاً يحمل القفل، فسقطت التاليتان في ~٣ث لكلٍّ.

    الإعادةُ تنتظر اليتيمَ (بسقف) بدل أن تصطدم بقفله — ولا تقتله: قتلُ dpkg أثناء
    التثبيت يُفسد حالته.
    """
    log = _fake_bin(tmp_path, succeed_on=2)
    polls = tmp_path / "polls"
    polls.write_text("0", encoding="utf-8")
    _script_with(
        tmp_path,
        "pgrep",
        f'echo "pgrep $*" >> "{log}"\n'
        f'n=$(cat "{polls}"); n=$((n + 1)); echo "$n" > "{polls}"\n'
        '[ "$n" -le 2 ] && { echo "2655 apt-get install -y fonts-freefont-ttf"; exit 0; }\n'
        "exit 1\n",
    )
    proc, calls = _run(tmp_path, APT_IDLE_POLL="0")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    lines = calls.splitlines()
    idle = [i for i, x in enumerate(lines) if x.startswith("pgrep")]
    second = [i for i, x in enumerate(lines) if x.startswith("npx playwright install")][1]
    assert len(idle) == 3 and idle[-1] < second, "المحاولةُ الثانية بعد تحرّر القفل لا قبله"
    assert "2655 apt-get" in proc.stdout, "اليتيمُ يُسمّى في السجلّ"
    assert "تحرّر قفلُ apt" in proc.stdout


def test_the_mirror_switch_reaches_the_runner_mirrorlist(tmp_path):
    """مُشغِّلاتُ GitHub تقرأ المرآة من `mirror+file:/etc/apt/apt-mirrors.txt`.

    السجلّ طبع «المرآة بُدِّلت» ثمّ جلب التحديثُ التالي من `azure.archive.ubuntu.com`
    نفسِه. ملفُّ المصادر هنا **بصيغة المُشغِّل** و`sed` حقيقيّ — الاختبارُ السابق زيّف
    `sed` وكتب مصدراً بمضيفٍ صريح لا يوجد على المُشغِّل، فلم يكن ليرى العطل.
    """
    _script_with(tmp_path, "sudo", 'exec "$@"\n')
    sources = tmp_path / "ubuntu.sources"
    sources.write_text("Types: deb\nURIs: mirror+file:/etc/apt/apt-mirrors.txt\n", encoding="utf-8")
    mirrors = tmp_path / "apt-mirrors.txt"
    mirrors.write_text(
        "http://azure.archive.ubuntu.com/ubuntu/\tpriority:1\n"
        "https://archive.ubuntu.com/ubuntu/\tpriority:2\n",
        encoding="utf-8",
    )
    helper = ROOT / "scripts/ci/apt_mirror_fallback.sh"
    env = os.environ.copy()
    env["PATH"] = f"{tmp_path}:{env['PATH']}"
    env["APT_SOURCE_FILES"] = f"{mirrors} {sources}"
    probe = subprocess.run(
        ["bash", "-c", f'. "{helper}"; switch_apt_mirror'],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
    )
    assert "azure" not in mirrors.read_text(encoding="utf-8")
    assert "بُدِّلت" in probe.stdout and str(mirrors) in probe.stdout, probe.stdout


def test_a_switch_that_finds_no_host_does_not_claim_it_switched(tmp_path):
    """`sed -i` يُعيد صفراً بلا استبدال — فالرمزُ لا يشهد أنّ المرآة بُدِّلت."""
    _script_with(tmp_path, "sudo", 'exec "$@"\n')
    sources = tmp_path / "ubuntu.sources"
    sources.write_text("URIs: mirror+file:/etc/apt/apt-mirrors.txt\n", encoding="utf-8")
    helper = ROOT / "scripts/ci/apt_mirror_fallback.sh"
    env = os.environ.copy()
    env["PATH"] = f"{tmp_path}:{env['PATH']}"
    env["APT_SOURCE_FILES"] = f"{tmp_path / 'absent.txt'} {sources}"
    probe = subprocess.run(
        ["bash", "-c", f'. "{helper}"; switch_apt_mirror'],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
    )
    assert probe.returncode == 0, "تبديلُ المرآة تحسينُ فرصة لا شرطُ صحّة"
    assert "بُدِّلت" not in probe.stdout, probe.stdout
    assert "لم تُبدَّل" in probe.stdout


def test_the_final_error_says_which_attempts_timed_out_and_which_failed(tmp_path):
    """«تجاوز مهلته ٣ مرّات» ومحاولتان منها سقطتا على القفل في ثوانٍ — ادّعاءٌ لم يقع."""
    log = _fake_bin(tmp_path, succeed_on=None)
    counter = tmp_path / "rc_n"
    counter.write_text("0", encoding="utf-8")
    _script_with(
        tmp_path,
        "npx",
        f'echo "npx $*" >> "{log}"\n'
        f'n=$(cat "{counter}"); n=$((n + 1)); echo "$n" > "{counter}"\n'
        '[ "$n" = 1 ] && exit 124\n'
        "exit 100\n",
    )
    proc, _ = _run(tmp_path, PW_ATTEMPTS="3")
    assert proc.returncode != 0
    assert "1:مهلة" in proc.stderr and "2:فشل(100)" in proc.stderr, proc.stderr
    assert "تجاوز مهلته" not in proc.stderr

"""العقد التنفيذيّ لتثبيت APT الصامد — **ما نُفِّذ يُقاس، لا ما كُتِب**.

وقع العطل ثلاث مرّات في يومٍ واحد على هذا المستودع (15:53 · 16:14 · 18:09)، وفي كلٍّ
منها بلغ `apt-get` سقفه الجداريّ مرّتين فسقطت الوظيفة. والحدُّ وحده يحوّل الحرق إلى
فشلٍ مُسمّى — وهو مكسبٌ حقيقيّ — لكنّه **لا يُنجِح التثبيت**. فأُضيف تراجعٌ متزايد
ومرآةٌ بديلة، وأُخرِج المنطق من ثلاث كتل `run:` متطابقة إلى سكربتٍ واحد يُختبَر.

يُزيَّف `sudo`/`apt-get` ويُسجَّل كلّ استدعاء، فيُقاس الفرعُ المُنفَّذ لا نصُّه.
"""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.security]

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "ci" / "resilient_apt_install.sh"


def _fake_bin(tmp_path: Path, *, succeed_on: int | None) -> Path:
    """`apt-get` مزيّف ينجح عند محاولةٍ بعينها (أو أبداً)، و`sudo` شفّاف يسجّل.

    العدّاد على `apt-get update` وحده: كلّ محاولة تبدأ به، فعدّه يعدّ المحاولات.
    """
    log = tmp_path / "calls.log"
    counter = tmp_path / "n"
    counter.write_text("0", encoding="utf-8")
    on = "" if succeed_on is None else str(succeed_on)

    apt = tmp_path / "apt-get"
    apt.write_text(
        "#!/usr/bin/env bash\n"
        f'echo "apt-get $*" >> "{log}"\n'
        'if [ "$1" = "update" ]; then\n'
        f'  n=$(cat "{counter}"); n=$((n + 1)); echo "$n" > "{counter}"\n'
        f'  [ -n "{on}" ] && [ "$n" -ge "{on}" ] && exit 0\n'
        "  exit 1\n"
        "fi\n"
        f'n=$(cat "{counter}")\n'
        f'[ -n "{on}" ] && [ "$n" -ge "{on}" ] && exit 0\n'
        "exit 1\n",
        encoding="utf-8",
    )
    apt.chmod(apt.stat().st_mode | stat.S_IEXEC)

    # `sudo` شفّاف: ينفّذ ما بعده ويسجّله. وبلاه يسقط السكربت على مُشغِّل بلا sudo.
    sudo = tmp_path / "sudo"
    sudo.write_text(
        f'#!/usr/bin/env bash\necho "sudo $*" >> "{log}"\nexec "$@"\n',
        encoding="utf-8",
    )
    sudo.chmod(sudo.stat().st_mode | stat.S_IEXEC)

    # `sed` مزيّف لا يلمس نظام الملفّات الحقيقيّ لو وُجِدت مصادر APT على المُشغِّل.
    sed = tmp_path / "sed"
    sed.write_text(
        f'#!/usr/bin/env bash\necho "sed $*" >> "{log}"\nexit 0\n',
        encoding="utf-8",
    )
    sed.chmod(sed.stat().st_mode | stat.S_IEXEC)
    return log


def _run(tmp_path: Path, **env_extra: str) -> tuple[subprocess.CompletedProcess, str]:
    env = os.environ.copy()
    env["PATH"] = f"{tmp_path}:{env['PATH']}"
    env.setdefault("APT_BACKOFF", "0")  # لا ننفق وقتاً حقيقيّاً على النوم
    env.setdefault("APT_SOURCE_FILES", _apt_sources(tmp_path))
    env.update(env_extra)
    proc = subprocess.run(
        ["bash", str(SCRIPT), "postgresql-client"],
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
    """عددُ المحاولات = أسطرُ `apt-get update` **المباشرة**.

    `sudo` المزيّف ينفّذ ما بعده، فكلّ استدعاء يظهر سطرين (الغلاف والمغلَّف).
    وعدُّ أيّ ذكرٍ يُعطي الضعف — أمسكه أوّل تشغيل، وهو صنف «قياسٌ يعدّ غير ما يدّعي».
    """
    return sum(1 for line in log.splitlines() if line.strip() == "apt-get update -qq")


def test_the_script_parses_as_bash():
    """سكربتٌ لا يبدأ أسوأ من غيابه: يُقرأ فشلُه عطلاً في APT لا في نفسه."""
    r = subprocess.run(
        ["bash", "-n", str(SCRIPT)], capture_output=True, text=True, encoding="utf-8"
    )
    assert r.returncode == 0, r.stderr


def test_a_first_attempt_success_neither_retries_nor_switches_the_mirror(tmp_path):
    """المسار السعيد لا يدفع ثمن العلاج: لا نوم، ولا مسّ لمصادر APT."""
    _fake_bin(tmp_path, succeed_on=1)
    proc, log = _run(tmp_path)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert _attempts(log) == 1, log
    assert "sed" not in log, "تبديل المرآة على نجاحٍ من أوّل محاولة تغييرٌ بلا سبب"


def test_a_transient_failure_is_retried_and_the_mirror_is_switched_first(tmp_path):
    """التبديل **قبل** النوم: النوم على مرآةٍ متعثّرة إنفاقُ وقتٍ على نفس الشرط."""
    _fake_bin(tmp_path, succeed_on=2)
    proc, log = _run(tmp_path)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert _attempts(log) == 2, log
    lines = log.splitlines()
    first_sed = next(i for i, x in enumerate(lines) if x.startswith("sed"))
    second_update = [i for i, x in enumerate(lines) if x.strip() == "apt-get update -qq"][1]
    assert first_sed < second_update, "المرآة تُبدَّل قبل المحاولة التالية لا بعدها"


def test_every_apt_invocation_is_wall_clock_bounded(tmp_path):
    """الحدّ الجداريّ هو ما حوّل ١١٢ دقيقة صامتة إلى فشلٍ يُقرأ — لا يسقط بالتوسعة."""
    _fake_bin(tmp_path, succeed_on=1)
    proc, log = _run(tmp_path)
    assert proc.returncode == 0
    for line in log.splitlines():
        if line.startswith("sudo ") and "apt-get" in line:
            assert "timeout -k 10" in line, f"استدعاء APT بلا سقف جداريّ: {line}"


def test_exhausting_every_attempt_fails_closed_with_a_named_error(tmp_path):
    """فشلٌ صامت يُقرأ عملاً جارياً؛ والاسم هو ما يجعل الأحمر قابلاً للقراءة."""
    _fake_bin(tmp_path, succeed_on=None)
    proc, log = _run(tmp_path, APT_ATTEMPTS="3")
    assert proc.returncode != 0
    assert _attempts(log) == 3, log
    assert "::error::" in proc.stderr, proc.stderr
    assert "مرآة بديلة" in proc.stderr, "الرسالة تقول ما جُرِّب، وإلّا أُعيد تجريبه"


def test_no_packages_requested_is_a_usage_error_not_a_silent_success(tmp_path):
    """استدعاءٌ بلا حِزَم يخرج بصفر يُقرأ «ثُبِّتت» وهو «لم يُطلَب شيء»."""
    _fake_bin(tmp_path, succeed_on=1)
    env = os.environ.copy()
    env["PATH"] = f"{tmp_path}:{env['PATH']}"
    proc = subprocess.run(
        ["bash", str(SCRIPT)], capture_output=True, text=True, encoding="utf-8", env=env
    )
    assert proc.returncode == 2, proc.stdout + proc.stderr


def test_the_three_workflow_sites_delegate_instead_of_duplicating(tmp_path):
    """ثلاث كتل متطابقة تنحرف عن بعضها عند أوّل تعديل — والانحراف صامت.

    وهذا هو الدرس المُسجَّل في `resilient_docker_pull.sh` نفسه، مُطبَّقاً على APT.
    """
    ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert ci.count("scripts/ci/resilient_apt_install.sh") == 3, (
        "المواضع الثلاثة تستدعي السكربت الواحد"
    )
    assert "apt-get install -y -qq postgresql-client && break" not in ci, (
        "الكتلة المكرّرة أُزيلت، وإلّا بقي مصدران للحقيقة"
    )


def test_the_mirror_switch_is_driven_by_injection_not_by_the_runner_filesystem(tmp_path):
    """العطل الذي أمسكه مراجعٌ خارجيّ: الاختبار كان يقيس البيئة لا السكربت.

    المسارات كانت مُصلَّبة في `switch_apt_mirror`، فإن غاب `/etc/apt` عن المُشغِّل لم
    يُستدعَ `sed` أصلاً وسقط تأكيدُ «تُبدَّل قبل النوم» — **بلا تغييرٍ في الشيفرة**.
    مرّ هنا لأنّ الملفّين موجودان، وسقط عنده لأنّهما ليسا كذلك. وهذا أسوأ من أحمر:
    أخضرٌ يعتمد على آلةٍ بعينها.

    يُقاس هنا الطرفان معاً — أنّ المحقون **يُحرَّر**، وأنّ الغياب **لا يُفشِل** (فالتبديل
    تحسينُ فرصةٍ لا شرطُ صحّة).
    """
    import os

    helper = ROOT / "scripts/ci/apt_mirror_fallback.sh"
    log = tmp_path / "calls.log"
    sed = tmp_path / "sed"
    sed.write_text(f'#!/usr/bin/env bash\necho "sed $*" >> "{log}"\nexit 0\n', encoding="utf-8")
    sed.chmod(sed.stat().st_mode | stat.S_IEXEC)
    sudo = tmp_path / "sudo"
    sudo.write_text('#!/usr/bin/env bash\nexec "$@"\n', encoding="utf-8")
    sudo.chmod(sudo.stat().st_mode | stat.S_IEXEC)

    probe = tmp_path / "probe.sh"
    probe.write_text(f'. "{helper}"\nswitch_apt_mirror\n', encoding="utf-8")
    env = os.environ.copy()
    env["PATH"] = f"{tmp_path}:{env['PATH']}"

    # ① مسارٌ محقونٌ **موجود** ⇒ يُحرَّر هو، ولا يُمَسّ نظام ملفّات المُشغِّل.
    injected = _apt_sources(tmp_path)
    env["APT_SOURCE_FILES"] = injected
    r = subprocess.run(
        ["bash", str(probe)], capture_output=True, text=True, encoding="utf-8", env=env
    )
    assert r.returncode == 0, r.stderr
    calls = log.read_text(encoding="utf-8")
    assert injected in calls, calls
    assert "/etc/apt" not in calls, "لا يُمَسّ نظام ملفّات المُشغِّل: المسار محقون"

    # ② مسارٌ محقونٌ **غائب** ⇒ صفرُ استدعاء، ورمزُ خروجٍ صفر: الغياب ليس فشلاً.
    log.unlink()
    env["APT_SOURCE_FILES"] = str(tmp_path / "لا-وجود-له.sources")
    r = subprocess.run(
        ["bash", str(probe)], capture_output=True, text=True, encoding="utf-8", env=env
    )
    assert r.returncode == 0, r.stderr
    assert not log.exists(), "ملفٌّ غائب لا يُستدعى له sed"

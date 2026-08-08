"""العقد التنفيذيّ لسحب الصور: **يفشل مغلقاً ولا يُكمِل**.

رسالةُ التزامٍ تقول «مقيسٌ بمحاكاة» ليست قياساً — والمالك ردّ التزامي بذلك: العيب
كان مُصلَحاً في الشيفرة بلا اختبارٍ يُثبِته. هذا الملفّ يُثبِته.

**ما يُقاس بالضبط:** بعد استنفاد المحاولات لا يكفي أن يعود رمزُ خروجٍ غير صفريّ —
يجب أن **لا يُنفَّذ ما بعده**. فالعطل الأصليّ لم يكن رمز خروج خاطئاً بل استمرارَ
التنفيذ إلى `docker run` برسالةٍ أغمض. لذلك يُزيَّف `docker` ويُسجَّل كلُّ استدعاء،
ثمّ يُؤكَّد أنّ السجلّ لا يحوي `run`.
"""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "ci" / "resilient_docker_pull.sh"


def _fake_docker(tmp_path: Path, *, pull_succeeds_on: int | None) -> tuple[Path, Path]:
    """‏`docker` مزيّف يسجّل كلّ استدعاء، وينجح عند محاولة بعينها أو لا ينجح أبداً."""
    log = tmp_path / "calls.log"
    counter = tmp_path / "count"
    counter.write_text("0", encoding="utf-8")
    succeed = "" if pull_succeeds_on is None else str(pull_succeeds_on)
    docker = tmp_path / "docker"
    docker.write_text(
        "#!/usr/bin/env bash\n"
        f'echo "$@" >> "{log}"\n'
        'if [ "$1" = "pull" ]; then\n'
        f'  n=$(cat "{counter}"); n=$((n + 1)); echo "$n" > "{counter}"\n'
        f'  [ -n "{succeed}" ] && [ "$n" = "{succeed}" ] && exit 0\n'
        "  exit 1\n"
        "fi\n"
        "exit 0\n",
        encoding="utf-8",
    )
    docker.chmod(docker.stat().st_mode | stat.S_IEXEC)
    return docker, log


def _run(tmp_path: Path, docker: Path, attempts: int = 3):
    """يستدعي السكربت ثمّ `docker run` **بالتسلسل تحت `set -e`** — كما في الوظيفة.

    لو أعاد السكربت صفراً خطأً، لَنُفِّذ `docker run` وظهر في السجلّ.
    """
    env = dict(os.environ, PATH=f"{docker.parent}:{os.environ['PATH']}")
    return subprocess.run(  # noqa: S603
        [
            "bash",
            "-c",
            f'set -e; "{SCRIPT}" some/image {attempts}; docker run -d --name x some/image',
        ],
        capture_output=True,
        encoding="utf-8",
        env=env,
        cwd=tmp_path,
    )


def test_exhausting_the_attempts_fails_and_does_not_reach_docker_run(tmp_path):
    """العقد الحاجب: استنفاد المحاولات ⇒ رمز خروج غير صفريّ **و**لا `docker run`."""
    docker, log = _fake_docker(tmp_path, pull_succeeds_on=None)
    proc = _run(tmp_path, docker, attempts=3)

    assert proc.returncode != 0, "استُنفِدت المحاولات ومع ذلك نجح — فشلٌ مفتوح"
    calls = log.read_text(encoding="utf-8").splitlines()
    assert calls == ["pull some/image"] * 3, calls
    assert not any(c.startswith("run") for c in calls), (
        "وصل التنفيذ إلى `docker run` بعد فشل السحب — وهو العطل الأصليّ بعينه"
    )
    assert "تعذّر سحب" in proc.stderr


def test_a_successful_retry_still_proceeds(tmp_path):
    """المرساة المقابلة: بلا هذا يمرّ سكربتٌ يفشل **دائماً** فيُعطَّل السحب كلّه."""
    docker, log = _fake_docker(tmp_path, pull_succeeds_on=2)
    proc = _run(tmp_path, docker, attempts=3)

    assert proc.returncode == 0, proc.stderr
    calls = log.read_text(encoding="utf-8").splitlines()
    assert calls[:2] == ["pull some/image"] * 2
    assert any(c.startswith("run") for c in calls), "نجح السحب ولم يُكمِل إلى `docker run`"


def test_no_backoff_sleep_after_the_final_attempt(tmp_path):
    """ملاحظة المالك غير الحاجبة، مقيسة: ٦٠ ثانية بعد المحاولة الأخيرة نفقةٌ بلا مقابل.

    القياس زمنيّ لا نصّيّ: `sleep` بعد الأخيرة كان سيجعل ثلاث محاولات تتجاوز ٣٠ث
    (10+20+30)، وبدونها تبقى دون ذلك بكثير.
    """
    docker, _ = _fake_docker(tmp_path, pull_succeeds_on=None)
    proc = subprocess.run(  # noqa: S603
        ["bash", "-c", f'"{SCRIPT}" some/image 1'],
        capture_output=True,
        encoding="utf-8",
        env=dict(os.environ, PATH=f"{docker.parent}:{os.environ['PATH']}"),
        timeout=5,
    )
    assert proc.returncode != 0
    assert "backoff" not in proc.stderr, "نام بعد المحاولة الأخيرة"


def test_the_workflow_calls_the_script_rather_than_inlining_the_loop():
    """السكربت المُختبَر لا ينفع إن بقيت الوظيفة تحمل نسختها الخاصّة من الحلقة."""
    ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    job = ci[ci.index("live-pg-fake-connection-proofs:") : ci.index("  security-scan:")]
    assert "scripts/ci/resilient_docker_pull.sh" in job, "الوظيفة لا تستدعي السكربت المُختبَر"
    assert "docker pull" not in job, "ما زالت الوظيفة تحمل حلقة سحبٍ خاصّة غير مُختبَرة"

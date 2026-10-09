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
POSTGIS_BUILDER = ROOT / "scripts" / "ci" / "build_postgis_test_image.sh"


def _fake_docker(
    tmp_path: Path,
    *,
    pull_succeeds_on: int | None,
) -> tuple[Path, Path]:
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
        '  if [ -n "${FAKE_DOCKER_PULL_ERROR:-}" ]; then echo "$FAKE_DOCKER_PULL_ERROR" >&2; fi\n'
        f'  n=$(cat "{counter}"); n=$((n + 1)); echo "$n" > "{counter}"\n'
        f'  [ -n "{succeed}" ] && [ "$n" = "{succeed}" ] && exit 0\n'
        "  exit 1\n"
        "fi\n"
        'if [ "$1" = "build" ]; then cat > "$FAKE_DOCKERFILE_OUT"; exit 0; fi\n'
        "exit 0\n",
        encoding="utf-8",
    )
    docker.chmod(docker.stat().st_mode | stat.S_IEXEC)
    return docker, log


def _run(tmp_path: Path, docker: Path, attempts: int = 3, **extra_env: str):
    """يستدعي السكربت ثمّ `docker run` **بالتسلسل تحت `set -e`** — كما في الوظيفة.

    لو أعاد السكربت صفراً خطأً، لَنُفِّذ `docker run` وظهر في السجلّ.
    """
    fast_bin = tmp_path / "fast-bin"
    fast_bin.mkdir(exist_ok=True)
    sleep = fast_bin / "sleep"
    sleep.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    sleep.chmod(sleep.stat().st_mode | stat.S_IEXEC)
    env = dict(
        os.environ,
        PATH=f"{fast_bin}:{docker.parent}:{os.environ['PATH']}",
        **extra_env,
    )
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
    """ملاحظة المالك غير الحاجبة، مقيسة: لا نوم بعد المحاولة الأخيرة."""
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


def test_rate_limit_stops_retrying_and_records_invalid_harness_cause(tmp_path):
    docker, log = _fake_docker(
        tmp_path,
        pull_succeeds_on=None,
    )
    cause_file = tmp_path / "primary-cause.txt"
    proc = _run(
        tmp_path,
        docker,
        attempts=6,
        FAKE_DOCKER_PULL_ERROR=(
            "toomanyrequests: You have reached your unauthenticated pull rate limit"
        ),
        HARNESS_PRIMARY_CAUSE_FILE=str(cause_file),
    )

    assert proc.returncode != 0
    assert log.read_text(encoding="utf-8").splitlines() == ["pull some/image"]
    assert "failure_class=RATE_LIMIT" in proc.stderr
    assert "database_state=NOT_STARTED" in proc.stderr
    assert "evidence_state=HARNESS_INVALID" in proc.stderr
    assert cause_file.read_text(encoding="utf-8").strip() == "DOCKER_IMAGE_PULL_FAILED"
    assert "backoff" not in proc.stderr


@pytest.mark.parametrize(
    ("error", "failure_class"),
    [
        (
            "Get https://auth.docker.io/token: context deadline exceeded",
            "AUTH_TIMEOUT",
        ),
        ("registry returned 503 Service Unavailable", "REGISTRY_5XX"),
    ],
)
def test_pull_failure_classes_are_reported(tmp_path, error, failure_class):
    docker, _ = _fake_docker(tmp_path, pull_succeeds_on=None)
    proc = _run(
        tmp_path,
        docker,
        attempts=1,
        FAKE_DOCKER_PULL_ERROR=error,
    )

    assert proc.returncode != 0
    assert f"failure_class={failure_class}" in proc.stderr


def test_postgis_image_is_built_from_pinned_postgres_and_signed_packages(tmp_path):
    base_image = (
        "public.ecr.aws/docker/library/postgres@"
        "sha256:ca0bd484cb98bf4b24eb1010e73fb3fcbd6714d240fbc1a10eea5b7dbecb641d"
    )
    docker, log = _fake_docker(tmp_path, pull_succeeds_on=1)
    dockerfile = tmp_path / "Dockerfile"
    env = dict(
        os.environ,
        PATH=f"{docker.parent}:{os.environ['PATH']}",
        FAKE_DOCKERFILE_OUT=str(dockerfile),
    )
    proc = subprocess.run(  # noqa: S603
        ["bash", str(POSTGIS_BUILDER), base_image, "16", "sahool-postgis:ci"],
        capture_output=True,
        encoding="utf-8",
        env=env,
        cwd=ROOT,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert log.read_text(encoding="utf-8").splitlines() == [
        f"pull {base_image}",
        "build --pull=false --tag sahool-postgis:ci -",
    ]
    build_instructions = dockerfile.read_text(encoding="utf-8")
    assert f"FROM {base_image}" in build_instructions
    assert "postgresql-16-postgis-3" in build_instructions
    assert "postgresql-16-postgis-3-scripts" in build_instructions


def test_the_workflow_calls_the_script_rather_than_inlining_the_loop():
    """السكربت المُختبَر لا ينفع إن بقيت الوظيفة تحمل نسختها الخاصّة من الحلقة."""
    ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    job = ci[ci.index("live-pg-fake-connection-proofs:") : ci.index("  security-scan:")]
    assert "scripts/ci/build_postgis_test_image.sh" in job
    builder = (ROOT / "scripts/ci/build_postgis_test_image.sh").read_text(encoding="utf-8")
    assert "scripts/ci/resilient_docker_pull.sh" in builder
    assert "docker pull" not in job, "ما زالت الوظيفة تحمل حلقة سحبٍ خاصّة غير مُختبَرة"

"""عقد توفير عميل PostgreSQL: **من صورة الخادم، لا من مرآة Ubuntu**.

العطل الذي يوجد هذا الملفّ لأجله مقيس مرّتين في تشغيلٍ واحد (32274613475):
`apt-get` تجمّد ثلاث محاولاتٍ مع تبديل مرآة، فلم يُثبَّت `postgresql-client`،
فغاب `psql`، فلم تعمل خطوة إنشاء `sahool_app`، فطبع حارس الإغلاق
``RESTRICTED_ROLE_NOT_FOUND`` — **رسالةٌ عن schema عن قاعدةٍ لم تُقَس أصلاً**.

فالمقيس هنا ثلاثة أشياء لا واحد:
  ① لا يُلمَس apt ولا الشبكة الخارجيّة — الأداة تُشتقّ من الحاوية القائمة.
  ② حاويةٌ غير قائمة تُفشِل التوفير **فوراً**، ولا تترك غلافاً يفشل لاحقاً بغموض.
  ③ الغلاف يترجم `-h/-p` إلى داخل الحاوية، فتبقى نداءات `-h localhost -p <port>`
     القائمة في الـworkflow صحيحةً بلا تعديل موضع استدعاء.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "ci" / "provision_pg_client.sh"


def _fake_docker(tmp_path: Path, *, running: bool) -> Path:
    log = tmp_path / "calls.log"
    docker = tmp_path / "docker"
    docker.write_text(
        "#!/usr/bin/env bash\n"
        f'echo "$@" >> "{log}"\n'
        'if [ "$1" = "inspect" ]; then\n'
        f'  echo "{str(running).lower()}"\n'
        f"  exit {0 if running else 1}\n"
        "fi\n"
        "exit 0\n",
        encoding="utf-8",
    )
    docker.chmod(0o755)
    return log


def _run(tmp_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = {
        "PATH": f"{tmp_path}:/usr/bin:/bin",
        "RUNNER_TEMP": str(tmp_path / "runner"),
        "HOME": str(tmp_path),
    }
    return subprocess.run(
        ["bash", str(SCRIPT), *args], capture_output=True, text=True, env=env, cwd=tmp_path
    )


def test_the_client_is_derived_from_the_container_and_never_from_apt(tmp_path):
    log = _fake_docker(tmp_path, running=True)
    result = _run(tmp_path, "sahool-pg16", "5435")
    assert result.returncode == 0, result.stderr
    calls = log.read_text(encoding="utf-8")
    # القرار كلّه محلّيّ: فحصُ حالة الحاوية فقط، بلا تنزيلٍ ولا مرآة.
    assert "inspect" in calls
    assert "pull" not in calls
    for tool in ("psql", "pg_isready"):
        shim = tmp_path / "runner" / "pg-client-shims" / tool
        assert shim.is_file() and shim.stat().st_mode & 0o111, f"{tool} لم يُركَّب"
        body = shim.read_text(encoding="utf-8")
        assert "docker exec" in body
        assert "apt" not in body


def test_a_container_that_is_not_running_fails_provisioning_immediately(tmp_path):
    """وإلّا رُكِّب غلافٌ يفشل لاحقاً برسالةٍ لا تسمّي سببها."""
    _fake_docker(tmp_path, running=False)
    result = _run(tmp_path, "sahool-pg16", "5435")
    assert result.returncode != 0
    assert "sahool-pg16" in result.stdout + result.stderr
    assert not (tmp_path / "runner" / "pg-client-shims" / "psql").exists()


@pytest.mark.parametrize(
    "argv",
    [
        ["-h", "localhost", "-p", "5435", "-U", "sahool_user", "-qAtc", "select 1"],
        ["--host=localhost", "--port=5435", "-d", "sahool"],
        ["-hlocalhost", "-p5435", "-d", "sahool"],
    ],
)
def test_host_and_port_are_translated_into_the_container(tmp_path, argv):
    """الغلاف يبتلع عنوان المضيف ومنفَذه ويستبدلهما بعنوان الحاوية الداخليّ.

    لولا ذلك لَحاول `psql` داخل الحاوية الاتّصال بـ`localhost:5435` وهو منفَذ
    المضيف المنشور، فيفشل الاتّصال ويُقرأ العطل «قاعدة البيانات لا تستجيب».
    """
    log = _fake_docker(tmp_path, running=True)
    assert _run(tmp_path, "sahool-pg16", "5435").returncode == 0
    shim = tmp_path / "runner" / "pg-client-shims" / "psql"
    log.write_text("", encoding="utf-8")
    subprocess.run(
        [str(shim), *argv],
        capture_output=True,
        text=True,
        env={"PATH": f"{tmp_path}:/usr/bin:/bin", "PGPASSWORD": "x"},
    )
    forwarded = log.read_text(encoding="utf-8").strip()
    assert "-h 127.0.0.1 -p 5432" in forwarded
    assert "5435" not in forwarded, "منفَذ المضيف تسرّب إلى داخل الحاوية"


def test_the_workflow_no_longer_provisions_the_client_through_apt():
    """العقد على الـworkflow نفسها: لا عودة صامتة إلى المسار الذي سقط مقيساً."""
    ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "resilient_apt_install.sh postgresql-client" not in ci
    assert ci.count("provision_pg_client.sh") == 3

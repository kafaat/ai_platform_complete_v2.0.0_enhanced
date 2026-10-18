"""تدقيقُ الأمن يرفض كلَّ وضعِ TLS لقاعدة البيانات أضعفَ من ``verify-full`` — بلا استثناء.

العطلُ الذي وُجِد لأجله هذا الملفّ: مُصدِّرُ المقاييس كان يحتاج ``sslmode=disable`` صراحةً
(Postgres في v9 بلا TLS، وسائقُه ``lib/pq`` يعدّ الفارغ ``require``)، فأُضيف له استثناءٌ في
``scripts/security_audit.sh`` وحرسه هذا الملفّ من الاتّساع. والقاعدةُ نفسُها كانت لا تلتقط إلّا
**التصريح** بـ``disable`` — فتُعاقب مَن يقول الحقيقة وتُجيز ``prefer`` الضمنيّ لكلّ عميلٍ آخر.

POSTGRES-V9-HAS-NO-TLS-SO-EVERY-CLIENT-IS-PLAINTEXT-01 أُغلِق: الخادمُ يُلزِم TLS وكلُّ عميلٍ
``verify-full``، فنُزِع الاستثناء. هنا يُشغَّل التدقيقُ **الحقيقيّ** على شجرةٍ مؤقّتة: سطرُ
المُصدِّر القديم صار يُفشِله، وكذلك كلُّ وضعٍ أضعف (disable/allow/prefer تسقط إلى النصّ، وrequire
يقبل خادماً منتحَلاً)، بينما ``verify-full`` يمرّ — والشجرةُ الحقيقيّة نفسُها تمرّ.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
AUDIT = ROOT / "scripts" / "security_audit.sh"
#: سطرُ المُصدِّر **كما كان مُستثنى** على main@0e5281614 — المرساةُ على الحادثة لا على الشجرة.
FORMER_EXPORTER_LINE = "      DATA_SOURCE_URI: sahool-postgres:5432/sahool?sslmode=disable\n"
VERIFY_FULL_LINE = (
    "      DATA_SOURCE_URI: sahool-postgres:5432/sahool?sslmode=verify-full"
    "&sslrootcert=/etc/sahool/postgres-ca/ca.pem\n"
)

pytestmark = [pytest.mark.unit]


def _run(tmp_path: Path, compose_text: str) -> subprocess.CompletedProcess[str]:
    (tmp_path / "scripts").mkdir()
    shutil.copy(AUDIT, tmp_path / "scripts" / "security_audit.sh")
    (tmp_path / "docker-compose.v9.yml").write_text(compose_text, encoding="utf-8")
    (tmp_path / ".env.example").write_text("POSTGRES_USER=sahool_user\n", encoding="utf-8")
    return subprocess.run(
        ["bash", str(tmp_path / "scripts" / "security_audit.sh")],
        cwd=tmp_path,
        env={"ROOT": str(tmp_path), "PATH": "/usr/bin:/bin"},
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def _tls_line(out: str) -> str:
    return next(line for line in out.splitlines() if "disabled database TLS" in line)


def test_the_formerly_excepted_exporter_line_now_fails(tmp_path):
    result = _run(tmp_path, "services:\n  x:\n    environment:\n" + FORMER_EXPORTER_LINE)
    assert _tls_line(result.stdout).startswith("FAIL:"), result.stdout
    assert result.returncode != 0


def test_verify_full_passes(tmp_path):
    result = _run(tmp_path, "services:\n  x:\n    environment:\n" + VERIFY_FULL_LINE)
    assert _tls_line(result.stdout).startswith("OK:"), result.stdout


@pytest.mark.parametrize(
    "line",
    [
        "      DATABASE_URL: postgresql://sahool_app:x@sahool-postgres:5432/sahool?sslmode=disable\n",
        "      DATABASE_URL: postgresql://sahool_app:x@sahool-postgres:5432/sahool?sslmode=prefer\n",
        "      DATABASE_URL: postgresql://a:x@sahool-postgres:5432/sahool?sslmode=require&x=1\n",
        "      DATA_SOURCE_URI: other-db:5432/sahool?sslmode=allow\n",
        "      PGSSLMODE_URL: host=sahool-postgres sslmode=disable\n",
    ],
)
def test_any_mode_weaker_than_verify_full_fails(tmp_path, line):
    result = _run(tmp_path, "services:\n  x:\n    environment:\n" + VERIFY_FULL_LINE + line)
    assert _tls_line(result.stdout).startswith("FAIL:"), result.stdout
    assert result.returncode != 0


def test_the_audit_carries_no_exception_for_the_tls_rule():
    rule = next(
        line
        for line in AUDIT.read_text(encoding="utf-8").splitlines()
        if line.startswith("fail_if_hits 'sslmode=")
    )
    assert rule.count("' '") == 1, (
        f"قاعدةُ TLS عادت تحمل وسيطاً ثالثاً (استثناء) — كلُّ وضعٍ أضعف من verify-full يُرفَض: {rule}"
    )


def test_the_real_tree_passes_the_tls_rule():
    result = subprocess.run(
        ["bash", str(AUDIT)], cwd=ROOT, capture_output=True, text=True, encoding="utf-8"
    )
    assert _tls_line(result.stdout).startswith("OK:"), result.stdout

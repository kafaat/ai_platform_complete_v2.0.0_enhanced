"""استثناءُ `sslmode=disable` في تدقيق الأمن محصورٌ في سطر مُصدِّر Postgres وحده.

العطلُ الذي وُجِد لأجله: مُصدِّرُ المقاييس يحتاج `sslmode=disable` صراحةً (سائقُه `lib/pq`
يعدّ الفارغ `require`)، فأُضيف له استثناءٌ في `scripts/security_audit.sh`. والخطرُ أن يتّسع
الاستثناءُ صامتاً فيقبل `sslmode=disable` في أيّ DATABASE_URL. هذا الاختبار يُشغّل التدقيقَ
الحقيقيّ على شجرةٍ مؤقّتة: سطرُ المُصدِّر وحده يمرّ، وأيُّ ظهورٍ آخرَ يُفشِله.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
AUDIT = ROOT / "scripts" / "security_audit.sh"
EXPORTER_LINE = "      DATA_SOURCE_URI: sahool-postgres:5432/sahool?sslmode=disable\n"


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


def test_the_exporter_line_alone_passes(tmp_path):
    result = _run(tmp_path, "services:\n  x:\n    environment:\n" + EXPORTER_LINE)
    assert _tls_line(result.stdout).startswith("OK:"), result.stdout


@pytest.mark.parametrize(
    "line",
    [
        "      DATABASE_URL: postgresql://sahool_app:x@sahool-postgres:5432/sahool?sslmode=disable\n",
        "      DATA_SOURCE_URI: other-db:5432/sahool?sslmode=disable\n",
        "      PGSSLMODE_URL: host=sahool-postgres sslmode=disable\n",
    ],
)
def test_any_other_disabled_tls_still_fails(tmp_path, line):
    result = _run(tmp_path, "services:\n  x:\n    environment:\n" + EXPORTER_LINE + line)
    assert _tls_line(result.stdout).startswith("FAIL:"), result.stdout
    assert result.returncode != 0

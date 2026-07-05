"""حارس: منظومتا الترحيل (MANIFEST.txt + scripts_v9/run_migrations.sql) متطابقتان.

بوّابة الإنتاج (production_validation_gate) تفشل إن نقص ملفّ من run_migrations.sql —
حدث مع v142 (أُضيف لـMANIFEST دون run_migrations.sql). هذا الحارس unit يلتقطه محلّيّاً
قبل CI/البوّابة كي لا يتكرّر: كلّ إدخال MANIFEST أماميّ يجب أن يُضمَّن في run_migrations.sql.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[1]
MANIFEST = REPO / "migrations" / "MANIFEST.txt"
RUN_SQL = REPO / "scripts_v9" / "run_migrations.sql"


def _manifest_forward() -> list[str]:
    out = []
    for raw in MANIFEST.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.endswith(".sql") and not line.endswith(".down.sql"):
            out.append(line)
    return out


def test_every_manifest_migration_is_in_run_migrations_sql():
    run = RUN_SQL.read_text(encoding="utf-8")
    missing = [m for m in _manifest_forward() if m not in run]
    assert not missing, (
        "ترحيلات في MANIFEST لكن غائبة عن scripts_v9/run_migrations.sql (تُفشِل بوّابة "
        f"الإنتاج): {missing}"
    )

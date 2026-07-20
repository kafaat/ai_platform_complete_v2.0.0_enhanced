"""حارس ساكن (مُنفَّذ في CI): فصل فضاءَي ترقيم نظامَي الهجرة — MIGRATE-ID-COLLISION مُغلَق.

التصادم القديم (تدقيق 2026-07-20): ملفّان في ``alembic/versions/`` أعادا استعمال أرقام ``vNNN``
المملوكة لـ``migrations/`` — ``v101_field_runtime_cohesion.sql`` (بينما migrations/v101 =
farm_budget_costing) و``v105_marketplace_ecosystem.sql`` (marketplace canonical = migrations/v121) —
فصار «نفس الرقم، ملفّان مختلفان لكلّ نظام»: قنبلة صامتة (غموض «vNNN applied»/rollback/مطابقة بيئات).
الملفّان كانا ميّتَين (خارج سلسلة مراجعات alembic 0001→0002 · لا مُشغّل يطبّقهما · صفر استعمال
لجداولهما) فأُزيلا. **هذا الحارس يمنع الانحدار** بفرض فضاءَين منفصلَين:

  • ``alembic/versions/`` = مراجعات alembic الأصليّة ``NNNN_*.py`` حصراً — **لا** ``vNNN_*.sql``.
  • ``migrations/``       = هجرات ``vNNN_*.sql`` حصراً — **لا** مراجعات alembic ``NNNN_*.py``.

ملاحظة موضع: ملفّ حارس شقيق يوجد في ``tests/migrations/`` (توثيقيّ)، لكنّ ذلك المسار خارج
``testpaths = tests_v9`` فلا يشغّله CI؛ لذا النسخة **المُنفَّذة** هنا (مُعلَّمة ``unit``).

فحص ساكن صرف — ``pytest -m unit`` (لا قاعدة/شبكة).
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[1]


def _stray_vnnn_sql_in_alembic(versions_dir: Path) -> list[str]:
    """يعيد أسماء أيّ ملفّات ``vNNN_*.sql`` داخل مجلّد مراجعات alembic (يجب أن تكون فارغة)."""
    return sorted(p.name for p in versions_dir.glob("v*.sql"))


def test_alembic_versions_has_no_vnnn_sql_files() -> None:
    """alembic/versions/ يملك فضاء ``NNNN_*.py`` وحده — أيّ ``vNNN_*.sql`` يعيد التصادم."""
    versions = _ROOT / "alembic" / "versions"
    if not versions.is_dir():
        pytest.skip("alembic/versions غير موجود")
    stray = _stray_vnnn_sql_in_alembic(versions)
    assert stray == [], (
        "alembic/versions/ يجب ألّا يحوي ملفّات vNNN_*.sql (فضاء migrations/): "
        f"{stray} — يعيد تصادم معرّفات الهجرة عبر النظامين (MIGRATE-ID-COLLISION)."
    )


def test_migrations_dir_has_no_alembic_nnnn_py_revisions() -> None:
    """migrations/ يملك فضاء ``vNNN_*.sql`` وحده — لا مراجعات alembic ``NNNN_*.py`` مدسوسة فيه."""
    migrations = _ROOT / "migrations"
    stray = sorted(p.name for p in migrations.glob("[0-9][0-9][0-9][0-9]_*.py"))
    assert stray == [], f"migrations/ يجب ألّا يحوي مراجعات alembic NNNN_*.py: {stray}"


def test_negative_proof_guard_catches_a_planted_zombie(tmp_path: Path) -> None:
    """برهان سلبيّ: زرع ``vNNN_*.sql`` اصطناعيّ في مجلّد alembic-شبيه يقلب منطق الحارس أحمر.

    يمنع أن يمرّ الحارس **فراغاً** (vacuously): لو كان المنطق معطوباً لَما التقط الزومبيّ.
    """
    fake_versions = tmp_path / "alembic" / "versions"
    fake_versions.mkdir(parents=True)
    (fake_versions / "0001_baseline.py").write_text(
        "revision = '0001_baseline'\n", encoding="utf-8"
    )
    (fake_versions / "v105_marketplace_ecosystem.sql").write_text(
        "CREATE TABLE zombie(id int);\n", encoding="utf-8"
    )
    assert _stray_vnnn_sql_in_alembic(fake_versions) == ["v105_marketplace_ecosystem.sql"], (
        "منطق الحارس يجب أن يلتقط ملفّ vNNN_*.sql الاصطناعيّ (وإلّا الحارس بلا قيمة)"
    )

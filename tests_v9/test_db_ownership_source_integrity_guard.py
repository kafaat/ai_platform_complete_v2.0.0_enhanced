"""حارس ساكن (يُنفَّذ في CI ضمن tests_v9): سلامة مراجع ``source:`` في db_ownership.yml.

الفجوة المُغلَقة (تدقيق 2026-08-04): حارس فضاء الترقيم
(test_migration_id_namespace_separation_guard.py) حذف ملفّي
``alembic/versions/v101_field_runtime_cohesion.sql`` و``v105_marketplace_ecosystem.sql``
كملفّين ميّتين — لكن ``docs/architecture/db_ownership.yml`` بقي يستشهد بهما كـ``source``
لعشرة جداول. والأدهى أنّ ثلاثة منها (canonical_field_state_snapshots و
field_digital_twin_views وrecommendation_lifecycle_events) لا يوجد لها أيّ ملفّ إنشاء
في المستودع كلّه: جداول «شبح» سجّلها ملفٌّ زومبيّ محذوف، ومالكها المُعلَن
(raster-service / field-management-service / agriai-engine) لا ينشئها ولا يعرفها.
الحارس القديم يفحص محتوى المجلّدات فقط، لا مراجع YAML — فمرّ الانحراف بلا التقاط.

هذا الحارس يفرض: كلّ مسار مذكور في ``source:`` يجب أن يشير إلى ملفٍّ موجود فعلاً
في المستودع (مسار نسبيّ من الجذر). فحص ساكن صرف — ``pytest -m unit`` (لا قاعدة/شبكة).
التحليل سطريّ بلا اعتماد YAML خارجيّ (نفس اتفاق db_ownership.yml الموثّق في ترويسته).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[1]
_OWNERSHIP = _ROOT / "docs" / "architecture" / "db_ownership.yml"

_TABLE_RE = re.compile(r"^  (\S+):\s*$")
_SOURCE_RE = re.compile(r'^\s+source:\s*"(?P<src>[^"]+)"\s*$')


def _extract_sources(text: str) -> dict[str, list[str]]:
    """يعيد {اسم_الجدول: [مسارات source]}. تحليل سطريّ متعمّد — لا PyYAML."""
    sources: dict[str, list[str]] = {}
    current: str | None = None
    for line in text.splitlines():
        m = _TABLE_RE.match(line)
        if m:
            current = m.group(1)
            continue
        s = _SOURCE_RE.match(line)
        if s and current:
            paths = [p.strip() for p in s.group("src").split(",") if p.strip()]
            sources[current] = paths
    return sources


def _missing_sources(text: str, root: Path) -> dict[str, list[str]]:
    """يعيد الجداول ذات المسارات غير الموجودة — يجب أن تكون فارغة دائماً."""
    missing: dict[str, list[str]] = {}
    for table, paths in _extract_sources(text).items():
        dead = [p for p in paths if not (root / p).is_file()]
        if dead:
            missing[table] = dead
    return missing


def test_every_source_path_in_db_ownership_exists() -> None:
    """كلّ ``source:`` في db_ownership.yml يشير إلى ملفٍّ موجود — لا مراجع شبح."""
    if not _OWNERSHIP.is_file():
        pytest.skip("db_ownership.yml غير موجود")
    missing = _missing_sources(_OWNERSHIP.read_text(encoding="utf-8"), _ROOT)
    assert missing == {}, (
        "مراجع source: ميّتة في db_ownership.yml (الملفّ غير موجود في المستودع): "
        f"{missing} — صحّح المسار إلى الملفّ القانونيّ أو احذف القيد إن كان الجدول "
        "لا يُنشأ أصلاً (جدول شبح سجّله مصدر محذوف)."
    )


def test_no_table_without_any_source() -> None:
    """كلّ جدول مُسجَّل له ``source:`` واحد على الأقلّ — لا ملكيّة بلا أصل."""
    if not _OWNERSHIP.is_file():
        pytest.skip("db_ownership.yml غير موجود")
    text = _OWNERSHIP.read_text(encoding="utf-8")
    tables = [m.group(1) for m in map(_TABLE_RE.match, text.splitlines()) if m]
    sourced = set(_extract_sources(text))
    orphans = sorted(set(tables) - sourced)
    assert orphans == [], f"جداول في db_ownership.yml بلا source: إطلاقاً: {orphans}"


def test_negative_proof_guard_catches_a_planted_ghost(tmp_path: Path) -> None:
    """برهان سلبيّ: زرع مصدر وهميّ يقلب منطق الحارس أحمر — وإلّا فهو بلا قيمة."""
    (tmp_path / "migrations").mkdir()
    (tmp_path / "migrations" / "v1_real.sql").write_text("SELECT 1;", encoding="utf-8")
    text = (
        "tables:\n"
        "  real_table:\n"
        '    source: "migrations/v1_real.sql"\n'
        "  ghost_table:\n"
        '    source: "migrations/v1_real.sql, alembic/versions/v999_deleted.sql"\n'
    )
    missing = _missing_sources(text, tmp_path)
    assert missing == {"ghost_table": ["alembic/versions/v999_deleted.sql"]}, (
        "منطق الحارس يجب أن يلتقط المسار الوهميّ المزروع وينسبه لجدوله بالضبط"
    )

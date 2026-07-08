"""حارس ساكن — v152: إيقاف recommendation_feedback الميّت (جسر #4) + منع إحيائه صامتاً.

يوثّق القرار كشيفرة: الجدول مُعطَّل بتعليق يوجّه للمسارات المرجعيّة، ولا كاتب في الكود
(لو أُضيف كاتب مستقبلاً بلا مراجعة، يكشفه هذا الحارس — يُعيد تجزئة النتائج التي حلّها جسر #3).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
MIG = ROOT / "migrations" / "v152_deprecate_recommendation_feedback.sql"


def test_migration_exists_and_deprecates():
    sql = MIG.read_text(encoding="utf-8")
    assert "COMMENT ON TABLE recommendation_feedback" in sql
    assert "DEPRECATED" in sql
    # يوجّه للمسارات المرجعيّة الحيّة الثلاث.
    assert "recommendation_outcomes" in sql
    assert "farm_operations_ledger" in sql
    assert "water_ledger" in sql
    # لا DROP (سلامة بيانات) — تعليق فقط.
    assert "DROP TABLE" not in sql.upper()


def test_registered_in_both_runners():
    manifest = (ROOT / "migrations" / "MANIFEST.txt").read_text(encoding="utf-8")
    runner = (ROOT / "scripts_v9" / "run_migrations.sql").read_text(encoding="utf-8")
    assert "v152_deprecate_recommendation_feedback.sql" in manifest
    assert "v152_deprecate_recommendation_feedback.sql" in runner


def test_recommendation_feedback_stays_unwritten():
    """صدق: لا يُضاف كاتب INSERT لـrecommendation_feedback (يُعيد تجزئة النتائج).

    يمسح كود المنصّة والوكلاء؛ التغذية الراجعة الدائمة تمرّ عبر recommendation_outcomes.
    """
    write_re = re.compile(r"INSERT\s+INTO\s+recommendation_feedback\b", re.IGNORECASE)
    offenders = []
    for base in ("services",):
        for p in (ROOT / base).rglob("*.py"):
            if "test" in p.name:
                continue
            try:
                if write_re.search(p.read_text(encoding="utf-8", errors="replace")):
                    offenders.append(str(p.relative_to(ROOT)))
            except OSError:
                continue
    assert offenders == [], (
        "recommendation_feedback مُعطَّل (v152) — لا تُضِف كاتباً؛ استخدم "
        f"recommendation_outcomes/farm_operations_ledger/water_ledger. المخالفون: {offenders}"
    )

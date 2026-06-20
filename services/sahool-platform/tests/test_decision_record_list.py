"""اختبار نقاط القراءة/التدقيق لسلسلة النَّسَب المُدامة (سرد القرارات + سلسلة الحقل).

يثبت **التوصيل** و**نقاوة التجميع** دون قاعدة (مسار القراءة نفسه تكامليّ، يتطلّب
Postgres — كـdecision_dispatch). يغطّي ما يُختبَر وحدويّاً بصدق:

  • توصيل الموجِّه: نقطتا القراءة مُضمَّنتان في التطبيق بفعل GET.
  • نقاوة `_group_outcomes_by_decision` (تجميع تحت القرار، كشف orphan_outcomes).

الصدق: لا يدّعي اختبار قراءة DB هنا (لا Postgres في الوحدة) — يقتصر على ما يُتحقَّق
حتميّاً. مسار القراءة يطبّقه CI Integration كبقيّة نقاط tenant_connection.
"""

import api.main  # noqa: F401 — تهيئة api.main قبل استيراد الموجِّه
import pytest
from api.routers.decision_record import _group_outcomes_by_decision

pytestmark = pytest.mark.unit


def test_list_endpoints_wired():
    """نقطتا القراءة مُضمَّنتان في التطبيق بفعلها الصحيح (GET)."""
    routes = {(r.path, m) for r in api.main.app.routes for m in getattr(r, "methods", set())}
    assert ("/api/v1/decision/records", "GET") in routes
    assert ("/api/v1/field/{field_id}/lineage", "GET") in routes


def _orow(outcome_id, decision_id):
    """صفّ outcome_record صناعيّ بحدّ أدنى من حقول _shape_outcome_row (JSONB كنصّ خام)."""
    return {
        "outcome_id": outcome_id,
        "decision_id": decision_id,
        "field_id": "f1",
        "region": "r1",
        "stage": "outcome",
        "planned": None,
        "actual": None,
        "metrics": None,
        "success": None,
        "created_by": "u1",
        "created_at": None,
    }


def test_group_outcomes_under_their_decisions():
    """تُجمَع النتائج تحت قراراتها بمطابقة decision_id (نقيّاً)."""
    orows = [_orow("o1", "d1"), _orow("o2", "d1"), _orow("o3", "d2")]
    grouped, orphans = _group_outcomes_by_decision(["d1", "d2"], orows)
    assert orphans == []
    assert [o["outcome_id"] for o in grouped["d1"]] == ["o1", "o2"]
    assert [o["outcome_id"] for o in grouped["d2"]] == ["o3"]


def test_decision_without_outcomes_gets_empty_list():
    """قرار مُدام بلا نتائج ⇒ قائمة فارغة (لا مفتاح مفقود)."""
    grouped, orphans = _group_outcomes_by_decision(["d1"], [])
    assert grouped == {"d1": []}
    assert orphans == []


def test_orphan_outcomes_exposed_not_hidden():
    """نتيجة لقرار غير مُدام (decision_id خارج drows) ⇒ تُكشَف تحت orphans لا تُخفى."""
    orows = [_orow("o1", "d1"), _orow("o9", "ghost")]
    grouped, orphans = _group_outcomes_by_decision(["d1"], orows)
    assert [o["outcome_id"] for o in grouped["d1"]] == ["o1"]
    assert [o["outcome_id"] for o in orphans] == ["o9"]

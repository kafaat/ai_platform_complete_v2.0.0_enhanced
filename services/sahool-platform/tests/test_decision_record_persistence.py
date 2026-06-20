"""اختبار إدامة سلسلة النَّسَب (Decision→Outcome persistence — P0-1/P0-3).

يثبت **بنية** مسار الإدامة دون قاعدة (مسار الكتابة نفسه تكامليّ، يتطلّب Postgres —
كـdecision_dispatch). يغطّي ما يُختبَر وحدويّاً بصدق:

  • تسجيل نوعَي الحدث الجديدين في EventType + event_catalog (الاسم/القيمة/الفئة).
  • نقاوة `_derive_success` (خلاصة نجاح صادقة: None بلا مقياس، سلبيّ ⇒ False).
  • توصيل الموجِّه: النقاط الثلاث مُضمَّنة في التطبيق بأفعال HTTP الصحيحة.

الصدق: لا يدّعي اختبار كتابة DB هنا (لا Postgres في الوحدة) — يقتصر على ما يُتحقَّق
حتميّاً. مسار الكتابة يطبّقه CI Integration كبقيّة نقاط tenant_connection.
"""

import api.main  # noqa: F401 — تهيئة api.main قبل استيراد الموجِّه
import pytest
from api.event_bus import EventType
from api.event_catalog import get_event, is_registered
from api.routers.decision_record import _derive_success

pytestmark = pytest.mark.unit


def test_new_event_types_registered_in_enum():
    """نوعا الحدث الجديدان موجودان في EventType بقيمتهما المنقّطة (وسيط NATS)."""
    assert EventType.DECISION_RECORDED.value == "decision.recorded"
    assert EventType.OUTCOME_MEASURED.value == "outcome.measured"
    # قابلان للبحث بالاسم (كما يستعملهما _emit_domain_event: EventType[name]).
    assert EventType["DECISION_RECORDED"] is EventType.DECISION_RECORDED
    assert EventType["OUTCOME_MEASURED"] is EventType.OUTCOME_MEASURED


def test_new_events_registered_in_catalog():
    """نوعا الحدث مُسجَّلان في سجلّ الأحداث (حوكمة): فئة lineage + وصف عربيّ."""
    for name in ("DECISION_RECORDED", "OUTCOME_MEASURED"):
        assert is_registered(name), f"{name} غير مسجَّل في event_catalog"
        ev = get_event(name)
        assert ev is not None
        assert ev["category"] == "lineage"
        assert ev["description_ar"]  # وصف غير فارغ


def test_derive_success_none_when_nothing_evaluated():
    """لا مقياس مُقيَّم (كلّه needs_data) ⇒ None (لا حكم مُختلق)."""
    metrics = [
        {"key": "irrigation", "status": "needs_data"},
        {"key": "stress", "status": "needs_data"},
    ]
    assert _derive_success(metrics) is None


def test_derive_success_true_when_no_negative():
    """كلّ المقاييس المُقيَّمة محايدة/إيجابيّة ⇒ نجاح."""
    metrics = [
        {"key": "irrigation", "status": "followed"},
        {"key": "stress", "status": "better"},
        {"key": "yield", "status": "needs_data"},
    ]
    assert _derive_success(metrics) is True


def test_derive_success_false_when_any_negative():
    """أيّ مقياس مُقيَّم سلبيّ (انحراف عن الهدف) ⇒ ليس نجاحاً."""
    metrics = [
        {"key": "irrigation", "status": "followed"},
        {"key": "water_budget", "status": "exceeded"},  # سلبيّ
    ]
    assert _derive_success(metrics) is False


def test_persistence_endpoints_wired():
    """النقاط الثلاث مُضمَّنة في التطبيق بأفعالها الصحيحة (POST/POST/GET)."""
    routes = {(r.path, m) for r in api.main.app.routes for m in getattr(r, "methods", set())}
    assert ("/api/v1/decision/record", "POST") in routes
    assert ("/api/v1/outcome/record", "POST") in routes
    assert ("/api/v1/decision/{decision_id}/lineage", "GET") in routes
    # P0-2: دليل المنطقة المُدام (يُجمّع outcome_record المحفوظة).
    assert ("/api/v1/calibration/{region}/evidence/persisted", "GET") in routes

"""تفويض ملكيّة الحقل في soil-service — حارس عزل متعدّد المستأجرين.

السبب (ثغرة مُحقَّقة): GET /v1/soil/readings/{field_id} كان محميّاً بتوكن الخدمة فقط
ثمّ يقرأ بـWHERE field_id=$1 بلا فلتر/فحص ملكيّة ⇒ أيّ حامل توكن خدمة يقرأ قراءات
تربة أيّ مستأجِر بمعرفة field_id (IDOR / تسريب عبر المستأجرين). والاستيعاب كان يثق
بـtenant_id من جسم الطلب (لا يُوثَق به إطلاقاً).

الإصلاح يعكس نمط raster-service: `_require_field_tenant` يحسم المالك من المصدر
الموثوق (جدول fields عبر دالّة SECURITY DEFINER `sahool_field_owner_tenant`):
  • مالكٌ معروف ≠ مستأجِر الطلب (X-Tenant-Id الموثوق، أو غيابه) ⇒ 403.
  • قاعدة مُهيّأة لكن تعذّر إثبات الملكيّة (OwnerLookupUnavailable) ⇒ 503 (fail-closed).
  • بلا قاعدة (DATABASE_URL غير مضبوط ⇒ المالك None) ⇒ لا حجب (يبقى CI أخضر).
  • الاستيعاب يشتقّ tenant_id من المالك المُثبَت لا من الجسم؛ جسمٌ يخالف المالك ⇒ 409.
"""

from __future__ import annotations

import importlib.util
import os

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.security]  # CI يشغّل -m unit

ROOT = os.path.join(os.path.dirname(__file__), "..")
SOIL = os.path.join(ROOT, "services/soil-service")

# يتطلّب fastapi (المسارات/الترويسات) — قد يغيب في بيئة CI الخفيفة ⇒ نتخطّى بصدق.
_fastapi = importlib.util.find_spec("fastapi") is not None


def _const_owner(value):
    """يصنع بديلاً async لـ_field_owner يُعيد مالكاً ثابتاً (يحاكي جدول fields)."""

    async def _f(field_id):
        return value

    return _f


@pytest.fixture
def sm():
    """يستورد soil-service.main وينظّف سياق المستأجِر قبل/بعد كلّ اختبار. يستبدل
    _field_owner ببديل افتراضيّ يُعيد None (لا قاعدة) ما لم يُعيّن الاختبار مالكاً."""
    if not _fastapi:
        pytest.skip("fastapi غير متاح في هذه البيئة — يُنفَّذ في وظيفة الوحدات الكاملة")
    import importlib
    import sys

    if SOIL not in sys.path:
        sys.path.insert(0, SOIL)
    # عزل: اسم الوحدة 'main' عامّ عبر الخدمات. نُسقط المُخبّأ ونُعيد الاستيراد من مسار
    # soil، ونتحقّق أنّه فعلاً soil-service (لا تصادم أسماء عبر الخدمات).
    # بعد التفكيك: نُسقط أيضاً وحدات routers/ + router_registry كي يُعاد بناء رسم
    # الوحدات كاملاً متّسقاً — وإلّا تُبقي routers/ المُخبّأة مرجعاً لـmain قديم (حالة
    # متعفّنة عبر الاختبارات: المُعالِج المُعاد-تصديره يقرأ main قديماً لا المُعاد استيراده).
    for _m in (
        "main",
        "db_persist",
        "router_registry",
        "routers",
        "routers.readings",
        "routers.health",
    ):
        sys.modules.pop(_m, None)
    soil_main = importlib.import_module("main")
    assert hasattr(soil_main, "ingest_reading") and hasattr(soil_main, "get_readings"), (
        "استُورد main خاطئ (تصادم أسماء عبر الخدمات) — ليس soil-service"
    )

    _orig_owner = soil_main._field_owner
    soil_main._field_owner = _const_owner(None)  # لا قاعدة افتراضيّاً
    tok = soil_main._REQ_TENANT.set(None)
    try:
        yield soil_main
    finally:
        soil_main._REQ_TENANT.reset(tok)
        soil_main._field_owner = _orig_owner
        sys.modules.pop("main", None)
        sys.modules.pop("db_persist", None)


# ─── المصدر الموثوق (جدول fields) ──────────────────────────────────
async def test_owner_tenant_allowed(sm):
    """tenant_a → field_a (يملكه جدول fields) ⇒ يمرّ، ويُعيد المالك المُثبَت."""
    sm._field_owner = _const_owner("tenant_a")
    sm._REQ_TENANT.set("tenant_a")
    owner = await sm._require_field_tenant("field_a")  # لا يرفع
    assert owner == "tenant_a"


async def test_other_tenant_forbidden(sm):
    """tenant_b → field_a (يملكه tenant_a في fields) ⇒ 403 (إغلاق IDOR)."""
    from fastapi import HTTPException

    sm._field_owner = _const_owner("tenant_a")
    sm._REQ_TENANT.set("tenant_b")
    with pytest.raises(HTTPException) as ei:
        await sm._require_field_tenant("field_a")
    assert ei.value.status_code == 403


async def test_missing_tenant_with_owned_field_forbidden(sm):
    """بلا X-Tenant-Id لحقلٍ مملوك (جدول fields) ⇒ 403 (إغلاق فجوة «غياب المستأجِر»)."""
    from fastapi import HTTPException

    sm._field_owner = _const_owner("tenant_a")
    sm._REQ_TENANT.set(None)
    with pytest.raises(HTTPException) as ei:
        await sm._require_field_tenant("field_a")
    assert ei.value.status_code == 403


# ─── حقل مجهول / بلا قاعدة: لا حجب (لا تسريب، لا رفض زائف) ──────────
async def test_unknown_field_no_decision(sm):
    """حقل غير موجود في fields (المالك None) ⇒ لا حجب (لا بيانات تُسرَّب)."""
    sm._REQ_TENANT.set("tenant_b")
    owner = await sm._require_field_tenant("field_never_seen")  # لا يرفع
    assert owner is None


async def test_db_less_no_block(sm):
    """وضع بلا قاعدة (DATABASE_URL غير مضبوط ⇒ المالك None) ⇒ لا حجب (يبقى CI أخضر)."""
    sm._field_owner = _const_owner(None)
    sm._REQ_TENANT.set("tenant_b")
    owner = await sm._require_field_tenant("field_x")  # لا يرفع
    assert owner is None


async def test_db_configured_but_lookup_unavailable_fails_closed(sm):
    """fail-closed: قاعدة **مُهيّأة** لكن تعذّر إثبات الملكيّة ⇒ 503 (لا نخدم بلا إثبات)."""
    import sys

    from fastapi import HTTPException

    db_persist = sys.modules.get("db_persist") or __import__("db_persist")

    async def _unavailable(field_id):
        raise db_persist.OwnerLookupUnavailable("connect failed")

    sm._field_owner = _unavailable
    sm._REQ_TENANT.set("tenant_b")
    with pytest.raises(HTTPException) as ei:
        await sm._require_field_tenant("field_a")
    assert ei.value.status_code == 503


# ─── الاستيعاب: لا يثق بـtenant_id من الجسم ────────────────────────
async def test_ingest_rejects_body_tenant_conflicting_owner(sm):
    """جسمٌ يحمل tenant_id يخالف مالك الحقل المُثبَت ⇒ 409 (منع انتحال)."""
    from fastapi import HTTPException

    sm._field_owner = _const_owner("tenant_a")
    sm._REQ_TENANT.set("tenant_a")
    reading = sm.SoilReading(field_id="field_a", sensor_id="s1", tenant_id="tenant_evil")
    with pytest.raises(HTTPException) as ei:
        await sm.ingest_reading(reading, x_agent_token=_token(sm))
    assert ei.value.status_code == 409


async def test_ingest_cross_tenant_field_forbidden(sm):
    """استيعاب لحقلٍ يملكه مستأجِر آخر ⇒ 403 (منع كتابة عبر المستأجرين)."""
    from fastapi import HTTPException

    sm._field_owner = _const_owner("tenant_a")
    sm._REQ_TENANT.set("tenant_b")
    reading = sm.SoilReading(field_id="field_a", sensor_id="s1")
    with pytest.raises(HTTPException) as ei:
        await sm.ingest_reading(reading, x_agent_token=_token(sm))
    assert ei.value.status_code == 403


async def test_ingest_body_tenant_ignored_uses_resolved_owner(sm):
    """tenant_id من الجسم يُتجاهَل ويُشتقّ من المالك المُثبَت — حتّى لو وافق الترويسة.

    بلا _pool (DB-less) يصل إلى 503 بعد تجاوز فحص الملكيّة دون انتحال (الجسم لا يخالف
    المالك لأنّه يساويه) — فلا 409/403، ما يثبت أنّ قيمة الجسم لا تُستخدَم كمصدر ثقة."""
    from fastapi import HTTPException

    sm._field_owner = _const_owner("tenant_a")
    sm._REQ_TENANT.set("tenant_a")
    sm._pool = None  # DB-less ⇒ بعد فحص الملكيّة الناجح ⇒ 503 (لا 409/403)
    reading = sm.SoilReading(field_id="field_a", sensor_id="s1", tenant_id="tenant_a")
    with pytest.raises(HTTPException) as ei:
        await sm.ingest_reading(reading, x_agent_token=_token(sm))
    assert ei.value.status_code == 503  # وصل لمسار الكتابة ⇒ الملكيّة سُمِح بها، الجسم لم يُرفَض


# ─── حُرّاس مصدر (دفاع عمق) ────────────────────────────────────────
def test_db_backed_owner_lookup_wired():
    """المصدر الموثوق موصول: db_persist.field_owner_tenant + الدالّة SECURITY DEFINER
    + fail-closed عبر OwnerLookupUnavailable ⇒ 503 في main."""
    dbp = open(os.path.join(SOIL, "db_persist.py"), encoding="utf-8").read()
    assert "async def field_owner_tenant(" in dbp
    assert "sahool_field_owner_tenant" in dbp
    assert "class OwnerLookupUnavailable" in dbp
    assert "raise OwnerLookupUnavailable" in dbp
    # بعد التفكيك: مُعالِج الاستيعاب انتقل إلى routers/؛ نمسح المصدر المُجمَّع
    # (main.py + routers/*.py) فيبقى التأكيد الأمنيّ صحيحاً (لا إضعاف، توسيع نطاق فقط).
    from soil_route_source import soil_combined_source

    main_src = soil_combined_source(ROOT)
    assert "OwnerLookupUnavailable" in main_src and "HTTPException(503" in main_src, (
        "_require_field_tenant لا يُغلق fail-closed عند تعذّر إثبات الملكيّة"
    )
    # الاستيعاب لا يثق بـtenant_id من الجسم (يكتب المالك المُشتقّ لا reading.tenant_id)
    assert "resolved_tenant" in main_src and "reading.tenant_id," not in main_src, (
        "الاستيعاب لا يزال يثق بـtenant_id من الجسم"
    )


def _token(sm):
    """يضبط توكن الخدمة (إن لم يُضبط) ويُعيده ليتجاوز فحص التوكن في الاختبارات."""
    if not sm.AGENT_TOKEN:
        sm.AGENT_TOKEN = "test-token"
    return sm.AGENT_TOKEN

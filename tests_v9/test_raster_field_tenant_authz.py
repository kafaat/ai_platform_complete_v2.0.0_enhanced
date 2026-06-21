"""تفويض ملكيّة الحقل في raster-service — حارس عزل متعدّد المستأجرين.

السبب (تدقيق معماريّ): مسارات الحقل المكشوفة للمتصفّح
(tiles/tilejson/timeseries/indicator-grid) تُنادى بالـfield_id فقط. المصادقة
مفروضة عند البوّابة (JWT → حقن X-Tenant-Id موثوق)، لكنّ غياب فحص **التفويض**
(ملكيّة الحقل للمستأجِر) يسمح لمستأجِر بقراءة حقل آخر بمعرفة المعرّف (IDOR).

`_require_field_tenant` يغلق هذا بطبقتين:
  ١) ذاكرة الطبقات المخبّأة (tenant_id) — كشف فوريّ بلا I/O.
  ٢) المصدر الموثوق: جدول fields عبر دالّة SECURITY DEFINER (`_field_owner`) — يحسم
     بعد إعادة التشغيل، وبلا طبقة مخبّأة، **وحتى عند غياب X-Tenant-Id**.

تعاقُد الاختبار: tenant_a→field_a = يمرّ؛ tenant_b→field_a = 403 (عبر الذاكرة أو
القاعدة)؛ وبلا X-Tenant-Id لحقلٍ مملوك = 403؛ وحقلٌ مجهول = لا حجب (لا تسريب).
"""

from __future__ import annotations

import importlib.util
import os

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.security]  # CI يشغّل -m unit

ROOT = os.path.join(os.path.dirname(__file__), "..")
RASTER = os.path.join(ROOT, "services/raster-service")

# يتطلّب fastapi (المسارات) — في بيئة CI الخفيفة قد يغيب؛ نتخطّى بصدق إن غاب.
_fastapi = importlib.util.find_spec("fastapi") is not None


def _const_owner(value):
    """يصنع بديلاً async لـ_field_owner يُعيد مالكاً ثابتاً (يحاكي جدول fields)."""

    async def _f(field_id):
        return value

    return _f


@pytest.fixture
def rm():
    """يستورد raster-service.main وينظّف الحالة العالميّة + ذاكرة المالك قبل/بعد كلّ
    اختبار. يستبدل _field_owner ببديل افتراضيّ يُعيد None (لا قاعدة) كي تحكم الذاكرة
    ما لم يُعيّن الاختبار مالكاً صراحةً."""
    if not _fastapi:
        pytest.skip("fastapi غير متاح في هذه البيئة — يُنفَّذ في وظيفة الوحدات الكاملة")
    import sys

    if RASTER not in sys.path:
        sys.path.insert(0, RASTER)
    # عزل: اسم الوحدة 'main' عامّ عبر الخدمات. نُسقط المُخبّأ ونُعيد الاستيراد من مسار
    # raster، ونتحقّق أنّه فعلاً raster (لا تصادم أسماء عبر الخدمات).
    import importlib

    sys.modules.pop("main", None)
    raster_main = importlib.import_module("main")
    assert hasattr(raster_main, "_field_layers"), (
        "استُورد main خاطئ (تصادم أسماء عبر الخدمات) — ليس raster-service"
    )

    raster_main._layers.clear()
    raster_main._field_layers.clear()
    raster_main._field_owner_cache.clear()
    _orig_owner = raster_main._field_owner
    raster_main._field_owner = _const_owner(None)  # لا قاعدة افتراضيّاً
    tok = raster_main._REQ_TENANT.set(None)
    try:
        yield raster_main
    finally:
        raster_main._REQ_TENANT.reset(tok)
        raster_main._field_owner = _orig_owner
        raster_main._layers.clear()
        raster_main._field_layers.clear()
        raster_main._field_owner_cache.clear()
        sys.modules.pop("main", None)


def _seed_field(rm, field_id: str, owner_tenant: str) -> None:
    """يُسجّل طبقة مخبّأة للحقل مملوكة لمستأجِر (كما يفعل /process)."""
    lid = f"lyr_{field_id}"
    rm._layers[lid] = {"cog_url": "file:///x.tif", "index": "ndvi", "tenant_id": owner_tenant}
    rm._field_layers[field_id] = [lid]


# ─── الطبقة ١: ذاكرة الطبقات المخبّأة ──────────────────────────────
async def test_owner_tenant_allowed(rm):
    """tenant_a → field_a (يملكه، طبقة مخبّأة) ⇒ يمرّ."""
    _seed_field(rm, "field_a", "tenant_a")
    rm._REQ_TENANT.set("tenant_a")
    await rm._require_field_tenant("field_a")  # لا يرفع


async def test_other_tenant_forbidden_via_cache(rm):
    """tenant_b → field_a (طبقة مخبّأة لـtenant_a) ⇒ 403 (كشف cache فوريّ)."""
    from fastapi import HTTPException

    _seed_field(rm, "field_a", "tenant_a")
    rm._REQ_TENANT.set("tenant_b")
    with pytest.raises(HTTPException) as ei:
        await rm._require_field_tenant("field_a")
    assert ei.value.status_code == 403


# ─── الطبقة ٢: المصدر الموثوق (جدول fields) — بلا طبقة مخبّأة ───────
async def test_other_tenant_forbidden_via_db(rm):
    """tenant_b → field_a بلا طبقة مخبّأة، لكنّ جدول fields يملكه tenant_a ⇒ 403.

    يغلق الفجوة: لا اعتماد على الذاكرة وحدها (بعد إعادة التشغيل/worker آخر)."""
    from fastapi import HTTPException

    rm._field_owner = _const_owner("tenant_a")  # المصدر الموثوق
    rm._REQ_TENANT.set("tenant_b")
    with pytest.raises(HTTPException) as ei:
        await rm._require_field_tenant("field_a")
    assert ei.value.status_code == 403


async def test_db_owner_allows(rm):
    """tenant_a → field_a بلا طبقة، وجدول fields يملكه tenant_a ⇒ يمرّ."""
    rm._field_owner = _const_owner("tenant_a")
    rm._REQ_TENANT.set("tenant_a")
    await rm._require_field_tenant("field_a")  # لا يرفع


async def test_missing_tenant_with_owned_field_forbidden(rm):
    """بلا X-Tenant-Id لحقلٍ مملوك (جدول fields) ⇒ 403 (إغلاق فجوة «غياب المستأجِر»)."""
    from fastapi import HTTPException

    rm._field_owner = _const_owner("tenant_a")
    rm._REQ_TENANT.set(None)
    with pytest.raises(HTTPException) as ei:
        await rm._require_field_tenant("field_a")
    assert ei.value.status_code == 403


# ─── حقل مجهول / قاعدة متعذّرة: لا حجب (لا تسريب، لا رفض زائف) ──────
async def test_unknown_field_no_decision(rm):
    """حقل لا طبقة له ولا في fields (المالك None) ⇒ لا حجب (لا بيانات تُسرَّب)."""
    rm._REQ_TENANT.set("tenant_b")
    await rm._require_field_tenant("field_never_seen")  # لا يرفع


async def test_db_unavailable_failsafe_still_blocks_cache(rm):
    """fail-safe: القاعدة متعذّرة (المالك None) لكنّ طبقة مخبّأة لمستأجِر آخر ⇒ يبقى 403."""
    from fastapi import HTTPException

    _seed_field(rm, "field_a", "tenant_a")  # cache يكشف
    rm._field_owner = _const_owner(None)  # قاعدة متعذّرة
    rm._REQ_TENANT.set("tenant_b")
    with pytest.raises(HTTPException) as ei:
        await rm._require_field_tenant("field_a")
    assert ei.value.status_code == 403


async def test_db_unavailable_no_db_configured_no_block(rm):
    """وضع بلا قاعدة (DATABASE_URL غير مضبوط ⇒ المالك None) ⇒ لا حجب (يبقى فحص الذاكرة)."""
    rm._field_owner = _const_owner(None)
    rm._REQ_TENANT.set("tenant_b")
    await rm._require_field_tenant("field_x")  # لا يرفع


async def test_db_configured_but_lookup_unavailable_fails_closed(rm):
    """fail-closed: قاعدة **مُهيّأة** لكن تعذّر إثبات الملكيّة ⇒ 503 (لا نخدم بلا إثبات).

    يُغلق ملاحظة المراجعة: سابقاً كان تعذّر القاعدة يُعيد None ⇒ لا حجب (fail-open)."""
    import sys

    from fastapi import HTTPException

    db_persist = sys.modules.get("db_persist") or __import__("db_persist")

    async def _unavailable(field_id):
        raise db_persist.OwnerLookupUnavailable("connect failed")

    rm._field_owner = _unavailable
    rm._REQ_TENANT.set("tenant_b")
    with pytest.raises(HTTPException) as ei:
        await rm._require_field_tenant("field_a")
    assert ei.value.status_code == 503


# ─── حُرّاس مصدر (دفاع عمق) ────────────────────────────────────────
def test_rehydrated_layer_stores_tenant():
    """الطبقة المُعاد ترطيبها من القاعدة يجب أن تحمل tenant_id (وإلّا تسريب عبر cache)."""
    src = open(os.path.join(RASTER, "main.py"), encoding="utf-8").read()
    block = src[src.index('lid = f"db_') : src.index('lid = f"db_') + 600]
    assert '"tenant_id": _REQ_TENANT.get()' in block, (
        "طبقة DB المُعاد ترطيبها بلا tenant_id ⇒ ثغرة تسريب عبر الـcache"
    )


def test_db_backed_owner_lookup_wired():
    """المصدر الموثوق موصول: db_persist.field_owner_tenant + migration v88 بدالّة
    SECURITY DEFINER على fields، مُدرَجة في MANIFEST."""
    dbp = open(os.path.join(RASTER, "db_persist.py"), encoding="utf-8").read()
    assert "async def field_owner_tenant(" in dbp
    assert "sahool_field_owner_tenant" in dbp
    # fail-closed: قاعدة مُهيّأة + تعذّر الإثبات ⇒ OwnerLookupUnavailable ⇒ 503 (لا fail-open)
    assert "class OwnerLookupUnavailable" in dbp
    assert "raise OwnerLookupUnavailable" in dbp
    main_src = open(os.path.join(RASTER, "main.py"), encoding="utf-8").read()
    assert "OwnerLookupUnavailable" in main_src and "HTTPException(503" in main_src, (
        "_require_field_tenant لا يُغلق fail-closed عند تعذّر إثبات الملكيّة"
    )
    mig = os.path.join(ROOT, "migrations/v88_field_owner_function.sql")
    assert os.path.exists(mig), "migration v88 مفقود"
    sql = open(mig, encoding="utf-8").read()
    assert "SECURITY DEFINER" in sql and "FROM fields WHERE field_id" in sql
    manifest = open(os.path.join(ROOT, "migrations/MANIFEST.txt"), encoding="utf-8").read()
    assert "v88_field_owner_function.sql" in manifest, "v88 غير مُدرَج في MANIFEST"

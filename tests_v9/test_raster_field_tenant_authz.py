"""تفويض ملكيّة الحقل في raster-service — حارس عزل متعدّد المستأجرين.

السبب (تدقيق معماريّ): مسارات الحقل المكشوفة للمتصفّح
(tiles/tilejson/timeseries/indicator-grid) تُنادى بالـfield_id فقط. المصادقة
مفروضة عند البوّابة (JWT → حقن X-Tenant-Id موثوق)، لكنّ غياب فحص **التفويض**
(ملكيّة الحقل للمستأجِر) يسمح لمستأجِر بقراءة حقل آخر بمعرفة المعرّف (IDOR).

`_require_field_tenant` يغلق هذا: الطبقات تحمل tenant_id (سُجِّل عند /process وعند
إعادة الترطيب من القاعدة)، وأيّ طبقة معروفة بمستأجِر مختلف عن مستأجِر الطلب ⇒ 403.

تعاقُد الاختبار المطلوب: tenant_a→field_a = يمرّ؛ tenant_b→field_a = 403.
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


@pytest.fixture
def rm():
    """يستورد وحدة raster-service.main مع تنظيف الحالة العالميّة قبل/بعد كلّ اختبار."""
    if not _fastapi:
        pytest.skip("fastapi غير متاح في هذه البيئة — يُنفَّذ في وظيفة الوحدات الكاملة")
    import sys

    if RASTER not in sys.path:
        sys.path.insert(0, RASTER)
    import main as raster_main

    raster_main._layers.clear()
    raster_main._field_layers.clear()
    tok = raster_main._REQ_TENANT.set(None)
    try:
        yield raster_main
    finally:
        raster_main._REQ_TENANT.reset(tok)
        raster_main._layers.clear()
        raster_main._field_layers.clear()


def _seed_field(rm, field_id: str, owner_tenant: str) -> None:
    """يُسجّل طبقة للحقل مملوكة لمستأجِر (كما يفعل /process)."""
    lid = f"lyr_{field_id}"
    rm._layers[lid] = {"cog_url": "file:///x.tif", "index": "ndvi", "tenant_id": owner_tenant}
    rm._field_layers[field_id] = [lid]


def test_owner_tenant_allowed(rm):
    """tenant_a → field_a (يملكه) ⇒ يمرّ بلا استثناء."""
    _seed_field(rm, "field_a", "tenant_a")
    rm._REQ_TENANT.set("tenant_a")
    rm._require_field_tenant("field_a")  # لا يرفع


def test_other_tenant_forbidden(rm):
    """tenant_b → field_a (يملكه tenant_a) ⇒ 403 (إغلاق IDOR)."""
    from fastapi import HTTPException

    _seed_field(rm, "field_a", "tenant_a")
    rm._REQ_TENANT.set("tenant_b")
    with pytest.raises(HTTPException) as ei:
        rm._require_field_tenant("field_a")
    assert ei.value.status_code == 403


def test_unknown_field_no_decision(rm):
    """بلا طبقات معروفة للحقل ⇒ لا حجب (مسار القاعدة مُنطّق بالمستأجِر فلا تسريب)."""
    rm._REQ_TENANT.set("tenant_b")
    rm._require_field_tenant("field_never_seen")  # لا يرفع


def test_no_tenant_context_no_decision(rm):
    """بلا سياق مستأجِر (نداء داخليّ بلا X-Tenant-Id) ⇒ لا حجب هنا."""
    _seed_field(rm, "field_a", "tenant_a")
    rm._REQ_TENANT.set(None)
    rm._require_field_tenant("field_a")  # لا يرفع


def test_rehydrated_layer_stores_tenant(rm):
    """دفاع عمق: الطبقة المُعاد ترطيبها من القاعدة يجب أن تحمل tenant_id (لا None)
    وإلّا يمرّ مستأجِر آخر على الـcache. نتحقّق أنّ كود الترطيب يضبط tenant_id."""
    src = open(os.path.join(RASTER, "main.py"), encoding="utf-8").read()
    # كتلة إعادة الترطيب (lid = f"db_...") تُسند tenant_id من سياق الطلب.
    block = src[src.index('lid = f"db_') : src.index('lid = f"db_') + 600]
    assert '"tenant_id": _REQ_TENANT.get()' in block, (
        "طبقة DB المُعاد ترطيبها بلا tenant_id ⇒ ثغرة تسريب عبر الـcache"
    )

"""اختبار توريث هويّة المستأجِر في مسار قراءة الراستر (إصلاح ترطيب raster_assets).

يثبت أنّ الترويسة الموثوقة X-Tenant-Id تصل إلى db_persist.fetch_latest_asset عبر سياق
الطلب، وأنّ غيابها ⇒ None (سلوك fail-closed، لا انحدار). نُحاكي الجلب فلا حاجة لقاعدة.
"""

import asyncio

import db_persist
import main


def test_tenant_from_header_normalisation():
    assert main._tenant_from_header("t-1") == "t-1"
    assert main._tenant_from_header("  t-2  ") == "t-2"
    assert main._tenant_from_header("") is None
    assert main._tenant_from_header("   ") is None
    assert main._tenant_from_header(None) is None


def _resolve_with_tenant(tenant, monkeypatch):
    captured = {}

    async def fake_fetch(field_id, index_name, date=None, tenant_id=None):
        captured["tenant_id"] = tenant_id
        return None  # لا أصل ⇒ _resolve_field_layer يعود None مباشرة بعد الجلب

    monkeypatch.setattr(db_persist, "fetch_latest_asset", fake_fetch)
    token = main._REQ_TENANT.set(tenant)
    try:
        res = asyncio.run(main._resolve_field_layer("fld-unknown", "ndvi", "latest"))
    finally:
        main._REQ_TENANT.reset(token)
    assert res is None
    return captured.get("tenant_id")


def test_resolve_propagates_trusted_tenant(monkeypatch):
    # المستأجِر الموثوق من السياق يصل لطبقة القاعدة (يُمكّن RLS + الفلتر الصريح).
    assert _resolve_with_tenant("tenant-abc", monkeypatch) == "tenant-abc"


def test_resolve_without_tenant_passes_none(monkeypatch):
    # بلا مستأجِر ⇒ None ⇒ RLS يحجب (fail-closed) — السلوك الحالي محفوظ، لا انحدار.
    assert _resolve_with_tenant(None, monkeypatch) is None

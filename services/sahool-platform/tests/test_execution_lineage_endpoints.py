"""اختبار توصيل نقاط النَّسَب الموحّد (routers/execution_lineage) + تسجيل الحدث.

مسار الكتابة/القراءة تكامليّ (يتطلّب Postgres+RLS) — هنا نؤكّد: (أ) نوع الحدث
LINEAGE_LINKED مُسجَّل في EventType + event_catalog؛ (ب) النقطتان مُضمَّنتان بأفعالهما؛
(ج) العلم المُطفأ ⇒ 404 قبل أيّ قاعدة (استدعاء مباشر للمعالِج، تفادي TestClient/المصادقة).
"""

import api.main  # noqa: F401 — تهيئة api.main قبل استيراد الموجِّهات
import pytest
from api.event_bus import EventType
from api.event_catalog import get_event, is_registered
from api.routers.execution_lineage import (
    LineageLinkRequest,
    get_lineage_chain,
    link_lineage_ref,
)
from core.canonical_schemas import UserRole, UserSchema
from fastapi import HTTPException

pytestmark = pytest.mark.unit

_USER = UserSchema(
    user_id="u-lin",
    tenant_id="00000000-0000-0000-0000-000000000002",
    role=UserRole.OWNER,
    name_ar="رابِط",
)


def test_lineage_linked_event_registered():
    """نوع الحدث LINEAGE_LINKED مُسجَّل في EventType + event_catalog (فئة lineage)."""
    assert EventType.LINEAGE_LINKED.value == "lineage.linked"
    assert EventType["LINEAGE_LINKED"] is EventType.LINEAGE_LINKED
    assert is_registered("LINEAGE_LINKED")
    ev = get_event("LINEAGE_LINKED")
    assert ev is not None and ev["category"] == "lineage"


def test_lineage_endpoints_wired():
    """نقطتا النَّسَب الموحّد مُضمَّنتان بأفعالهما الصحيحة (POST link / GET chain)."""
    routes = {(r.path, m) for r in api.main.app.routes for m in getattr(r, "methods", set())}
    assert ("/api/v1/lineage/link", "POST") in routes
    assert ("/api/v1/lineage/{lineage_id}", "GET") in routes


async def test_link_flag_off_returns_404(monkeypatch):
    """العلم المُطفأ ⇒ 404 قبل أيّ قاعدة (إغلاق مرن: الميزة معطّلة افتراضاً)."""
    monkeypatch.delenv("FEATURE_UNIFIED_LINEAGE", raising=False)
    req = LineageLinkRequest(ref_type="decision", ref_id="dec_1")
    with pytest.raises(HTTPException) as e:
        await link_lineage_ref(req=req, user=_USER)
    assert e.value.status_code == 404


async def test_get_chain_flag_off_returns_404(monkeypatch):
    monkeypatch.delenv("FEATURE_UNIFIED_LINEAGE", raising=False)
    with pytest.raises(HTTPException) as e:
        await get_lineage_chain(lineage_id="lin_1", user=_USER)
    assert e.value.status_code == 404


async def test_link_bad_ref_type_400(monkeypatch):
    """نوع مرجع مجهول ⇒ 400 قبل أيّ قاعدة (fail-closed على المُدخل، العلم مُفعَّل)."""
    monkeypatch.setenv("FEATURE_UNIFIED_LINEAGE", "true")
    req = LineageLinkRequest(ref_type="nonsense", ref_id="x1")
    with pytest.raises(HTTPException) as e:
        await link_lineage_ref(req=req, user=_USER)
    assert e.value.status_code == 400


def test_shape_link_row_formats_time():
    from datetime import UTC, datetime

    from api.routers.execution_lineage import _shape_link_row

    row = {
        "lineage_id": "lin_1",
        "ref_type": "dispatch",
        "ref_id": "disp_9",
        "created_at": datetime(2026, 6, 16, 12, 0, tzinfo=UTC),
    }
    out = _shape_link_row(row)
    assert out["lineage_id"] == "lin_1"
    assert out["ref_type"] == "dispatch"
    assert out["ref_id"] == "disp_9"
    assert out["created_at"].startswith("2026-06-16T12:00")

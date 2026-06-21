"""حُرّاس عزل الموارد + الصدق في خادم Market MCP (وحدات، بلا خدمات حيّة).

يغطّي الفجوات المُتحقَّقة:
  (أ) أمر شراء بـfield_id لمستأجِر آخر ⇒ مرفوض (403)؛ وتعذّر الإثبات ⇒ 503؛
      وبلا قاعدة (DB-less) ⇒ لا حجب.
  (ب) عرض بيع بـbatch_id لمستأجِر آخر/غير مرئيّ تحت RLS ⇒ مرفوض (403)؛ وتعذّر
      الإثبات ⇒ 503؛ وبلا قاعدة ⇒ لا حجب.
  (ج) /readyz يُعيد 503 حين تكون القاعدة مُهيّأة لكن غير قابلة للوصول، و"ready"
      في وضع بلا قاعدة (DB-less/CI).
  (د) العقد الآجل لم يعد يُعيد سعراً مُلفّقاً (يرفع 501).

نستورد market_server في الذاكرة (نفس نمط test_mcp_functional) ونستخدم fakes
لـDB — لا Postgres مطلوب. مُعلَّم unit/security ليُشغَّل في بوّابة CI.
"""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.security]  # CI يشغّل -m unit

REPO_ROOT = Path(__file__).resolve().parents[1]
MCP_DIR = REPO_ROOT / "services" / "mcp_servers"

JWT_SECRET = "test_secret_min_32_chars_for_sahool_v9"

OWNER_A = "11111111-1111-1111-1111-111111111111"
OWNER_B = "22222222-2222-2222-2222-222222222222"


class _DummyPool:
    """pool وهميّ — تُجرى فحوص الملكيّة **قبل** acquire، فلا يُستخدَم فعليّاً في
    مسارات الرفض. وجوده يتجاوز get_pool (الذي يرفع 503 'not configured' بلا قاعدة)
    كي يصل التنفيذ إلى فحص الملكيّة بدل التوقّف على غياب القاعدة."""

    def acquire(self):  # pragma: no cover — لا يُبلَغ في مسارات الرفض
        raise AssertionError("acquire لا يجب أن يُبلَغ بعد رفض الملكيّة")


def _patch_pool(market_server):
    """يجعل get_pool يُعيد pool وهميّاً (لتجاوز حاجز 'Database not configured')."""

    async def _pool():
        return _DummyPool()

    market_server.get_pool = _pool


def _ensure_mcp_path() -> None:
    """يضع services/mcp_servers ثمّ جذر المستودع على sys.path (دمج الحاوية)،
    ويُخلي ربط shared الجذريّ كي تُحلّ shared.oauth_middleware من mcp_servers."""
    for p in (str(REPO_ROOT), str(MCP_DIR)):  # MCP_DIR أخيراً ⇒ ينتهي أوّلاً
        if p in sys.path:
            sys.path.remove(p)
        sys.path.insert(0, p)
    for name in [n for n in sys.modules if n == "shared" or n.startswith("shared.")]:
        mod = sys.modules.get(name)
        mod_file = getattr(mod, "__file__", "") or ""
        if mod_file and str(MCP_DIR) not in mod_file:
            sys.modules.pop(name, None)


@pytest.fixture
def mkt():
    """يستورد market_server + market_db_authz في الذاكرة ويعزل sys.path/modules.

    يتخطّى بصدق إن تعذّر الاستيراد في تخطيط CI الخفيف (fastapi/التبعيّات غائبة)."""
    os.environ["JWT_SECRET"] = JWT_SECRET
    path_before = list(sys.path)
    shared_before = {
        k: v for k, v in sys.modules.items() if k == "shared" or k.startswith("shared.")
    }
    _ensure_mcp_path()
    try:
        market_server = importlib.import_module("market_server")
        authz = importlib.import_module("market_db_authz")
    except Exception as exc:  # noqa: BLE001 — تخطيط CI خفيف
        pytest.skip(f"market_server غير قابل للاستيراد هنا: {type(exc).__name__}: {exc}")
    # الوحدات مُخبّأة عبر الاختبارات؛ نحفظ الدوالّ الأصليّة ونستعيدها كي لا تتسرّب
    # رُقَع monkeypatch (field_owner_tenant/batch_visible_under_tenant/get_pool/
    # DATABASE_URL) إلى اختبارات لاحقة.
    saved = {
        "field_owner_tenant": authz.field_owner_tenant,
        "batch_visible_under_tenant": authz.batch_visible_under_tenant,
        "authz_db": authz.DATABASE_URL,
        "get_pool": market_server.get_pool,
        "srv_db": market_server.DATABASE_URL,
    }
    try:
        yield market_server, authz
    finally:
        authz.field_owner_tenant = saved["field_owner_tenant"]
        authz.batch_visible_under_tenant = saved["batch_visible_under_tenant"]
        authz.DATABASE_URL = saved["authz_db"]
        market_server.get_pool = saved["get_pool"]
        market_server.DATABASE_URL = saved["srv_db"]
        sys.path[:] = path_before
        for k in [k for k in sys.modules if k == "shared" or k.startswith("shared.")]:
            sys.modules.pop(k, None)
        sys.modules.update(shared_before)


# ─── (أ) أمر شراء بـfield_id غريب ────────────────────────────────
async def test_procurement_foreign_field_denied(mkt):
    """field_id يملكه OWNER_B بينما الأمر لمستأجِر OWNER_A ⇒ 403 (إغلاق IDOR)."""
    from fastapi import HTTPException

    market_server, authz = mkt

    async def _owner(field_id):
        return OWNER_B  # المالك الحقيقيّ ≠ مستأجِر الأمر

    authz.field_owner_tenant = _owner
    _patch_pool(market_server)
    with pytest.raises(HTTPException) as ei:
        await market_server.tool_create_procurement(
            {"tenant_id": OWNER_A, "field_id": "field-x", "items": []}
        )
    assert ei.value.status_code == 403


async def test_procurement_lookup_unavailable_fails_closed(mkt):
    """قاعدة مُهيّأة لكن تعذّر إثبات ملكيّة الحقل ⇒ 503 (fail-closed، لا نخدم)."""
    from fastapi import HTTPException

    market_server, authz = mkt

    async def _owner(field_id):
        raise authz.OwnerLookupUnavailable("connect failed")

    authz.field_owner_tenant = _owner
    _patch_pool(market_server)
    with pytest.raises(HTTPException) as ei:
        await market_server.tool_create_procurement(
            {"tenant_id": OWNER_A, "field_id": "field-x", "items": []}
        )
    assert ei.value.status_code == 503


async def test_procurement_dbless_owner_none_no_block(mkt):
    """بلا قاعدة: المُحقِّق يُعيد None ⇒ فحص الملكيّة لا يحجب (لا 403).

    نُثبت طبقتين: (١) field_owner_tenant يُعيد None حين DATABASE_URL غير مضبوط؛
    (٢) المالك None ⇒ لا 403 (يتوقّف التنفيذ لاحقاً على غياب القاعدة، لا على الملكيّة)."""
    from fastapi import HTTPException

    market_server, authz = mkt

    # (١) تعاقُد المُحقِّق في وضع بلا قاعدة (لا حجب).
    orig_url = authz.DATABASE_URL
    authz.DATABASE_URL = ""
    try:
        assert await authz.field_owner_tenant("field-x") is None
    finally:
        authz.DATABASE_URL = orig_url

    # (٢) المالك None ⇒ لا 403؛ get_pool بلا قاعدة يرفع 503 (ليس 403).
    async def _owner(field_id):
        return None

    authz.field_owner_tenant = _owner
    market_server.DATABASE_URL = ""  # وضع بلا قاعدة ⇒ get_pool يرفع 503 نظيفاً
    with pytest.raises(HTTPException) as ei:
        await market_server.tool_create_procurement(
            {"tenant_id": OWNER_A, "field_id": "field-x", "items": []}
        )
    assert ei.value.status_code != 403  # الملكيّة لم تحجب (DB-less لا يبدأ بالحجب)
    assert ei.value.status_code == 503  # توقّف على غياب القاعدة لا على الملكيّة


# ─── (ب) عرض بيع بـbatch_id غريب ─────────────────────────────────
async def test_sales_foreign_batch_denied(mkt):
    """batch_id غير مرئيّ تحت RLS لمستأجِر العرض ⇒ 403 (إغلاق IDOR)."""
    from fastapi import HTTPException

    market_server, authz = mkt

    async def _visible(batch_id, tenant_id):
        return False  # لا صفّ مرئيّ تحت RLS لهذا المستأجِر

    authz.batch_visible_under_tenant = _visible
    _patch_pool(market_server)
    with pytest.raises(HTTPException) as ei:
        await market_server.tool_create_sales_listing(
            {
                "tenant_id": OWNER_A,
                "batch_id": "33333333-3333-3333-3333-333333333333",
                "crop_type": "wheat",
                "quantity_kg": 100,
                "price_per_kg_usd": 2.0,
            }
        )
    assert ei.value.status_code == 403


async def test_sales_batch_lookup_unavailable_fails_closed(mkt):
    """قاعدة مُهيّأة لكن تعذّر إثبات ملكيّة الدفعة ⇒ 503 (fail-closed)."""
    from fastapi import HTTPException

    market_server, authz = mkt

    async def _visible(batch_id, tenant_id):
        raise authz.OwnerLookupUnavailable("connect failed")

    authz.batch_visible_under_tenant = _visible
    _patch_pool(market_server)
    with pytest.raises(HTTPException) as ei:
        await market_server.tool_create_sales_listing(
            {
                "tenant_id": OWNER_A,
                "batch_id": "33333333-3333-3333-3333-333333333333",
                "crop_type": "wheat",
                "quantity_kg": 100,
                "price_per_kg_usd": 2.0,
            }
        )
    assert ei.value.status_code == 503


async def test_sales_dbless_visible_none_no_block(mkt):
    """بلا قاعدة: المُحقِّق يُعيد None ⇒ فحص ملكيّة الدفعة لا يحجب (لا 403)."""
    from fastapi import HTTPException

    market_server, authz = mkt

    # (١) تعاقُد المُحقِّق في وضع بلا قاعدة (لا حجب).
    orig_url = authz.DATABASE_URL
    authz.DATABASE_URL = ""
    try:
        assert await authz.batch_visible_under_tenant("batch-x", OWNER_A) is None
    finally:
        authz.DATABASE_URL = orig_url

    # (٢) visible None ⇒ لا 403؛ get_pool بلا قاعدة يرفع 503 (ليس 403).
    async def _visible(batch_id, tenant_id):
        return None

    authz.batch_visible_under_tenant = _visible
    market_server.DATABASE_URL = ""  # وضع بلا قاعدة ⇒ get_pool يرفع 503 نظيفاً
    with pytest.raises(HTTPException) as ei:
        await market_server.tool_create_sales_listing(
            {
                "tenant_id": OWNER_A,
                "batch_id": "33333333-3333-3333-3333-333333333333",
                "crop_type": "wheat",
                "quantity_kg": 100,
                "price_per_kg_usd": 2.0,
            }
        )
    assert ei.value.status_code != 403  # الملكيّة لم تحجب (DB-less)
    assert ei.value.status_code == 503  # توقّف على غياب القاعدة لا على الملكيّة


# ─── (ج) /readyz يفحص القاعدة فعليّاً ────────────────────────────
async def test_readyz_503_when_db_configured_unreachable(mkt):
    """قاعدة **مُهيّأة** لكن غير قابلة للوصول ⇒ 503 (لا توجيه حركة)."""
    from fastapi import HTTPException

    market_server, _ = mkt

    orig_db = market_server.DATABASE_URL
    orig_get_pool = market_server.get_pool

    async def _bad_pool():
        raise RuntimeError("pool down")

    market_server.DATABASE_URL = "postgresql://x@/y"  # القاعدة مُهيّأة
    market_server.get_pool = _bad_pool
    try:
        with pytest.raises(HTTPException) as ei:
            await market_server.readyz()
        assert ei.value.status_code == 503
    finally:
        market_server.DATABASE_URL = orig_db
        market_server.get_pool = orig_get_pool


async def test_readyz_ready_when_dbless(mkt):
    """وضع بلا قاعدة (DATABASE_URL غير مضبوط) ⇒ يبقى ready (لا يرفّ CI)."""
    market_server, _ = mkt

    orig_db = market_server.DATABASE_URL
    market_server.DATABASE_URL = ""  # بلا قاعدة
    try:
        result = await market_server.readyz()
        assert result["status"] == "ready"
        assert result.get("db_configured") is False
    finally:
        market_server.DATABASE_URL = orig_db


# ─── (د) العقد الآجل لا يُلفّق سعراً ─────────────────────────────
async def test_forward_contract_does_not_fabricate(mkt):
    """العقد الآجل يرفع 501 (غير مُنفَّذ) بدل إعادة سعرٍ/عقدٍ مُلفّق (صدق)."""
    from fastapi import HTTPException

    market_server, _ = mkt
    with pytest.raises(HTTPException) as ei:
        await market_server.tool_create_forward_contract(
            {"tenant_id": OWNER_A, "estimated_yield_kg": 5000, "crop": "wheat"}
        )
    assert ei.value.status_code == 501
    # لا أرقام ماليّة مُلفّقة في رسالة الخطأ.
    assert "agreed_price" not in str(ei.value.detail)

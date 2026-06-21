"""اختبار وحدويّ: صدق جسر Odoo (دفع SAHOOL→Odoo) وعزل المستأجر في الكتالوج.

يثبت أنّ إصلاحات الصدق/العزل في services/odoo-bridge/main.py حقيقيّة:

  (أ) دفع أمر شراء بمورّد غير قابل للحلّ في Odoo ⇒ الأمر يُعلَّم
      odoo_sync_status='failed' ولا يُدفَع أبداً بـpartner_id=1 المُلفَّق
      (لا أيّ purchase.order يُنشأ).
  (ب) دفع أمر بمورّد + منتج محلولَين فعليّاً ⇒ يُدفَع صحيحاً
      (partner_id = معرّف المورّد المحلول، product_id = المنتج المحلول، لا 1).
  (ج) إسناد tenant_id للكتالوج: حين ODOO_SYNC_TENANT_ID غائب ⇒ INSERT بلا
      tenant_id (كتالوج عالميّ)؛ حين مضبوط ⇒ tenant_id الصريح يُمرَّر (لا تلفيق).

نواة نقيّة بلا خدمات: نُحاكي عميل Odoo واتّصال قاعدة البيانات بالكامل (لا HTTP/DB حيّ).
"""

from __future__ import annotations

import importlib.util
import os
import sys

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.security]

ROOT = os.path.join(os.path.dirname(__file__), "..")
ODOO_BRIDGE = os.path.join(ROOT, "services/odoo-bridge")
MAIN_PATH = os.path.join(ODOO_BRIDGE, "main.py")


def _load_main(monkeypatch, *, sync_tenant: str | None = None):
    """يحمّل services/odoo-bridge/main.py باسم فريد مع بيئة محدّدة.

    fastapi/httpx/jose/asyncpg مطلوبة للاستيراد؛ بيئة الوحدة الخفيفة قد لا تثبّتها
    ⇒ نتخطّى بدل الفشل (يُغطّيه job أثقل)."""
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    pytest.importorskip("jose")
    pytest.importorskip("asyncpg")
    if sync_tenant is None:
        monkeypatch.delenv("ODOO_SYNC_TENANT_ID", raising=False)
    else:
        monkeypatch.setenv("ODOO_SYNC_TENANT_ID", sync_tenant)
    added = ODOO_BRIDGE not in sys.path
    if added:
        sys.path.insert(0, ODOO_BRIDGE)
    try:
        spec = importlib.util.spec_from_file_location(
            f"sahool_odoo_bridge_test_{sync_tenant or 'global'}", MAIN_PATH
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    finally:
        if added and ODOO_BRIDGE in sys.path:
            sys.path.remove(ODOO_BRIDGE)


# ══════════════════════════════════════════════════════════════
# Fakes (عميل Odoo + اتّصال DB + pool)
# ══════════════════════════════════════════════════════════════
class FakeOdoo:
    """عميل Odoo مُحاكى: search_read مُبرمَج، create يُسجّل كلّ إنشاء."""

    def __init__(self, *, partners=None, products=None):
        # partners/products: قوائم نتائج search_read حسب الموديل.
        self._partners = partners if partners is not None else []
        self._products = products if products is not None else []
        self.created: list[tuple[str, dict]] = []

    async def search_read(self, model, domain, fields, limit=0, order=""):
        if model == "res.partner":
            return list(self._partners)
        if model == "product.product":
            return list(self._products)
        return []

    async def create(self, model, values):
        self.created.append((model, values))
        # purchase.order يُعيد معرّفاً وهميّاً ثابتاً
        return 9999 if model == "purchase.order" else 8888


class FakeConn:
    """اتّصال DB مُحاكى: fetch/execute مُسجَّلان؛ fetch لجداول الأوامر مُبرمَج."""

    def __init__(self, *, orders, items):
        self._orders = orders
        self._items = items
        self.executes: list[tuple[str, tuple]] = []

    async def fetch(self, query, *args):
        if "FROM procurement_orders" in query:
            return list(self._orders)
        if "FROM procurement_order_items" in query:
            return list(self._items)
        return []

    async def execute(self, query, *args):
        self.executes.append((query, args))


class FakeAcquire:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, *a):
        return False


class FakePool:
    def __init__(self, conn):
        self._conn = conn

    def acquire(self):
        return FakeAcquire(self._conn)


def _wire(mod, monkeypatch, *, conn, odoo):
    """يربط get_pool/get_odoo/log_sync_record/set_last_sync بالمحاكيات."""

    async def _get_pool():
        return FakePool(conn)

    async def _noop(*a, **k):
        return None

    monkeypatch.setattr(mod, "get_pool", _get_pool)
    monkeypatch.setattr(mod, "get_odoo", lambda: odoo)
    monkeypatch.setattr(mod, "log_sync_record", _noop)
    monkeypatch.setattr(mod, "set_last_sync", _noop)
    monkeypatch.setattr(mod, "get_last_sync", _noop)


# ══════════════════════════════════════════════════════════════
# (أ) مورّد غير محلول ⇒ فشل صريح، لا partner_id=1 مُلفَّق
# ══════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_push_unresolved_supplier_marks_failed_not_partner_1(monkeypatch):
    mod = _load_main(monkeypatch)
    order = {
        "order_id": "PO-1",
        "tenant_id": "t-1",
        "status": "approved",
        "notes": "",
        "created_at": None,
    }
    items = [{"item_name": "Urea", "quantity": 5, "unit_cost_usd": 10, "supplier": "Acme Co"}]
    conn = FakeConn(orders=[order], items=items)
    # لا مورّد مطابق في Odoo، ولا منتج — يجب الفشل عند المورّد أوّلاً.
    odoo = FakeOdoo(partners=[], products=[])
    _wire(mod, monkeypatch, conn=conn, odoo=odoo)

    await mod.sync_procurement_orders_to_odoo()

    # لم يُنشأ أيّ purchase.order مُلفَّق (ولا partner_id=1).
    assert not any(model == "purchase.order" for model, _ in odoo.created), (
        "يجب ألّا يُدفَع أمر شراء حين لا مورّد محلول"
    )
    assert not any(
        v.get("partner_id") == 1 for model, v in odoo.created if model == "purchase.order"
    )
    # الأمر عُلِّم failed (مع سبب).
    failed = [
        (q, a)
        for q, a in conn.executes
        if "odoo_sync_status='failed'" in q and "UPDATE procurement_orders" in q
    ]
    assert failed, "يجب تعليم الأمر failed"
    # السبب يذكر تعذّر حلّ المورّد.
    assert any("مورّد" in str(a[0]) for _, a in failed)


# ══════════════════════════════════════════════════════════════
# (ب) مورّد + منتج محلولان ⇒ دفع صحيح (partner_id الحقيقيّ، لا 1)
# ══════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_push_resolved_supplier_pushes_correctly(monkeypatch):
    mod = _load_main(monkeypatch)
    order = {
        "order_id": "PO-2",
        "tenant_id": "t-1",
        "status": "approved",
        "notes": "n",
        "created_at": None,
    }
    items = [{"item_name": "Urea", "quantity": 5, "unit_cost_usd": 10, "supplier": "Acme Co"}]
    conn = FakeConn(orders=[order], items=items)
    # مورّد حقيقيّ id=42، منتج حقيقيّ id=77.
    odoo = FakeOdoo(partners=[{"id": 42}], products=[{"id": 77}])
    _wire(mod, monkeypatch, conn=conn, odoo=odoo)

    await mod.sync_procurement_orders_to_odoo()

    pos = [v for model, v in odoo.created if model == "purchase.order"]
    lines = [v for model, v in odoo.created if model == "purchase.order.line"]
    assert len(pos) == 1, "يجب دفع أمر شراء واحد"
    assert pos[0]["partner_id"] == 42, "partner_id يجب أن يكون المورّد المحلول لا 1"
    assert pos[0]["partner_id"] != 1
    assert len(lines) == 1
    assert lines[0]["product_id"] == 77, "product_id يجب أن يكون المنتج المحلول لا 1"
    assert lines[0]["product_id"] != 1
    # عُلِّم synced لا failed.
    assert any("odoo_sync_status='synced'" in q for q, _ in conn.executes)


# ══════════════════════════════════════════════════════════════
# (ب-٢) منتج غير محلول (المورّد محلول) ⇒ فشل صريح، لا prod_id=1
# ══════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_push_unresolved_product_marks_failed_not_prod_1(monkeypatch):
    mod = _load_main(monkeypatch)
    order = {
        "order_id": "PO-3",
        "tenant_id": "t-1",
        "status": "approved",
        "notes": "",
        "created_at": None,
    }
    items = [{"item_name": "Ghost", "quantity": 1, "unit_cost_usd": 1, "supplier": "Acme Co"}]
    conn = FakeConn(orders=[order], items=items)
    # مورّد محلول، لكن لا منتج مطابق.
    odoo = FakeOdoo(partners=[{"id": 42}], products=[])
    _wire(mod, monkeypatch, conn=conn, odoo=odoo)

    await mod.sync_procurement_orders_to_odoo()

    # لا أمر شراء يُنشأ (حلّ المنتج يسبق الكتابة).
    assert not any(model == "purchase.order" for model, _ in odoo.created)
    assert not any(
        v.get("product_id") == 1 for model, v in odoo.created if model == "purchase.order.line"
    )
    failed = [q for q, _ in conn.executes if "odoo_sync_status='failed'" in q]
    assert failed, "يجب تعليم الأمر failed عند تعذّر حلّ المنتج"


# ══════════════════════════════════════════════════════════════
# (ج) إسناد tenant_id للكتالوج — عالميّ افتراضيّاً، صريح عند الضبط
# ══════════════════════════════════════════════════════════════
def _capture_inventory_insert(conn):
    """يُعيد (query, args) لأوّل INSERT INTO inventory_stock نُفّذ."""
    for q, a in conn.executes:
        if "INSERT INTO inventory_stock" in q:
            return q, a
    return None, None


@pytest.mark.asyncio
async def test_catalog_global_when_tenant_unset(monkeypatch):
    mod = _load_main(monkeypatch, sync_tenant=None)
    assert mod.ODOO_SYNC_TENANT_ID is None
    conn = FakeConn(orders=[], items=[])
    odoo = FakeOdoo(
        products=[{"id": 5, "name": "Urea", "standard_price": 3.0}],
    )
    _wire(mod, monkeypatch, conn=conn, odoo=odoo)

    await mod.sync_products()

    q, a = _capture_inventory_insert(conn)
    assert q is not None, "يجب تنفيذ INSERT INTO inventory_stock"
    # كتالوج عالميّ: لا عمود tenant_id في الكتابة.
    assert "tenant_id" not in q, "بلا ODOO_SYNC_TENANT_ID يجب ألّا يُكتب tenant_id (كتالوج عالميّ)"


@pytest.mark.asyncio
async def test_catalog_explicit_tenant_when_set(monkeypatch):
    tenant = "11111111-1111-1111-1111-111111111111"
    mod = _load_main(monkeypatch, sync_tenant=tenant)
    assert mod.ODOO_SYNC_TENANT_ID == tenant
    conn = FakeConn(orders=[], items=[])
    odoo = FakeOdoo(
        products=[{"id": 5, "name": "Urea", "standard_price": 3.0}],
    )
    _wire(mod, monkeypatch, conn=conn, odoo=odoo)

    await mod.sync_products()

    q, a = _capture_inventory_insert(conn)
    assert q is not None
    assert "tenant_id" in q, "مع ODOO_SYNC_TENANT_ID يجب كتابة عمود tenant_id"
    # القيمة المُمرَّرة هي tenant_id الصريح (لا مُلفَّق) — آخر وسيط قبل NOW().
    assert tenant in a, "يجب تمرير tenant_id الصريح المضبوط"


@pytest.mark.asyncio
async def test_suppliers_catalog_global_when_tenant_unset(monkeypatch):
    mod = _load_main(monkeypatch, sync_tenant=None)
    conn = FakeConn(orders=[], items=[])
    odoo = FakeOdoo(
        partners=[{"id": 7, "name": "Acme", "supplier_rank": 1}],
    )
    _wire(mod, monkeypatch, conn=conn, odoo=odoo)

    await mod.sync_suppliers()

    inserts = [q for q, _ in conn.executes if "INSERT INTO suppliers" in q]
    assert inserts, "يجب تنفيذ INSERT INTO suppliers"
    assert all("tenant_id" not in q for q in inserts), (
        "بلا ODOO_SYNC_TENANT_ID يجب ألّا يُكتب tenant_id للمورّدين (كتالوج عالميّ)"
    )

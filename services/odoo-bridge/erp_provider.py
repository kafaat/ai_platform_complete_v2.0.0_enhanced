"""
erp_provider.py — تجريد مزوّد ERP (Odoo / ERPNext / معطّل).

يعزل منطق المزامنة عن المزوّد المحدّد، فيُمكن التبديل بمتغيّر بيئة واحد:
  ERP_PROVIDER = odoo | erpnext | none

- odoo:    يستخدم OdooClient (JSON-RPC) — الموجود.
- erpnext:  يستخدم ERPNextClient (REST API لإطار Frappe).
- none:    يعطّل ERP تماماً (NullProvider) — النظام يعمل بلا ERP.

صدق: ERPNextClient كود حقيقي لـFrappe REST API، لكنّه يحتاج خادم ERPNext
حيّاً على جهازك لاختباره فعليّاً. NullProvider يجعل تعطيل ERP آمناً (لا أعطال).
"""

from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod
from datetime import UTC, datetime

logger = logging.getLogger("erp_provider")


# ═══════════════════════════════════════════════════════════════════
# الواجهة المشتركة — كلّ مزوّد ERP يحقّقها
# ═══════════════════════════════════════════════════════════════════
class ERPProvider(ABC):
    """واجهة موحّدة لأيّ مزوّد ERP (Odoo/ERPNext/...)."""

    name: str = "abstract"

    @abstractmethod
    async def authenticate(self) -> bool:
        """تسجيل الدخول. True عند النجاح."""
        ...

    @abstractmethod
    async def list_products(self, since: str | None = None) -> list[dict]:
        """يُرجِع المنتجات الموحّدة: [{name, code, category, uom, cost, supplier}]."""
        ...

    @abstractmethod
    async def list_suppliers(self, since: str | None = None) -> list[dict]:
        """يُرجِع المورّدين: [{name, code, phone, email}]."""
        ...

    @abstractmethod
    async def list_warehouses(self) -> list[dict]:
        """يُرجِع المستودعات/المواقع: [{name, code}]."""
        ...

    @abstractmethod
    async def push_field_cost(self, cost: dict) -> bool:
        """يدفع تكلفة حقل إلى ERP (محاسبة تحليليّة). True عند النجاح."""
        ...

    @abstractmethod
    async def health(self) -> dict:
        """حالة الاتّصال بالمزوّد."""
        ...


# ═══════════════════════════════════════════════════════════════════
# مزوّد معطّل (none) — يجعل إيقاف ERP آمناً
# ═══════════════════════════════════════════════════════════════════
class NullProvider(ERPProvider):
    """مزوّد فارغ — ERP معطّل. النظام يعمل بلا أيّ ERP (صدق: لا اختراع)."""

    name = "none"

    async def authenticate(self) -> bool:
        return True  # لا مصادقة مطلوبة

    async def list_products(self, since=None) -> list[dict]:
        return []

    async def list_suppliers(self, since=None) -> list[dict]:
        return []

    async def list_warehouses(self) -> list[dict]:
        return []

    async def push_field_cost(self, cost: dict) -> bool:
        # ERP معطّل — التكلفة تُحفَظ محلّيّاً في farm_ledger فقط
        logger.info("ERP معطّل (none) — تكلفة الحقل تبقى في farm_ledger المحلّي")
        return True

    async def health(self) -> dict:
        return {
            "provider": "none",
            "status": "disabled",
            "note": "ERP معطّل — النظام يعمل بـfarm_ledger المحلّي فقط",
        }


# ═══════════════════════════════════════════════════════════════════
# مزوّد ERPNext (Frappe REST API)
# ═══════════════════════════════════════════════════════════════════
class ERPNextProvider(ERPProvider):
    """مزوّد ERPNext عبر Frappe REST API.

    صدق: كود حقيقي لـFrappe REST، يحتاج خادم ERPNext حيّاً لاختباره.
    التوثيق: https://frappeframework.com/docs/user/en/api/rest
    """

    name = "erpnext"

    def __init__(
        self,
        url: str,
        api_key: str,
        api_secret: str,
        *,
        expense_account: str = "",
        credit_account: str = "",
        cost_center: str = "",
        company: str = "",
    ):
        self.url = url.rstrip("/")
        self.api_key = api_key
        self.api_secret = api_secret
        # ربط الحسابات (خاصّ بكلّ تثبيت — يُضبط عبر env، لا يُفبرك).
        # عند غيابه يبقى push_field_cost مُعلِناً NotImplementedError بصدق.
        self.expense_account = expense_account
        self.credit_account = credit_account
        self.cost_center = cost_center
        self.company = company
        self._client = None

    def _headers(self) -> dict:
        # مصادقة Frappe: token <key>:<secret> في رأس Authorization
        return {
            "Authorization": f"token {self.api_key}:{self.api_secret}",
            "Content-Type": "application/json",
        }

    async def _get_client(self):
        if self._client is None:
            import httpx

            self._client = httpx.AsyncClient(timeout=30.0, headers=self._headers())
        return self._client

    async def _get_list(
        self, doctype: str, fields: list, filters: list | None = None
    ) -> list[dict]:
        """يجلب قائمة مستندات Frappe (resource API)."""
        try:
            client = await self._get_client()
            import json

            params = {"fields": json.dumps(fields), "limit_page_length": 0}
            if filters:
                params["filters"] = json.dumps(filters)
            r = await client.get(f"{self.url}/api/resource/{doctype}", params=params)
            r.raise_for_status()
            return r.json().get("data", [])
        except Exception as e:  # noqa: BLE001 — صدق: فشل → فارغ لا اختراع
            logger.warning(f"ERPNext {doctype} تعذّر: {e}")
            return []

    async def authenticate(self) -> bool:
        # Frappe token-based: لا جلسة، نختبر بنداء خفيف.
        # صدق مهمّ: frappe.auth.get_logged_user يُرجِع HTTP 200 مع body="Guest"
        # عند توكن خاطئ/فارغ (لا يُرجِع 401)؛ فالاكتفاء بـstatus_code==200
        # إيجابيّة كاذبة. الشرط الصحيح: المستخدم مسجَّل وليس Guest.
        try:
            client = await self._get_client()
            r = await client.get(f"{self.url}/api/method/frappe.auth.get_logged_user")
            if r.status_code != 200:
                return False
            try:
                user = r.json().get("message")
            except Exception as je:  # noqa: BLE001 — صدق: JSON غير صالح → فشل لا اختراع
                logger.warning(f"ERPNext auth: استجابة غير JSON ({je})")
                return False
            return user not in (None, "", "Guest")
        except Exception as e:  # noqa: BLE001
            logger.warning(f"ERPNext auth تعذّر: {e}")
            return False

    async def list_products(self, since=None) -> list[dict]:
        # Item هو منتج Frappe؛ نوحّده لمخطّط الجسر
        items = await self._get_list(
            "Item", ["item_code", "item_name", "item_group", "stock_uom", "standard_rate"]
        )
        return [
            {
                "name": i.get("item_name"),
                "code": i.get("item_code"),
                "category": i.get("item_group", "General"),
                "uom": i.get("stock_uom", "Unit"),
                "cost": i.get("standard_rate", 0.0),
                "supplier": None,
            }
            for i in items
        ]

    async def list_suppliers(self, since=None) -> list[dict]:
        sups = await self._get_list("Supplier", ["supplier_name", "name", "mobile_no", "email_id"])
        return [
            {
                "name": s.get("supplier_name"),
                "code": s.get("name"),
                "phone": s.get("mobile_no"),
                "email": s.get("email_id"),
            }
            for s in sups
        ]

    async def list_warehouses(self) -> list[dict]:
        whs = await self._get_list("Warehouse", ["warehouse_name", "name"])
        return [{"name": w.get("warehouse_name"), "code": w.get("name")} for w in whs]

    async def push_field_cost(self, cost: dict) -> bool:
        """دفع تكلفة حقل إلى ERPNext كقيد محاسبيّ (Journal Entry).

        يبني قيداً متوازناً (مدين = دائن) **فقط** عند ضبط ربط الحسابات عبر
        البيئة (ERPNEXT_EXPENSE_ACCOUNT/ERPNEXT_CREDIT_ACCOUNT/COST_CENTER/
        COMPANY). الحسابات خاصّة بكلّ تثبيت — لا تُفبرك. عند غيابها يُعلَن
        الحدّ بصراحة (NotImplementedError) بدل محاولة فاشلة دوماً.

        البنية (أفضل ممارسة Frappe): voucher_type=Journal Entry، سطران
        accounts[] متوازنان (مصروف مدين / نقد أو دائنون دائن)، مع cost_center
        وcompany. المجموع المدين = الدائن (شرط Frappe الإلزامي).
        """
        amount = cost.get("amount")
        if amount is None or float(amount) <= 0:
            raise ValueError(f"push_field_cost يحتاج amount موجباً (وصل: {amount!r})")

        # ربط الحسابات غير مُعدّ → نُعلن الحدّ بصدق (لا فبركة أرقام حسابات)
        if not (self.expense_account and self.credit_account and self.company):
            raise NotImplementedError(
                "ERPNext push_field_cost: ربط حسابات قيد اليوميّة غير مُعدّ. "
                "اضبط ERPNEXT_EXPENSE_ACCOUNT + ERPNEXT_CREDIT_ACCOUNT + "
                "ERPNEXT_COMPANY (+ COST_CENTER) لهذا التثبيت — لم تُفبرك "
                f"أرقام حسابات. (amount={amount}, "
                f"description={cost.get('description')!r})"
            )

        amt = round(float(amount), 2)
        row_debit = {
            "account": self.expense_account,  # مصروف الحقل (مدين)
            "debit_in_account_currency": amt,
            "credit_in_account_currency": 0,
        }
        row_credit = {
            "account": self.credit_account,  # نقد/دائنون (دائن)
            "debit_in_account_currency": 0,
            "credit_in_account_currency": amt,
        }
        if self.cost_center:
            row_debit["cost_center"] = self.cost_center
            row_credit["cost_center"] = self.cost_center

        entry = {
            "doctype": "Journal Entry",
            "voucher_type": "Journal Entry",
            "company": self.company,
            "posting_date": cost.get("posting_date") or datetime.now(UTC).strftime("%Y-%m-%d"),
            "user_remark": cost.get("description", "SAHOOL field cost"),
            "accounts": [row_debit, row_credit],  # متوازن: مدين = دائن = amt
        }

        try:
            client = await self._get_client()
            resp = await client.post(
                f"{self.url}/api/resource/Journal Entry",
                headers=self._headers(),
                json={"data": entry},
            )
            if resp.status_code in (200, 201):
                return True
            logger.warning(
                "ERPNext push_field_cost رُفض (%s): %s", resp.status_code, resp.text[:200]
            )
            return False
        except Exception as e:  # noqa: BLE001 — لا نخفي الفشل، نُرجِع False
            logger.warning("ERPNext push_field_cost تعذّر: %s", e)
            return False

    async def health(self) -> dict:
        ok = await self.authenticate()
        return {
            "provider": "erpnext",
            "url": self.url,
            "status": "connected" if ok else "unreachable",
        }


# ═══════════════════════════════════════════════════════════════════
# مزوّد Odoo — يلفّ OdooClient الموجود بالواجهة الموحّدة
# ═══════════════════════════════════════════════════════════════════
class OdooProvider(ERPProvider):
    """يلفّ OdooClient الموجود (JSON-RPC) بالواجهة الموحّدة.

    يعيد استخدام منطق Odoo المبنيّ والمُختبَر — لا يكرّره.
    """

    name = "odoo"

    def __init__(self, odoo_client):
        self.odoo = odoo_client  # OdooClient الموجود

    async def authenticate(self) -> bool:
        try:
            await self.odoo.authenticate()
            return self.odoo.uid is not None
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Odoo auth تعذّر: {e}")
            return False

    async def list_products(self, since=None) -> list[dict]:
        domain = []
        rows = await self.odoo.search_read(
            "product.product", domain, ["name", "default_code", "categ_id", "uom_id", "list_price"]
        )
        out = []
        for p in rows:
            cat = p.get("categ_id")[1] if isinstance(p.get("categ_id"), list) else "General"
            uom = p.get("uom_id")[1] if isinstance(p.get("uom_id"), list) else "Unit"
            out.append(
                {
                    "name": p.get("name"),
                    "code": p.get("default_code"),
                    "category": cat,
                    "uom": uom,
                    "cost": p.get("list_price", 0.0),
                    "supplier": None,
                }
            )
        return out

    async def list_suppliers(self, since=None) -> list[dict]:
        rows = await self.odoo.search_read(
            "res.partner", [["supplier_rank", ">", 0]], ["name", "phone", "email"]
        )
        return [
            {
                "name": s.get("name"),
                "code": str(s.get("id", "")),
                "phone": s.get("phone"),
                "email": s.get("email"),
            }
            for s in rows
        ]

    async def list_warehouses(self) -> list[dict]:
        rows = await self.odoo.search_read("stock.warehouse", [], ["name", "code"])
        return [{"name": w.get("name"), "code": w.get("code")} for w in rows]

    async def push_field_cost(self, cost: dict) -> bool:
        # يعتمد المحاسبة التحليليّة في Odoo (analytic account)
        try:
            await self.odoo.call(
                "account.analytic.line",
                "create",
                [
                    {
                        "name": cost.get("description", "SAHOOL field cost"),
                        "amount": -abs(cost.get("amount", 0.0)),
                    }
                ],
            )
            return True
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Odoo push_field_cost تعذّر: {e}")
            return False

    async def health(self) -> dict:
        ok = await self.authenticate()
        return {"provider": "odoo", "status": "connected" if ok else "unreachable"}


# ═══════════════════════════════════════════════════════════════════
# مصنع المزوّد — يختار حسب ERP_PROVIDER
# ═══════════════════════════════════════════════════════════════════
def get_erp_provider(odoo_client=None) -> ERPProvider:
    """يُرجِع المزوّد المختار عبر ERP_PROVIDER (odoo|erpnext|none).

    odoo هو الافتراضي (التوافق الخلفي). أيّ قيمة غير معروفة → none (آمن).
    odoo_client: OdooClient الموجود (يُمرَّر لـOdooProvider).
    """
    provider = os.getenv("ERP_PROVIDER", "odoo").strip().lower()

    if provider in ("none", "disabled", "off"):
        logger.info("ERP_PROVIDER=none → ERP معطّل")
        return NullProvider()

    if provider == "erpnext":
        url = os.getenv("ERPNEXT_URL", "http://sahool-erpnext:8000")
        key = os.getenv("ERPNEXT_API_KEY", "")
        secret = os.getenv("ERPNEXT_API_SECRET", "")
        if not key or not secret:
            logger.warning("ERPNext مختار لكن المفاتيح فارغة → none (صدق: لا اتّصال وهمي)")
            return NullProvider()
        logger.info("ERP_PROVIDER=erpnext")
        # ربط حسابات Journal Entry (اختياري — push_field_cost يبقى معطّلاً
        # بصدق حتّى تُضبط الحسابات الثلاثة الإلزاميّة).
        return ERPNextProvider(
            url,
            key,
            secret,
            expense_account=os.getenv("ERPNEXT_EXPENSE_ACCOUNT", ""),
            credit_account=os.getenv("ERPNEXT_CREDIT_ACCOUNT", ""),
            cost_center=os.getenv("ERPNEXT_COST_CENTER", ""),
            company=os.getenv("ERPNEXT_COMPANY", ""),
        )

    if provider == "odoo":
        if odoo_client is None:
            logger.warning("ERP_PROVIDER=odoo لكن لا OdooClient مُمرَّر → none مؤقّتاً")
            return NullProvider()
        logger.info("ERP_PROVIDER=odoo (الافتراضي)")
        return OdooProvider(odoo_client)

    logger.warning(f"ERP_PROVIDER={provider} غير معروف → none (آمن)")
    return NullProvider()

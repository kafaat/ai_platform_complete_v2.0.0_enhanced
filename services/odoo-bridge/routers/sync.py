"""routers/sync.py — تشغيل المزامنة اليدويّة (Manual Sync)
======================================================================
شريحة من تفكيك ``main.py`` إلى وحدات ``APIRouter`` (سلوك محفوظ).

نُقل المُعالِج حرفيّاً مع تغيير ``@app`` إلى ``@router``؛ المسار/المخرجات
مطابقة. التبعيّات المشتركة (الحالة/المساعِدات) تبقى في ``main`` وتُشار إليها
عبر ``main.X``. ``register_routers(app)`` يضمّ هذا الراوتر بلا prefix.
"""

from __future__ import annotations

import asyncio

import main
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

router = APIRouter()

# مهلة probe المزوّد (ثوان) — قصيرة لتجنّب انتظار مفتوح على مسار المزامنة.
_PROVIDER_PROBE_TIMEOUT: float = 5.0


async def _probe_erp_or_503(provider) -> None:
    """يستدعي health() المزوّد بمهلة؛ 503 إن كان المزوّد متاحاً لكن غير مستجيب.

    يُستدعى بعد بوّابة 424 (provider.name != 'none') — أيّ استثناء يُحوَّل إلى
    503 Failed Service Dependency بدلاً من 500 الداخلي.
    يُثبت ضمن وثيقة إقفال ERP-BRIDGE-FIX-01 أنّ fail-closed يحدث عند مسار القدرة
    لحظة استدعائها (لا عند إقلاع الحاوية، ولا في /readyz أو /healthz).
    """
    try:
        result = await asyncio.wait_for(provider.health(), timeout=_PROVIDER_PROBE_TIMEOUT)
    except TimeoutError:
        raise HTTPException(
            503,
            {
                "error": "erp_provider_timeout",
                "provider": provider.name,
                "detail": (
                    f"ERP provider '{provider.name}' probe timed out "
                    f"({_PROVIDER_PROBE_TIMEOUT}s). "
                    "Retry when ERP is available. "
                    "Check /v1/readyz/capabilities for capability status."
                ),
            },
        ) from None
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            503,
            {
                "error": "erp_provider_unreachable",
                "provider": provider.name,
                "detail": str(exc)[:200],
            },
        ) from exc

    status = result.get("status", "")
    if status not in ("connected", "disabled", "reported"):
        raise HTTPException(
            503,
            {
                "error": "erp_provider_unreachable",
                "provider": provider.name,
                "erp_status": status,
                "detail": (
                    f"ERP provider '{provider.name}' is configured but unreachable "
                    f"(health={status!r}). "
                    "Retry when ERP is available. "
                    "Check /v1/readyz/capabilities for live status."
                ),
            },
        )


@router.post("/v1/sync")
async def trigger_sync(
    req: main.SyncRequest,
    background_tasks: BackgroundTasks,
    _auth: dict = Depends(main.require_auth),
):
    """Trigger manual sync — يتطلّب توكناً صالحاً (كان مكشوفاً).

    الأمان: المزامنة تكتب لـERP — تتطلّب مصادقة (نفس require_auth المطبَّقة
    على نقاط القراءة).

    fail-closed (ERP-BRIDGE-FIX-01):
      424 — مزوّد ERP غير مهيّأ (none/مفاتيح فارغة): لا إرسال وهميّ، لا كتابة جزئية.
      503 — مزوّد مهيّأ لكن غير مستجيب: probe بمهلة 5s قبل الإضافة للطابور.
    كلا الرفضين يحدثان قبل أيّ background_tasks.add_task() — ضمان لا كتابة جزئية.
    الحالة الطبيعية معروضة كبيانات في /v1/readyz/capabilities (HTTP 200 دائماً).
    """
    provider = main.get_active_erp_provider()

    # بوّابة ١: مزوّد غير مهيّأ → 424 (قبل أيّ I/O)
    if provider.name == "none":
        raise HTTPException(
            424,
            {
                "error": "erp_provider_not_configured",
                "provider": provider.name,
                "detail": (
                    "ERP provider is not configured or credentials are missing. "
                    "Set ERP_PROVIDER and the corresponding credentials "
                    "(ERPNEXT_API_KEY/ERPNEXT_API_SECRET or ODOO_*). "
                    "Check /v1/readyz/capabilities for current capability status."
                ),
            },
        )

    # بوّابة ٢: مزوّد مهيّأ لكن غير مستجيب → 503 (probe بمهلة)
    await _probe_erp_or_503(provider)

    if req.entity == "all" or req.entity == "products":
        background_tasks.add_task(main.sync_products)
    if req.entity == "all" or req.entity == "suppliers":
        background_tasks.add_task(main.sync_suppliers)
    if req.entity == "all" or req.entity == "warehouses":
        background_tasks.add_task(main.sync_warehouses)
    if req.entity == "all" or req.entity == "procurement":
        if main.get_active_erp_provider().name == "odoo":
            background_tasks.add_task(main.sync_procurement_orders_to_odoo)
        elif req.entity == "procurement":
            raise HTTPException(409, "procurement_sync_requires_odoo_provider")
    if req.entity == "all" or req.entity == "costs":
        background_tasks.add_task(main.sync_field_costs_to_odoo)
    return {"status": "queued", "entity": req.entity, "direction": req.direction}

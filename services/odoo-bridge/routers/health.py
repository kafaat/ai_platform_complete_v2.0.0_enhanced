"""routers/health.py — فحوص الحياة والجاهزية والقدرات
=============================================================
المستويات الثلاثة المستقلة — الفصل يمنع إدانة الحاوية بذنب قدرة خارجية اختيارية:

  /healthz               — حياة العملية (process alive): استجابة خالصة — لا DB، لا ERP.
                           healthcheck في Compose يضرب هذه النقطة دائماً (ثابت).
  /health                — مرادف /healthz (للتوافق الخلفيّ).
  /readyz                — الجاهزية الداخلية: DB داخلي جاهز ⇒ 200، غير ذلك 503.
                           لا يشترط ERP الخارجي الاختياري.
  /readyz/capabilities   — قدرات ERP (HTTP 200 دائماً): حالة المزوّد كبيانات تشغيلية لا
                           كحكم على صحة الحاوية. fail-closed يحدث عند مسار القدرة
                           لحظة استدعائها (POST /sync) لا عند إقلاع الحاوية.

ERR-BRIDGE-001 (مغلق بالالتزام 36e8656): السبب الجذري كان CREATE TABLE في
_run_migrations() يفشل برمجياً (InsufficientPrivilegeError على schema public)
قبل أن يبدأ الخادم في تلقي الطلبات. فصل المستويات هنا تصليح معماري مستقل
يمنع فئة أخرى: healthcheck يضرب مساراً يشترط قدرة خارجية ⇒ الحاوية تُدان بذنبها.
"""

from __future__ import annotations

import erp_runtime as _erp_rt
import main
from fastapi import APIRouter, HTTPException

router = APIRouter()


@router.get("/healthz")
@router.get("/health")
async def healthz():
    """حياة العملية — process alive.

    نقطة خالصة: لا استدعاء DB، لا استدعاء ERP، لا I/O من أيّ نوع.
    healthcheck في Compose يضرب هذه النقطة فقط — عقد لا يُكسَر.
    """
    return {"status": "alive", "service": "erp-bridge"}


@router.get("/readyz")
async def readyz():
    """الجاهزية الداخلية — internal readiness.

    يفحص قاعدة البيانات الداخلية فقط (SELECT 1). لا يشترط ERP الخارجي الاختياري:
    حالة ERP معلومة تشغيلية معروضة في /readyz/capabilities (HTTP 200 دائماً).
    تعذّر DB ⇒ 503. ERP غير مهيّأ لا يُفضي إلى 503 هنا.
    """
    pool = _erp_rt._pool
    if pool is not None:
        try:
            async with pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
        except Exception as e:
            main.logger.warning("readyz: قاعدة البيانات غير جاهزة — %s", e)
            raise HTTPException(
                503,
                {
                    "status": "not_ready",
                    "database": {"reachable": False, "reason": str(e)[:200]},
                },
            ) from e
        return {
            "status": "ready",
            "version": "9.1.0",
            "database": {"reachable": True, "schema_ready": True},
        }
    # لا DATABASE_URL مضبوطة — وضع متدرّج معلَن (جاهز بصدق بلا DB)
    return {
        "status": "ready",
        "version": "9.1.0",
        "database": {"reachable": False, "configured": False},
    }


@router.get("/readyz/capabilities")
async def readyz_capabilities():
    """قدرات ERP — معلومة تشغيلية، HTTP 200 دائماً.

    يعرض حالة المزوّد المختار كبيانات لا كحكم صحة — الحاوية حيّة بلا ERP مهيّأ
    ليست مريضة؛ هي صادقة العجز عن قدرة واحدة. fail-closed يحدث عند مسار القدرة
    لحظة استدعائها (POST /sync بلا ERP ⇒ 424/503 مُصنَّف) لا هنا.
    لا probe شبكيّ هنا — للمعلومة الحيّة اقرأ /erp/config.
    """
    provider_name = main._selected_erp_provider()
    configured = provider_name not in ("none", "")
    return {
        "status": "reported",
        "capabilities": {
            "erp_provider": provider_name,
            "erp_configured": configured,
            "note": (
                "network probe not performed here — call /erp/config or /sync for live ERP status"
            ),
        },
    }

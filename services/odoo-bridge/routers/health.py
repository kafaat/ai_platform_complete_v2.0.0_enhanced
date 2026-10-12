"""routers/health.py — فحوص الحياة والجاهزية والقدرات
=============================================================
المستويات الثلاثة المستقلة — الفصل يمنع إدانة الحاوية بذنب قدرة خارجية اختيارية:

  /healthz               — حياة العملية (process alive): استجابة خالصة — لا DB، لا ERP.
                           healthcheck في Compose يضرب هذه النقطة دائماً (ثابت).
  /health                — مرادف /healthz (للتوافق الخلفيّ).
  /readyz                — جاهزية أداء الوظيفة: DB داخلي جاهز **و** ERP المختار مهيّأ ومستجيب
                           ⇒ 200؛ غير ذلك 503. الجسر بلا ERP لا يفعل شيئاً، فلا يُعلن الجاهزيّة
                           بلاه (قرار المالك §3.4، 2026-09-30 —
                           ERP-BRIDGE-RUNS-WITHOUT-ODOO-AND-READYZ-SAYS-READY-01؛ كان: DB ⇒ 200
                           ولو Odoo غائب). probe محدود المهلة، وجسم 503 رموزُ سبب لا عناوين/أسرار.
  /v1/readyz/capabilities — قدرات ERP (HTTP 200 دائماً): حالة المزوّد كبيانات تشغيلية لا
                           كحكم على صحة الحاوية. fail-closed يحدث عند مسار القدرة
                           لحظة استدعائها (POST /v1/sync) لا عند إقلاع الحاوية.

ERR-BRIDGE-001 (مغلق بالالتزام 36e8656): السبب الجذري كان CREATE TABLE في
_run_migrations() يفشل برمجياً (InsufficientPrivilegeError على schema public)
قبل أن يبدأ الخادم في تلقي الطلبات. فصل المستويات هنا تصليح معماري مستقل
يمنع فئة أخرى: healthcheck يضرب مساراً يشترط قدرة خارجية ⇒ الحاوية تُدان بذنبها.
"""

from __future__ import annotations

import asyncio

import erp_runtime as _erp_rt
import main
from fastapi import APIRouter, HTTPException

router = APIRouter()

# مهلة probe الـERP في /readyz (ثوانٍ) — أقصر من مهلة httpx (30ث) كي لا يُعلَّق مسبار الجاهزيّة.
_READYZ_ERP_PROBE_TIMEOUT: float = 3.0


async def _erp_readiness() -> tuple[bool, dict]:
    """هل ERP المختار مهيّأ ومستجيب؟ — (جاهز، وصف بلا أسرار).

    none/غير مهيّأ (ERPNext بلا عنوان ومفتاحين، أو ERP_PROVIDER=none) ⇒ غير جاهز بلا شبكة.
    Odoo بلا كلمة مرور ولا مفتاح API ⇒ غير مهيّأ بلا شبكة. غير ذلك: health() بمهلة؛
    status != "connected" أو مهلة أو استثناء ⇒ غير جاهز. الجسم رموزُ سبب فقط — لا URL ولا
    نصّ الاستثناء (قد يحمل ردّ Odoo أو عنواناً بمعرّفات).
    """
    provider = _erp_rt.get_active_erp_provider()
    info: dict = {"provider": provider.name, "configured": True, "reachable": False}
    if provider.name == "none":
        info.update(provider=main._selected_erp_provider(), configured=False)
        info["reason"] = "erp_not_configured"
        return False, info
    odoo_client = getattr(provider, "odoo", None)
    if odoo_client is not None and not (odoo_client.api_key or odoo_client.password):
        info.update(configured=False, reason="odoo_credentials_missing")
        return False, info
    try:
        health = await asyncio.wait_for(provider.health(), timeout=_READYZ_ERP_PROBE_TIMEOUT)
    except TimeoutError:
        info["reason"] = "erp_probe_timeout"
        return False, info
    except Exception as e:  # noqa: BLE001 — أيّ عطل probe ⇒ غير جاهز، بصنفه لا بنصّه
        info["reason"] = f"erp_probe_error:{type(e).__name__}"
        return False, info
    finally:
        # ERPNextProvider يبني httpx.AsyncClient لكلّ مزوّد جديد — أغلقه كي لا يتسرّب مع كلّ
        # مسبار. (OdooClient عالميّ مشترك عبر get_odoo() فلا يُغلَق هنا.)
        client = getattr(provider, "_client", None)
        if client is not None:
            await client.aclose()
    info["reachable"] = health.get("status") == "connected"
    if not info["reachable"]:
        info["reason"] = "erp_unreachable"
    return info["reachable"], info


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
    """جاهزية أداء الوظيفة — DB داخلي + ERP المختار.

    1) DB الداخلي (SELECT 1) إن ضُبط DATABASE_URL؛ تعذّره ⇒ 503.
    2) ERP المختار مهيّأ ومستجيب (probe بمهلة _READYZ_ERP_PROBE_TIMEOUT)؛ غير مهيّأ أو غير
       مستجيب ⇒ 503 — «خدمةٌ لا تعمل بلا تبعيّتها لا تُعلن الجاهزيّة بلاها» (قرار المالك §3.4).
    الحياة (/healthz) مستقلّة عن هذا كلّه ويضربها healthcheck في Compose — فغياب ERP يُخرج
    الجسر من التوجيه لا يُعيد تشغيله. /v1/readyz/capabilities يبقى معلومةً (200 دائماً).
    """
    database: dict = {"reachable": False, "configured": False}
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
        database = {"reachable": True, "schema_ready": True}
    # لا DATABASE_URL مضبوطة — وضع متدرّج معلَن (DB ليس شرطاً)، أمّا ERP فشرط.
    erp_ready, erp = await _erp_readiness()
    if not erp_ready:
        main.logger.warning("readyz: ERP غير جاهز — %s", erp.get("reason"))
        raise HTTPException(503, {"status": "not_ready", "database": database, "erp": erp})
    return {"status": "ready", "version": "9.1.0", "database": database, "erp": erp}


@router.get("/v1/readyz/capabilities")
async def readyz_capabilities():
    """قدرات ERP — معلومة تشغيلية، HTTP 200 دائماً.

    يعرض حالة المزوّد المختار كبيانات لا كحكم صحة — الحاوية حيّة بلا ERP مهيّأ
    ليست مريضة؛ هي صادقة العجز عن قدرة واحدة. fail-closed يحدث عند مسار القدرة
    لحظة استدعائها (POST /v1/sync بلا ERP ⇒ 424/503 مُصنَّف) لا هنا.
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
                "network probe not performed here — call /erp/config or /v1/sync for live ERP status"
            ),
        },
    }

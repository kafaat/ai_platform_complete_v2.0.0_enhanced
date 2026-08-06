"""api/routers/simulate.py — محاكاة what-if (WOFOST Scenario Simulation)
========================================================================
شريحة من تفكيك ``api/main.py`` إلى وحدات ``APIRouter`` (نمط P0).

الاعتماديّات المشتركة (التبعيات/النموذج) تبقى مُعرَّفة في ``api.main`` وتُستورَد من
هنا تفادياً لكسر ``_rebuild_pydantic_models`` واستيرادات الاختبارات. استيراد محرّك
WOFOST يبقى كسولاً داخل الدالّة كما كان. لتفادي الاستيراد الدائريّ: ``api.main``
يستورد هذا الموجِّه في نهايته فقط (بعد تعريف كلّ التبعيات/النماذج)، فيُحلّ الاستيراد.

سبعة أعطال مقيسة بتشغيل المحرّك (طقس محقون، ١٥٠ يوماً، بلا شبكة) — كلّها مُغلَقة هنا:

1. ``WOFOST-ENGINE-ERROR-READ-AS-SUCCESS-01`` — المحرّك **يُعيد** ``{"error": ...}``
   عند فشل الطقس ولا يرفع استثناءً، فـ``except`` لم يكن يعمل أبداً والاستجابة تخرج
   ``available: true`` بقيم ``null``. صار الفحص على المخرَج لا على الاستثناء.
2. ``WOFOST-SCENARIO-IS-DECORATIVE-01`` — ``scenario`` كان يُعاد صدىً بينما تُشغَّل
   الحالتان نفساهما. صار لكلّ سيناريو نسبة ريّ تُمرَّر إلى المحرّك وتُعلَن في المخرَج.
3–4. ``WOFOST-SILENT-PARAM-FALLBACK-01`` — «محصول لا وجود له» كان يُحسب قمحاً صلباً
   («٩.٧٨٨ ط/هـ» نفسها بالضبط) وتربة مجهولة تُحسب ``loam``، بينما تعيد الاستجابة اسم
   المستخدم. الاحتياط باقٍ (منعُ محصول غير مُدرَج يكسر نشراً شرعيّاً) لكنّه **مُفصَح**.
5. ``WOFOST-INVALID-DATE-SILENTLY-TODAY-01`` — ``except ValueError: pd = today()``
   يحاكي موسماً غير الذي طُلِب. صار رفضاً ``422``.
6. ``WOFOST-EXCEPTION-TEXT-LEAKS-01`` — نصّ الاستثناء كان يعود إلى العميل. صار رمزاً
   ثابتاً + رسالة عامّة، والتفاصيل في السجلّ مع ``correlation_id``.
7. ``WOFOST-WATER-SAVED-MIXES-QUANTITIES-01`` — ``water_saved_mm`` كان طرح
   ``irrigation_needed_mm`` بين الفرعين: مقدارٌ يخلط ماءً **مطبَّقاً** بعجزٍ **لم
   يُسدَّ** بحسب فرع ``irrigation`` (ويحمل معامل ×1.1 في أحد الفرعين)، فالطرح بلا
   معنى. صار مشتقّاً من ``irrigation_applied_mm`` — المقدار الوحيد المتجانس بين
   الفرعين — مع تسمية الأساس والاتّجاه صراحةً، وبلا قصٍّ عند الصفر.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from api.main import (
    UserSchema,
    WhatIfRequest,
    get_current_user,
)

router = APIRouter()

logger = logging.getLogger("sahool.simulate")

# نسبة الريّ لكلّ سيناريو — بيانات مُعلَنة، لا فرع مخفيّ. الفرع «الإجراء المقترَح»
# يُشغَّل دائماً بـ1.0 (الممارسة الموصى بها)، والفرع الآخر بالنسبة أدناه:
#   no_irrigation      0.0  — بلا ريّ (سلوك ما قبل الإصلاح لكلا السيناريوين)
#   recommended_action 0.0  — «لا إجراء» هو خطّ الأساس الذي يقارنه المُوائم
#   reduce_irrigation  0.5  — تقليل حقيقيّ؛ كان مطابقاً لـ0.0 قبل الإصلاح
SCENARIO_IRRIGATION_FRACTION: dict[str, float] = {
    "no_irrigation": 0.0,
    "recommended_action": 0.0,
    "reduce_irrigation": 0.5,
}
ACTION_IRRIGATION_FRACTION = 1.0


def _unavailable(field_id: str, code: str, note_ar: str, correlation_id: str) -> dict[str, Any]:
    """استجابة تعذّر موحّدة: رمز ثابت للآلة، نصّ عامّ للإنسان، تفاصيل في السجلّ فقط."""
    return {
        "field_id": field_id,
        "available": False,
        "error_code": code,
        # مُبقًى للتوافق الخلفيّ مع مستهلكين يقرؤون `error`؛ نصّه عامّ الآن.
        "error": note_ar,
        "note_ar": note_ar,
        "correlation_id": correlation_id,
    }


@router.post("/api/v1/simulate/what-if")
async def simulate_what_if(
    req: WhatIfRequest,
    user: UserSchema = Depends(get_current_user),
):
    """يحاكي أثر سيناريو (تقليل/إيقاف الريّ) على المحصول والماء.

    Runtime Cohesion: يغذّي حلقة القرار بأثر متوقّع للإجراء المقترَح. يشغّل
    WOFOST مرّتين (الإجراء الموصى به مقابل السيناريو) ويقارن. صدق: عند تعذّر
    النموذج/الطقس يُعلَن (لا أرقام مخترَعة). lat/lon إلزاميّان للطقس الحيّ.
    """
    correlation_id = uuid.uuid4().hex[:16]

    if req.lat is None or req.lon is None:
        return _unavailable(
            req.field_id,
            "MISSING_LOCATION",
            "lat/lon مطلوبان للطقس الحيّ — لا محاكاة بلا موقع",
            correlation_id,
        )
    # استيراد نظاميّ من الحزمة المملوكة (WOFOST Runtime Closure): المحرّك صار في
    # shared/wofost/ — داخل سياق Docker (COPY shared/) — فلا تحميل ديناميكيّ
    # بمسار ملفّ، ولا «غير متاح على هذا المسار» صامت في الإنتاج. يبقى الاستيراد
    # داخل الدالّة حفاظاً على عقدة التهيئة (api.main يستورد هذا الموجِّه أخيراً).
    try:
        from shared.wofost import simulate_wofost as _simulate_wofost
    except ImportError:
        logger.exception("what-if[%s]: تعذّر استيراد shared.wofost", correlation_id)
        return _unavailable(
            req.field_id,
            "ENGINE_IMPORT_FAILED",
            "تعذّر استيراد محرّك المحاكاة",
            correlation_id,
        )

    class _Eng:
        """موائم ضئيل يحفظ شكل الاستدعاء السابق (_eng.simulate_wofost)."""

        simulate_wofost = staticmethod(_simulate_wofost)

    _eng = _Eng()

    from datetime import date as _date

    # تاريخ غير صالح كان يصير `today()` صامتاً — فتُحاكى سَنةٌ غير المطلوبة وتُنسَب
    # نتيجتها إلى تاريخ المستخدم. الرفض هنا أصدق من رقمٍ يخصّ موسماً آخر.
    if req.planting_date:
        try:
            pd = _date.fromisoformat(req.planting_date)
        except ValueError:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"planting_date غير صالح: {req.planting_date!r} — يُتوقَّع تاريخ ISO (YYYY-MM-DD)"
                ),
            ) from None
    else:
        pd = _date.today()

    scenario_fraction = SCENARIO_IRRIGATION_FRACTION[req.scenario]

    async def _run(fraction: float):
        return await _eng.simulate_wofost(
            req.field_id,
            req.crop,
            req.soil_type,
            req.lat,
            req.lon,
            pd,
            irrigation=fraction > 0,
            irrigation_fraction=fraction,
        )

    try:
        action = await _run(ACTION_IRRIGATION_FRACTION)  # الإجراء المقترَح (ريّ كامل)
        scenario = await _run(scenario_fraction)  # السيناريو المطلوب
    except Exception:  # noqa: BLE001 — صدق: الطقس/النموذج تعذّر
        logger.exception("what-if[%s]: المحاكاة رفعت استثناءً", correlation_id)
        return _unavailable(
            req.field_id, "SIMULATION_FAILED", "تعذّرت المحاكاة (طقس/نموذج)", correlation_id
        )

    # المحرّك **يُعيد** {"error": ...} عند فشل الطقس ولا يرفع — فالفحص على المخرَج.
    # بدونه تخرج الاستجابة `available: true` وكلّ أرقامها `null`: ادّعاء نجاحٍ لم يقع.
    for label, result in (("action", action), ("scenario", scenario)):
        if not isinstance(result, dict) or result.get("error"):
            detail = result.get("error") if isinstance(result, dict) else type(result).__name__
            logger.warning("what-if[%s]: فرع %s أعاد تعذّراً: %s", correlation_id, label, detail)
            return _unavailable(
                req.field_id, "SIMULATION_FAILED", "تعذّرت المحاكاة (طقس/نموذج)", correlation_id
            )

    a_yield = action.get("simulation", {}).get("yield_t_ha")
    s_yield = scenario.get("simulation", {}).get("yield_t_ha")
    a_applied = action.get("water_balance", {}).get("irrigation_applied_mm")
    s_applied = scenario.get("water_balance", {}).get("irrigation_applied_mm")

    # الطرح على الماء **المطبَّق** — المقدار المتجانس الوحيد بين الفرعين. لا يُقَصّ
    # عند الصفر: نسبة أقلّ تُشغّل عتبة الإجهاد أكثر، فقد تُطبَّق كمّيّة أكبر إجمالاً؛
    # وقتها الجواب الصادق «زيادة» لا صفرٌ يُخفيها.
    water_saved = None
    direction = None
    if a_applied is not None and s_applied is not None:
        water_saved = round(a_applied - s_applied, 1)
        direction = (
            "reduction" if water_saved > 0 else ("increase" if water_saved < 0 else "unchanged")
        )

    # هل "الإجراء المقترَح" (الريّ) يُجدي؟ مُجدٍ إن رفع المحصول >2% فوق السيناريو.
    helps = None
    if a_yield is not None and s_yield is not None:
        helps = a_yield > s_yield * 1.02

    resolution = action.get("parameter_resolution") or {}
    degraded = bool(resolution.get("degraded"))
    note_ar = None
    if degraded:
        note_ar = (
            "مُدخَل غير مُدرَج في جداول المحرّك؛ حُسِبت المحاكاة ببارامترات بديلة "
            f"(محصول: {action.get('resolved_crop')} · تربة: {action.get('resolved_soil_type')}) "
            "— الأرقام تخصّ البديل لا المُدخَل"
        )

    return {
        "field_id": req.field_id,
        "available": True,
        "scenario": req.scenario,
        "scenario_irrigation_fraction": scenario_fraction,
        "action_irrigation_fraction": ACTION_IRRIGATION_FRACTION,
        # خطّ الأساس = السيناريو المطلوب؛ الإجراء = الريّ الموصى به (قيمتان متمايزتان
        # حتّى تكون recommended_action_helps مقارنةً فعليّةً لا قيمةً بنفسها).
        "baseline_yield_t_ha": s_yield,  # خطّ الأساس (السيناريو) — توافق خلفيّ
        "no_action_yield_t_ha": s_yield,  # مرادف صريح لخطّ الأساس (توافق خلفي)
        "scenario_yield_t_ha": s_yield,  # الاسم الصريح للمقدار نفسه
        "action_yield_t_ha": a_yield,  # الإجراء المقترَح (الريّ الموصى به)
        "action_irrigation_applied_mm": a_applied,
        "scenario_irrigation_applied_mm": s_applied,
        "water_saved_mm": water_saved,
        "water_saved_basis": "irrigation_applied_mm",
        "water_use_direction": direction,
        "recommended_action_helps": helps,
        "parameter_resolution": resolution,
        "degraded": degraded,
        "note_ar": note_ar,
    }

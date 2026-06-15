"""api/routers/simulate.py — محاكاة what-if (WOFOST Scenario Simulation)
========================================================================
شريحة من تفكيك ``api/main.py`` إلى وحدات ``APIRouter`` (نمط P0).

سلوك محفوظ بالكامل: مسارات/أذونات/مخرجات/مخطّط OpenAPI مطابقة تماماً لما كان
في ``main.py`` — نُقلت الدالّة حرفيّاً مع تغيير ``@app`` إلى ``@router``.

الاعتماديّات المشتركة (التبعيات/النموذج) تبقى مُعرَّفة في ``api.main`` وتُستورَد من
هنا تفادياً لكسر ``_rebuild_pydantic_models`` واستيرادات الاختبارات. استيراد محرّك
WOFOST يبقى كسولاً داخل الدالّة كما كان. لتفادي الاستيراد الدائريّ: ``api.main``
يستورد هذا الموجِّه في نهايته فقط (بعد تعريف كلّ التبعيات/النماذج)، فيُحلّ الاستيراد.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from api.main import (
    UserSchema,
    WhatIfRequest,
    get_current_user,
)

router = APIRouter()


@router.post("/api/v1/simulate/what-if")
async def simulate_what_if(
    req: WhatIfRequest,
    user: UserSchema = Depends(get_current_user),
):
    """يحاكي أثر سيناريو (مثلاً تقليل/إيقاف الريّ) على المحصول والماء.

    Runtime Cohesion: يغذّي حلقة القرار بأثر متوقّع للإجراء المقترَح. يشغّل
    WOFOST مرّتين (baseline مرويّ مقابل السيناريو) ويقارن. صدق: عند تعذّر
    النموذج/الطقس يُعلَن (لا أرقام مخترَعة). lat/lon إلزاميّان للطقس الحيّ.
    """
    if req.lat is None or req.lon is None:
        return {
            "field_id": req.field_id,
            "available": False,
            "note_ar": "lat/lon مطلوبان للطقس الحيّ — لا محاكاة بلا موقع",
        }
    # استيراد آمن لمحرّك WOFOST (وحدة جذريّة — قد لا تكون على المسار)
    try:
        import importlib.util as _ilu
        import os as _os

        _root = _os.path.abspath(_os.path.join(_os.path.dirname(__file__), "..", "..", "..", ".."))
        _eng_path = _os.path.join(_root, "wofost_real", "wofost_engine.py")
        if not _os.path.exists(_eng_path):
            return {
                "field_id": req.field_id,
                "available": False,
                "note_ar": "محرّك WOFOST غير متاح على هذا المسار",
            }
        _spec = _ilu.spec_from_file_location("wofost_engine", _eng_path)
        _eng = _ilu.module_from_spec(_spec)
        _spec.loader.exec_module(_eng)
    except Exception as e:  # noqa: BLE001 — صدق: نُعلن التعذّر
        return {
            "field_id": req.field_id,
            "available": False,
            "error": f"تعذّر تحميل محرّك المحاكاة: {e}",
        }

    from datetime import date as _date

    try:
        pd = _date.fromisoformat(req.planting_date) if req.planting_date else _date.today()
    except ValueError:
        pd = _date.today()

    async def _run(irrigation: bool):
        return await _eng.simulate_wofost(
            req.field_id,
            req.crop,
            req.soil_type,
            req.lat,
            req.lon,
            pd,
            irrigation=irrigation,
        )

    try:
        baseline = await _run(irrigation=True)  # مرويّ كاملاً (الأساس)
        scenario = await _run(irrigation=False)  # السيناريو (بلا/تقليل ريّ)
    except Exception as e:  # noqa: BLE001 — صدق: الطقس/النموذج تعذّر
        return {
            "field_id": req.field_id,
            "available": False,
            "error": f"تعذّرت المحاكاة (طقس/نموذج): {e}",
        }

    # b_yield = محصول الإجراء المقترَح (الريّ الموصى به)؛ s_yield = بلا إجراء (بلا ريّ)
    b_yield = baseline.get("simulation", {}).get("yield_t_ha")
    s_yield = scenario.get("simulation", {}).get("yield_t_ha")
    b_irr = baseline.get("water_balance", {}).get("irrigation_needed_mm")
    s_irr = scenario.get("water_balance", {}).get("irrigation_needed_mm")
    water_saved = round(b_irr - s_irr, 1) if (b_irr is not None and s_irr is not None) else None
    # هل "الإجراء المقترَح" (الريّ) يُجدي؟ مُجدٍ إن رفع المحصول >2% فوق خطّ الأساس
    # (لا إجراء). خطّ الأساس = s_yield، الإجراء = b_yield ⇒ المقارنة ذات معنى.
    helps = None
    if b_yield is not None and s_yield is not None:
        helps = b_yield > s_yield * 1.02  # الريّ الموصى به يرفع المحصول >2%

    return {
        "field_id": req.field_id,
        "available": True,
        "scenario": req.scenario,
        # خطّ الأساس = لا إجراء (بلا ريّ)؛ الإجراء = الريّ الموصى به (قيمتان متمايزتان
        # حتّى تكون recommended_action_helps مقارنةً فعليّةً لا قيمةً بنفسها).
        "baseline_yield_t_ha": s_yield,  # لا إجراء (السيناريو بلا ريّ) — خطّ الأساس
        "action_yield_t_ha": b_yield,  # الإجراء المقترَح (الريّ الموصى به)
        "no_action_yield_t_ha": s_yield,  # مرادف صريح لخطّ الأساس (توافق خلفي)
        "water_saved_mm": water_saved,
        "recommended_action_helps": helps,
    }

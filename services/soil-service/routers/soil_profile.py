"""routers/soil_profile.py — تفسير التربة: قوام USDA + ملاءمة المحصول + SoilGrids.

يسدّ فجوة حقيقيّة: soil-service كان يخزّن قراءات الحسّاسات فقط دون تفسير زراعيّ.
مصدرا الحقيقة:
  • ``POST /v1/soil/suitability`` — نقيّ: من خصائص مُعطاة (قوام/pH/EC) ⇒ صنف القوام +
    ترتيب ملاءمة المحاصيل (لا قاعدة/شبكة — تفسير حتميّ شفّاف).
  • ``GET  /v1/soil/soilgrids`` — يجلب خصائص التربة من SoilGrids لإحداثيّة (fail-soft:
    404 لا تغطية · 503 قيد الجلب/متعذّر، لا اختراع قيمة) ثمّ يُفسّرها كأعلاه.

الأمان: توكن الخدمة (``_require_service_token``) كبقيّة مسارات الخدمة. لا قاعدة ⇒ لا
عزل مستأجِر مطلوب هنا (لا بيانات مستأجِر تُقرأ؛ SoilGrids عامّ، والحساب نقيّ).
"""

from __future__ import annotations

import os

import main
import soil_science
import soilgrids_cache
import soilgrids_client
from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field

router = APIRouter()

# انتظارُ المستدعي أقصرُ من مهلة المنصّة (``ADAPTER_TIMEOUT`` = 20ث) كي يصلها جوابٌ
# صادق («قيد الجلب») بدل أن تقطع هي النداءَ فتقرأه «مفقوداً» بلا سبب.
_ROUTE_WAIT_S = soilgrids_cache.env_seconds(os.getenv("SOILGRIDS_ROUTE_WAIT_SECONDS", "15"), 15.0)
# خصائصُ SoilGrids نموذجٌ ثابت؛ أسبوعٌ افتراضاً، ويُضبَط بالبيئة.
_CACHE_TTL_S = soilgrids_cache.env_seconds(
    os.getenv("SOILGRIDS_CACHE_TTL_SECONDS", "604800"), 604800.0
)
_RETRY_AFTER_S = "30"

# المُجلِب يُحَلّ **وقتَ النداء** (lambda) لا وقتَ الإنشاء، فيبقى قابلاً للاستبدال.
_CACHE = soilgrids_cache.SoilGridsCache(
    lambda lon, lat: soilgrids_client.query_soil_properties(lon, lat),
    ttl_s=_CACHE_TTL_S,
)


class SuitabilityRequest(BaseModel):
    """خصائص تربة لتقييم القوام + ملاءمة المحصول (كلّها اختياريّة — تُقيَّم المتوفّرة)."""

    clay: float | None = Field(None, ge=0, le=100)
    sand: float | None = Field(None, ge=0, le=100)
    silt: float | None = Field(None, ge=0, le=100)
    ph: float | None = Field(None, ge=0, le=14)
    ec: float | None = Field(None, ge=0, le=50)


def _interpret(clay, sand, silt, ph, ec) -> dict:
    """يبني تفسير التربة (قوام إن توفّرت النِسَب + ترتيب ملاءمة المحاصيل)."""
    texture = None
    texture_key = None
    if clay is not None and sand is not None and silt is not None:
        texture = soil_science.usda_texture_class(clay, sand, silt)
        texture_key = texture["key"]
    crops = soil_science.rank_crops(ph=ph, ec=ec, texture_key=texture_key)
    return {"texture": texture, "crops": crops}


@router.post("/v1/soil/suitability")
async def soil_suitability(req: SuitabilityRequest, x_agent_token: str = Header(None)):
    """قوام USDA + ترتيب ملاءمة المحاصيل من خصائص مُعطاة (حساب نقيّ حتميّ)."""
    main._require_service_token(x_agent_token)
    try:
        result = _interpret(req.clay, req.sand, req.silt, req.ph, req.ec)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    return {"source": "input", **result}


@router.get("/v1/soil/soilgrids")
async def soil_from_soilgrids(
    lon: float = Query(..., ge=-180, le=180),
    lat: float = Query(..., ge=-90, le=90),
    x_agent_token: str = Header(None),
):
    """خصائص تربة SoilGrids لإحداثيّة + تفسيرها (قوام + ملاءمة). fail-soft صادق.

    أربعةُ أجوبةٍ لا يُخلَط بينها (كانت الثلاثةُ الأخيرةُ جواباً واحداً «وصول/تغطية»):
      • 200 — بيانات.
      • 404 ``soilgrids_no_coverage`` — ISRIC أجاب ولا قيمَ هنا (أرضٌ مُقنَّعة). دائم.
      • 503 ``soilgrids_pending`` + ``Retry-After`` — الجلبُ جارٍ في الخلفيّة.
      • 503 ``soilgrids_unavailable`` + ``reason`` — مهلة/تعذّر/ردّ شاذّ. عابر.
    """
    main._require_service_token(x_agent_token)
    # الجلبُ متزامنٌ ويجري في خيطٍ خلفيّ عبر الذاكرة المؤقّتة — لا يحجز حلقةَ الأحداث
    # (رصدَه مراجعُ #1093) ولا يُبقي المستدعي أطولَ من ``_ROUTE_WAIT_S``.
    result = await _CACHE.lookup(lon, lat, wait_s=_ROUTE_WAIT_S)
    outcome = result.get("outcome")
    if outcome == soilgrids_client.NO_COVERAGE:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "soilgrids_no_coverage",
                "note_ar": "SoilGrids لا يغطّي هذه الإحداثيّة (أرضٌ مُقنَّعة: حضريّة/صخريّة/مائيّة)"
                " — لا قيمةَ تُختلَق",
            },
        )
    if outcome == soilgrids_cache.PENDING:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "soilgrids_pending",
                "note_ar": "الجلبُ من SoilGrids جارٍ في الخلفيّة — أعِد المحاولة بعد قليل",
            },
            headers={"Retry-After": _RETRY_AFTER_S},
        )
    if outcome != soilgrids_client.OK:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "soilgrids_unavailable",
                "reason": result.get("reason", "unreachable"),
                "note_ar": "تعذّر جلب بيانات SoilGrids الآن (مهلة/وصول/ردّ شاذّ) — عابر",
            },
        )
    data = result["data"]
    p = data["properties"]
    result = _interpret(p.get("clay_pct"), p.get("sand_pct"), p.get("silt_pct"), p.get("ph"), None)
    return {"source": "soilgrids", "lon": lon, "lat": lat, "properties": p, **result}

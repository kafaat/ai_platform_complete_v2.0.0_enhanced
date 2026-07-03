"""routers/soil_profile.py — تفسير التربة: قوام USDA + ملاءمة المحصول + SoilGrids.

يسدّ فجوة حقيقيّة: soil-service كان يخزّن قراءات الحسّاسات فقط دون تفسير زراعيّ.
مصدرا الحقيقة:
  • ``POST /soil/suitability`` — نقيّ: من خصائص مُعطاة (قوام/pH/EC) ⇒ صنف القوام +
    ترتيب ملاءمة المحاصيل (لا قاعدة/شبكة — تفسير حتميّ شفّاف).
  • ``GET  /soil/soilgrids`` — يجلب خصائص التربة من SoilGrids لإحداثيّة (fail-soft:
    503 صادق عند تعذّر الوصول، لا اختراع قيمة) ثمّ يُفسّرها كأعلاه.

الأمان: توكن الخدمة (``_require_service_token``) كبقيّة مسارات الخدمة. لا قاعدة ⇒ لا
عزل مستأجِر مطلوب هنا (لا بيانات مستأجِر تُقرأ؛ SoilGrids عامّ، والحساب نقيّ).
"""

from __future__ import annotations

import main
import soil_science
import soilgrids_client
from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field

router = APIRouter()


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


@router.post("/soil/suitability")
async def soil_suitability(req: SuitabilityRequest, x_agent_token: str = Header(None)):
    """قوام USDA + ترتيب ملاءمة المحاصيل من خصائص مُعطاة (حساب نقيّ حتميّ)."""
    main._require_service_token(x_agent_token)
    try:
        result = _interpret(req.clay, req.sand, req.silt, req.ph, req.ec)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    return {"source": "input", **result}


@router.get("/soil/soilgrids")
async def soil_from_soilgrids(
    lon: float = Query(..., ge=-180, le=180),
    lat: float = Query(..., ge=-90, le=90),
    x_agent_token: str = Header(None),
):
    """خصائص تربة SoilGrids لإحداثيّة + تفسيرها (قوام + ملاءمة). fail-soft صادق."""
    main._require_service_token(x_agent_token)
    data = soilgrids_client.fetch_soil_properties(lon, lat)
    if data is None:
        # صدق: لم نحصل على بيانات (تعذّر وصول/تغطية) — لا نخترع قيمة.
        raise HTTPException(
            status_code=503,
            detail={
                "error": "soilgrids_unavailable",
                "note_ar": "تعذّر جلب بيانات SoilGrids لهذه الإحداثيّة (وصول/تغطية)",
            },
        )
    p = data["properties"]
    result = _interpret(p.get("clay_pct"), p.get("sand_pct"), p.get("silt_pct"), p.get("ph"), None)
    return {"source": "soilgrids", "lon": lon, "lat": lat, "properties": p, **result}

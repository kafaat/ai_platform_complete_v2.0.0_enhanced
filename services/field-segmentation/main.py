"""
SAHOOL — services/field-segmentation/main.py
خدمة تقطيع الحقل (Field Auto-Segmentation).

سياسة الصدق (حرجة):
  • المسار اليدويّ (manual) حقيقيّ بالكامل: نتحقّق/نطبّع مضلّع المستخدم محليّاً
    (مدقّق هندسيّ خفيف، بلا تبعيّات ثقيلة) ونعيده مصدره "manual".
  • المساران auto/hybrid يتطلّبان نموذجاً حقيقيّاً (SAM2/GeoSAM) + أوزاناً + GPU.
    لا نُلفّق أقنعة تقطيع ولا نخترع نتائج. حين لا يُهيّأ نموذج (SEGMENTATION_MODEL_PATH/
    SEGMENTATION_BACKEND غير مضبوط أو غير متاح) نُرجِع 503 صادقاً مع خطّاف بيئة موثّق.

المصادقة: خدمة-لخدمة عبر X-Agent-Token (مثل بقيّة الخدمات الداخليّة). تحقن البوّابة
(service_proxy) التوكن خادميّاً بعد التحقّق من JWT المستخدم.
"""

from __future__ import annotations

import logging
import os

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

logging.basicConfig(
    level=logging.INFO,
    format='{"time":"%(asctime)s","svc":"field-segmentation","level":"%(levelname)s","msg":"%(message)s"}',
)
logger = logging.getLogger("field-segmentation")

VERSION = "1.0.0"

# مصادقة خدمة-لخدمة. غياب التوكن ⇒ فشل آمن (الخدمة معطّلة، لا مجهول).
AGENT_TOKEN = os.getenv("SAHOOL_AGENT_TOKEN", "")

# خطّاف النموذج (auto/hybrid). غيابهما ⇒ 503 صادق. لا تلفيق.
SEGMENTATION_MODEL_PATH = os.getenv("SEGMENTATION_MODEL_PATH", "").strip()
SEGMENTATION_BACKEND = os.getenv("SEGMENTATION_BACKEND", "").strip()

app = FastAPI(title="SAHOOL Field Segmentation", version=VERSION)


def _require_service_token(x_agent_token: str | None) -> None:
    """يمنع الاستدعاء المجهول. فشل آمن لو التوكن غير مضبوط."""
    if not AGENT_TOKEN:
        raise HTTPException(503, "SAHOOL_AGENT_TOKEN غير مضبوط — الخدمة معطّلة بأمان")
    if x_agent_token != AGENT_TOKEN:
        raise HTTPException(401, "توكن خدمة غير صالح")


# ─── نماذج الطلب/الاستجابة ──────────────────────────────────────────────
class SegmentRequest(BaseModel):
    """طلب تقطيع حقل.

    mode:
      • manual : يتطلّب user_polygon (تحقّق/تطبيع حقيقيّ محليّاً).
      • auto   : تقطيع آليّ كامل من صورة (يتطلّب نموذجاً — 503 إن لم يُهيّأ).
      • hybrid : تقطيع آليّ مُوجَّه ببادرة المستخدم (يتطلّب نموذجاً — 503 إن لم يُهيّأ).
    """

    mode: str = Field(pattern="^(manual|auto|hybrid)$")
    # bbox: [min_lon, min_lat, max_lon, max_lat] — يُمرَّر للنموذج (auto/hybrid).
    field_bbox: list[float] | None = None
    # مرجع الصورة (مسار/معرّف مشهد) — يقرؤه خطّاف النموذج (auto/hybrid).
    image_ref: str | None = None
    # مضلّع المستخدم (manual / بادرة hybrid): [[lon,lat], ...] أو GeoJSON Polygon.
    user_polygon: list[list[float]] | dict | None = None


# ─── مدقّق هندسيّ خفيف محليّ (لا تبعيّة على shared/geometry-guard) ─────────
# نُبقي الخدمة خفيفة التبعيّات قصداً (fastapi/uvicorn/httpx فقط). المنطق هنا
# يطبّق نفس مبادئ حارس الهندسة مفهوميّاً: حلقة مغلقة، ≥4 رؤوس، إحداثيّات ضمن
# المدى الجغرافيّ المعقول، بلا NaN/Inf.
_MIN_RING_POINTS = 4  # مضلّع صالح (مغلق) = 3 رؤوس + تكرار الأوّل


def _coerce_ring(user_polygon: list[list[float]] | dict) -> list[list[float]]:
    """يستخرج حلقة الإحداثيّات الخارجيّة من إدخال المستخدم (قائمة أو GeoJSON)."""
    if isinstance(user_polygon, dict):
        gtype = str(user_polygon.get("type", "")).lower()
        coords = user_polygon.get("coordinates")
        if gtype != "polygon" or not isinstance(coords, list) or not coords:
            raise HTTPException(422, "GeoJSON غير صالح — يُتوقّع Polygon بإحداثيّات")
        ring = coords[0]  # الحلقة الخارجيّة
    else:
        ring = user_polygon
    if not isinstance(ring, list):
        raise HTTPException(422, "حلقة الإحداثيّات غير صالحة")
    return ring


def normalize_polygon(user_polygon: list[list[float]] | dict | None) -> dict:
    """يتحقّق ويطبّع مضلّع المستخدم → GeoJSON Polygon مغلق صالح.

    تحقّق حقيقيّ (لا تلفيق): نوع كلّ رأس، المدى الجغرافيّ، قيم منتهية، عدد رؤوس
    كافٍ، إغلاق الحلقة. يرفع 422 على المشوّه (fail-closed، لا تطبيع صامت لقمامة).
    """
    if user_polygon is None:
        raise HTTPException(422, "user_polygon مطلوب للمسار اليدويّ")

    ring = _coerce_ring(user_polygon)
    cleaned: list[list[float]] = []
    for pt in ring:
        if not isinstance(pt, (list, tuple)) or len(pt) < 2:
            raise HTTPException(422, "كلّ رأس يجب أن يكون [lon, lat]")
        try:
            lon = float(pt[0])
            lat = float(pt[1])
        except (TypeError, ValueError) as e:
            raise HTTPException(422, "إحداثيّات غير رقميّة") from e
        # رفض NaN/Inf (float('nan') != float('nan')).
        if lon != lon or lat != lat or abs(lon) == float("inf") or abs(lat) == float("inf"):
            raise HTTPException(422, "إحداثيّات غير منتهية (NaN/Inf)")
        if not (-180.0 <= lon <= 180.0) or not (-90.0 <= lat <= 90.0):
            raise HTTPException(422, "إحداثيّات خارج المدى الجغرافيّ المعقول")
        cleaned.append([lon, lat])

    # تطبيع الإغلاق: لو لم تُغلَق الحلقة، أغلِقها بتكرار الرأس الأوّل.
    if len(cleaned) >= 3 and cleaned[0] != cleaned[-1]:
        cleaned.append(list(cleaned[0]))

    if len(cleaned) < _MIN_RING_POINTS:
        raise HTTPException(422, "المضلّع يحتاج 3 رؤوس مميّزة على الأقلّ")

    return {"type": "Polygon", "coordinates": [cleaned]}


# ─── خطّاف تكامل النموذج (auto/hybrid) ──────────────────────────────────
def _model_configured() -> bool:
    """هل هُيّئ نموذج تقطيع حقيقيّ؟ (مسار الأوزان + خلفيّة)."""
    return bool(SEGMENTATION_MODEL_PATH) and bool(SEGMENTATION_BACKEND)


def run_segmentation_model(
    *,
    mode: str,
    field_bbox: list[float] | None,
    image_ref: str | None,
    user_polygon: list[list[float]] | dict | None,
) -> dict:
    """TODO(segmentation-model): نقطة تكامل SAM2 / GeoSAM.

    هنا يُحمَّل النموذج من SEGMENTATION_MODEL_PATH عبر الخلفيّة SEGMENTATION_BACKEND
    (مثلاً "sam2" أو "geosam")، تُجلب الصورة من image_ref ضمن field_bbox، ويُشغَّل
    الاستدلال (GPU). في hybrid يُستخدم user_polygon كبادرة (prompt) للنموذج.

    لا تُلفّق هنا أقنعة ولا تُخترع هندسة. حتى يُوصَل نموذج حقيقيّ، لا يُبلَغ هذا
    الموضع إطلاقاً — المستدعي يُرجِع 503 صادقاً أعلاه عبر _model_configured().
    """
    raise NotImplementedError(
        "نقطة تكامل النموذج (SAM2/GeoSAM) لم تُنفَّذ بعد — لا تلفيق نتائج"
    )


# ─── المسارات ───────────────────────────────────────────────────────────
@app.get("/healthz")
@app.get("/health")
async def healthz():
    return {"status": "alive", "service": "field-segmentation", "version": VERSION}


@app.get("/readyz")
async def readyz():
    # خدمة عديمة الحالة: جاهزة بمجرّد إقلاع العمليّة. (لا قاعدة/كاش يُفحَص.)
    return {"status": "ready", "model_configured": _model_configured()}


@app.post("/segment")
async def segment(req: SegmentRequest, x_agent_token: str = Header(None)):
    """تقطيع حقل.

    • manual : تحقّق/تطبيع مضلّع المستخدم محليّاً (حقيقيّ) → geometry + source=manual.
    • auto/hybrid : يتطلّب نموذجاً حقيقيّاً. غير مُهيّأ ⇒ 503 صادق (لا تلفيق)،
      مع خطّاف البيئة الموثّق SEGMENTATION_MODEL_PATH / SEGMENTATION_BACKEND.
    """
    _require_service_token(x_agent_token)

    if req.mode == "manual":
        geometry = normalize_polygon(req.user_polygon)
        return {"mode": "manual", "geometry": geometry, "source": "manual"}

    # auto / hybrid — يتطلّبان نموذجاً حقيقيّاً.
    if not _model_configured():
        # 503 صادق: لا نُلفّق ولا نخترع. الخطّاف الموثّق أدناه.
        raise HTTPException(
            status_code=503,
            detail={
                "error": "model_not_configured",
                "note_ar": (
                    "نموذج التقطيع (SAM2/GeoSAM) غير مُهيّأ — اضبط SEGMENTATION_MODEL_PATH"
                ),
            },
        )

    # النموذج مُهيّأ (بيئة إنتاج بأوزان+GPU): فوّض لخطّاف التكامل.
    result = run_segmentation_model(
        mode=req.mode,
        field_bbox=req.field_bbox,
        image_ref=req.image_ref,
        user_polygon=req.user_polygon,
    )
    return {"mode": req.mode, "geometry": result, "source": SEGMENTATION_BACKEND}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)

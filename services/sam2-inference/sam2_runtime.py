"""
SAHOOL — services/sam2-inference/main.py
خادم استدلال SAM2 (GPU/CUDA) لتفعيل التقطيع التلقائيّ/الهجين (auto/hybrid).

سياسة الصدق (حرجة — المستودع صدق-أوّلاً):
  • هذا الخادم يُنشر ويُختبر على عتاد GPU لدى المستخدم (RTX 4090 + CUDA). لا يمكن
    لكاتب الكود تشغيل CUDA/SAM2 ولا تنزيل الأوزان هنا. الكود حقيقيّ وصحيح لكنّه
    *غير مُختبَر على عتاد*؛ يجب التحقّق منه على الـRTX 4090.
  • لا نُلفّق أقنعة ولا هندسة إطلاقاً. إن لم يُحمَّل النموذج (أوزان ناقصة أو لا
    CUDA) → 503 صادق. إن تعذّر جلب صورة الإدخال → 503/422 صادق. إن لم نحصل على
    قناع/هندسة صالحة → 5xx صادق. لا مضلّع اصطناعيّ في أيّ مسار خطأ.
  • جودة التقطيع تعتمد على النموذج + جودة الصورة (غيوم/دقّة/توقيت). هذا تكامل
    بدئيّ يجب التحقّق من جودته على صور حقيقيّة وعتاد حقيقيّ.

العقد (يطابق services/field-segmentation/main.py تماماً — بلا تغيير كود المنصّة):
  الإدخال (POST JSON من field-segmentation._post_inference):
    {
      "mode": "auto" | "hybrid",
      "field_bbox": [min_lon, min_lat, max_lon, max_lat] | null,
      "image_ref": "<COG URL / scene ref>" | null,
      "user_polygon": [[lon,lat], ...] | <GeoJSON Polygon> | null
    }
  الترويسة: X-Agent-Token == SAHOOL_AGENT_TOKEN (نفس عقد المصادقة الداخليّ).
  الإخراج (يتحقّق منه field-segmentation.normalize_polygon):
    {"geometry": {"type": "Polygon", "coordinates": [[[lon,lat], ...]]}}
    حلقة مغلقة، ≥4 رؤوس، EPSG:4326.

المكتبات الثقيلة (torch/sam2/rasterio/shapely/numpy) تُستورَد *داخل الدوالّ* أو
خلف try/except عند الإقلاع، كي يُترجَم الملفّ (py_compile) ويعمل مسار 503 الصادق
حتى بلا تثبيت تلك المكتبات (بيئة CI بلا GPU).
"""

from __future__ import annotations

import logging
import os
import time  # noqa: F401 — إعادة تصدير (نمط main.X)

from fastapi import FastAPI, Header, HTTPException  # noqa: F401 — إعادة تصدير (نمط main.X)
from pydantic import BaseModel, Field

logging.basicConfig(
    level=logging.INFO,
    format='{"time":"%(asctime)s","svc":"sam2-inference","level":"%(levelname)s","msg":"%(message)s"}',
)
logger = logging.getLogger("sam2-inference")

VERSION = "1.0.0"

# ─── إعدادات البيئة ──────────────────────────────────────────────────────
# مصادقة خدمة-لخدمة. غياب التوكن ⇒ فشل آمن (الخدمة معطّلة، لا مجهول).
AGENT_TOKEN = os.getenv("SAHOOL_AGENT_TOKEN", "")

# مسار أوزان SAM2 (يُركَّب من volume sam2-models على /models).
SAM2_CHECKPOINT = os.getenv("SAM2_CHECKPOINT", "/models/sam2_hiera_large.pt").strip()
# ملفّ إعداد بنية النموذج (Hydra config name) — يُمرَّر لـbuild_sam2.
# الافتراض يطابق checkpoint large أعلاه. عدّله لو غيّرت حجم النموذج.
SAM2_MODEL_CFG = os.getenv("SAM2_MODEL_CFG", "sam2_hiera_l.yaml").strip()

# مصدر STAC اختياريّ لجلب صورة Sentinel-2 عند غياب image_ref صالح (Element84).
EARTH_SEARCH_URL = os.getenv(
    "EARTH_SEARCH_URL", "https://earth-search.aws.element84.com/v1"
).strip()
SENTINEL_COLLECTION = os.getenv("SENTINEL_COLLECTION", "sentinel-2-l2a").strip()
# نافذة بحث STAC (أيام للخلف) + سقف الغيوم — لجلب أحدث صورة صافية للـbbox.
STAC_LOOKBACK_DAYS = int(os.getenv("STAC_LOOKBACK_DAYS", "120").strip() or "120")
STAC_MAX_CLOUD = float(os.getenv("STAC_MAX_CLOUD", "20").strip() or "20")
HTTP_TIMEOUT = float(os.getenv("HTTP_TIMEOUT", "30").strip() or "30")

# سقف أبعاد القراءة من الصورة (بكسل) — يمنع استهلاك ذاكرة GPU/CPU مفرطاً.
MAX_IMAGE_DIM = int(os.getenv("MAX_IMAGE_DIM", "1024").strip() or "1024")

# تبسيط حدود القناع (بالأمتار): قناع SAM2 حدوده «درج بكسل» كثيف الرؤوس، فبعد التحويل
# لـ4326 تنهار رؤوس غير متجاورة إلى نفس الموضع (~سم) فتُطلِق تحذير «تقاطع ذاتيّ/رأس
# مكرّر» في الواجهة. تبسيط معتدل بمقياس أمتار (افتراضي 3م) يُنظّف الحدّ دون فقد شكل
# الحقل. الأرضيّة = حجم البكسل كي لا نُبسّط دون دقّة الصورة.
SIMPLIFY_TOLERANCE_M = float(os.getenv("SAM2_POLYGON_SIMPLIFY_TOLERANCE_M", "3").strip() or "3")
# مسافة دمج الرؤوس المتتالية شبه المكرّرة (بالأمتار، افتراضي 0.5م) بعد التحويل لـ4326.
DEDUP_TOLERANCE_M = float(os.getenv("SAM2_POLYGON_DEDUP_TOLERANCE_M", "0.5").strip() or "0.5")


# حالة النموذج العالميّة (تُملأ عند الإقلاع). None ⇒ غير محمّل ⇒ 503 صادق.
_PREDICTOR = None  # SAM2ImagePredictor أو None
_MODEL_LOAD_ERROR: str | None = None  # سبب فشل التحميل (للتشخيص الصادق)
# رمز سبب مُصنَّف (للتشخيص الآليّ في /readyz): None عند التحميل، وإلّا أحد:
#   cuda_unavailable · weights_missing · library_missing · load_failed.
_MODEL_LOAD_REASON_CODE: str | None = None


# ─── المصادقة ────────────────────────────────────────────────────────────
def _require_service_token(x_agent_token: str | None) -> None:
    """يمنع الاستدعاء المجهول. فشل آمن لو التوكن غير مضبوط."""
    if not AGENT_TOKEN:
        raise HTTPException(503, "SAHOOL_AGENT_TOKEN غير مضبوط — الخدمة معطّلة بأمان")
    if x_agent_token != AGENT_TOKEN:
        raise HTTPException(401, "توكن خدمة غير صالح")


# ─── نماذج الطلب ─────────────────────────────────────────────────────────
class PredictRequest(BaseModel):
    """طلب استدلال SAM2 — يطابق payload الذي يرسله field-segmentation."""

    mode: str = Field(pattern="^(auto|hybrid)$")
    field_bbox: list[float] | None = None
    image_ref: str | None = None
    user_polygon: list[list[float]] | dict | None = None


# ─── تحميل النموذج عند الإقلاع ─────────────────────────────────────────────
def _load_model() -> None:
    """يحمّل SAM2 على CUDA. الفشل (لا CUDA / أوزان ناقصة / مكتبة غائبة) لا يُسقِط
    العمليّة — يترك _PREDICTOR=None كي يردّ /v1/predict 503 صادقاً.

    ملاحظة عتاد: لا يمكن تشغيل هذا هنا (لا GPU). تحقّق على RTX 4090.
    """
    global _PREDICTOR, _MODEL_LOAD_ERROR, _MODEL_LOAD_REASON_CODE
    try:
        import torch  # ثقيل — داخل الدالّة كي يُترجَم الملفّ بلا torch.

        if not torch.cuda.is_available():
            _MODEL_LOAD_ERROR = "torch.cuda.is_available() == False — لا GPU/CUDA متاح"
            _MODEL_LOAD_REASON_CODE = "cuda_unavailable"
            logger.warning(_MODEL_LOAD_ERROR)
            return

        if not os.path.isfile(SAM2_CHECKPOINT):
            # حالتك الحاليّة: GPU متاح لكن الأوزان غير مركّبة على volume النماذج.
            _MODEL_LOAD_ERROR = f"أوزان SAM2 غير موجودة على {SAM2_CHECKPOINT}"
            _MODEL_LOAD_REASON_CODE = "weights_missing"
            logger.warning(_MODEL_LOAD_ERROR)
            return

        # واجهة SAM2 الرسميّة (facebookresearch/sam2):
        #   from sam2.build_sam import build_sam2
        #   from sam2.sam2_image_predictor import SAM2ImagePredictor
        try:
            from sam2.build_sam import build_sam2
            from sam2.sam2_image_predictor import SAM2ImagePredictor
        except ImportError as e:
            _MODEL_LOAD_ERROR = f"مكتبة SAM2 غير مثبّتة: {e}"
            _MODEL_LOAD_REASON_CODE = "library_missing"
            logger.warning(_MODEL_LOAD_ERROR)
            return

        device = torch.device("cuda")
        sam2_model = build_sam2(SAM2_MODEL_CFG, SAM2_CHECKPOINT, device=device)
        _PREDICTOR = SAM2ImagePredictor(sam2_model)
        _MODEL_LOAD_ERROR = None
        _MODEL_LOAD_REASON_CODE = None
        logger.info("SAM2 محمّل على CUDA (checkpoint=%s, cfg=%s)", SAM2_CHECKPOINT, SAM2_MODEL_CFG)
    except Exception as e:  # noqa: BLE001 — أيّ فشل تحميل ⇒ خدمة معطّلة بصدق (503)
        _PREDICTOR = None
        _MODEL_LOAD_ERROR = f"فشل تحميل SAM2: {type(e).__name__}: {e}"
        _MODEL_LOAD_REASON_CODE = "load_failed"
        logger.warning(_MODEL_LOAD_ERROR)


# ─── أدوات هندسيّة مساعدة ─────────────────────────────────────────────────
def _coerce_user_ring(user_polygon) -> list[list[float]] | None:
    """يستخرج حلقة [lon,lat] من user_polygon (قائمة أو GeoJSON Polygon). None لو غاب."""
    if user_polygon is None:
        return None
    if isinstance(user_polygon, dict):
        coords = user_polygon.get("coordinates")
        if str(user_polygon.get("type", "")).lower() != "polygon" or not coords:
            return None
        ring = coords[0]
    else:
        ring = user_polygon
    if not isinstance(ring, list) or len(ring) < 3:
        return None
    out: list[list[float]] = []
    for pt in ring:
        if not isinstance(pt, (list, tuple)) or len(pt) < 2:
            return None
        try:
            out.append([float(pt[0]), float(pt[1])])
        except (TypeError, ValueError):
            return None
    return out


# ─── جلب صورة Sentinel-2 RGB للـbbox ──────────────────────────────────────
def _resolve_image_url(image_ref: str | None, field_bbox: list[float] | None) -> str:
    """يحدّد رابط COG قابلاً للقراءة عبر /vsicurl/.

    الأولويّة:
      ١. image_ref إن كان رابط http(s)/s3/مسار محلّيّ → استخدمه مباشرة.
      ٢. وإلّا (لا image_ref صالح) استعلم Element84 STAC عن أحدث صورة Sentinel-2
         صافية للـbbox، واستخدم أصل visual (RGB) لها.
      ٣. تعذّر الجلب ⇒ يرفع HTTPException 503/422 صادقاً (لا اختراع صورة).
    """
    # ١. image_ref رابط جاهز.
    if image_ref:
        ref = image_ref.strip()
        if ref.startswith(("http://", "https://", "/vsicurl/", "s3://", "/")):
            return ref
        # مرجع مشهد غير قابل للقراءة مباشرة — نسقط للـSTAC أدناه.

    # ٢. لا رابط صالح — نحتاج bbox للبحث في STAC.
    if not field_bbox or len(field_bbox) != 4:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "no_image_and_no_bbox",
                "note_ar": "لا image_ref قابل للقراءة ولا field_bbox للبحث عن صورة",
            },
        )

    visual_url = _stac_latest_visual(field_bbox)
    if not visual_url:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "no_imagery_for_bbox",
                "note_ar": "تعذّر إيجاد صورة Sentinel-2 صافية للنطاق عبر STAC",
            },
        )
    return visual_url


def _stac_latest_visual(bbox: list[float]) -> str | None:
    """يستعلم Element84 Earth Search عن أحدث صورة Sentinel-2 صافية، يُرجِع رابط
    أصل visual (RGB COG) أو None عند الفشل. لا يخترع — None ⇒ 503 لاحقاً.
    """
    import datetime as _dt

    import httpx

    end = _dt.datetime.now(_dt.UTC)
    start = end - _dt.timedelta(days=STAC_LOOKBACK_DAYS)
    payload = {
        "collections": [SENTINEL_COLLECTION],
        "bbox": bbox,
        "datetime": f"{start.strftime('%Y-%m-%dT%H:%M:%SZ')}/{end.strftime('%Y-%m-%dT%H:%M:%SZ')}",
        "query": {"eo:cloud_cover": {"lte": STAC_MAX_CLOUD}},
        "limit": 1,
        "sortby": [{"field": "properties.datetime", "direction": "desc"}],
    }
    try:
        with httpx.Client(timeout=HTTP_TIMEOUT) as cli:
            resp = cli.post(f"{EARTH_SEARCH_URL}/search", json=payload)
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:  # noqa: BLE001 — فشل STAC ⇒ None ⇒ 503 صادق
        logger.warning("STAC search فشل: %s", e)
        return None

    feats = data.get("features") or []
    if not feats:
        return None
    assets = feats[0].get("assets") or {}
    # أصل visual في sentinel-2-l2a هو RGB COG جاهز (true color).
    visual = assets.get("visual") or {}
    href = visual.get("href")
    return href if isinstance(href, str) and href else None


def _read_rgb(image_url: str, bbox: list[float] | None):
    """يقرأ نافذة RGB من COG عبر rasterio (/vsicurl/ للبعيد) ضمن الـbbox.

    يُرجِع (rgb_uint8 [H,W,3], transform الفعليّ للقراءة, crs). يرفع HTTPException
    503 عند تعذّر القراءة (شبكة/مصدر غير صالح). لا يخترع صورة.
    """
    import numpy as np
    import rasterio
    from rasterio.transform import Affine
    from rasterio.warp import transform_bounds
    from rasterio.windows import from_bounds

    # توحيد البادئة لـGDAL: روابط http(s) تُقرأ عبر /vsicurl/.
    src_path = image_url
    if image_url.startswith(("http://", "https://")):
        src_path = f"/vsicurl/{image_url}"

    try:
        with rasterio.open(src_path) as src:
            # حدّد النافذة من الـbbox (4326) محوّلاً لـCRS الصورة إن أمكن.
            window = None
            if bbox and len(bbox) == 4:
                try:
                    if src.crs and src.crs.to_epsg() != 4326:
                        minx, miny, maxx, maxy = transform_bounds(
                            "EPSG:4326", src.crs, *bbox, densify_pts=21
                        )
                    else:
                        minx, miny, maxx, maxy = bbox
                    window = from_bounds(minx, miny, maxx, maxy, transform=src.transform)
                except Exception as e:  # noqa: BLE001 — نافذة فاشلة ⇒ نقرأ كامل المشهد
                    logger.warning("تعذّر حساب نافذة bbox (%s) — أقرأ كامل المصدر", e)
                    window = None

            # حساب decimation كي لا نتجاوز MAX_IMAGE_DIM (حماية الذاكرة).
            if window is not None:
                win_w = max(int(round(window.width)), 1)
                win_h = max(int(round(window.height)), 1)
            else:
                win_w, win_h = src.width, src.height
            scale = max(win_w, win_h) / float(MAX_IMAGE_DIM)
            out_w = max(int(win_w / scale), 1) if scale > 1 else win_w
            out_h = max(int(win_h / scale), 1) if scale > 1 else win_h

            # نقرأ أوّل ثلاثة نطاقات (visual = RGB). إن كان النطاق واحداً نكرّره.
            band_count = src.count
            bands = [1, 2, 3] if band_count >= 3 else [1, 1, 1]
            arr = src.read(
                bands,
                window=window,
                out_shape=(3, out_h, out_w),
                boundless=window is not None,
                fill_value=0,
            )
            # transform الفعليّ للنافذة المقروءة (لتحويل بكسل→جغرافي لاحقاً).
            if window is not None:
                win_transform = src.window_transform(window)
            else:
                win_transform = src.transform
            # عامل القياس بسبب out_shape (أبعاد الإخراج أصغر من النافذة).
            sx = (win_w / out_w) if out_w else 1.0
            sy = (win_h / out_h) if out_h else 1.0
            read_transform = win_transform * Affine.scale(sx, sy)
            crs = src.crs
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — أيّ فشل قراءة ⇒ 503 صادق
        raise HTTPException(
            status_code=503,
            detail={
                "error": "image_read_failed",
                "note_ar": "تعذّرت قراءة صورة الإدخال (مصدر/شبكة)",
                "detail": f"{type(e).__name__}: {e}",
            },
        ) from e

    # تحويل لـuint8 RGB [H,W,3] (SAM2 يتوقّع HWC uint8).
    rgb = np.transpose(arr, (1, 2, 0))  # [H,W,3]
    if rgb.dtype != np.uint8:
        # Sentinel visual غالباً uint8 أصلاً؛ إن لا، قُصّ خطّيّاً لـ0..255.
        finite = rgb[np.isfinite(rgb)] if np.issubdtype(rgb.dtype, np.floating) else rgb
        if finite.size:
            lo = float(np.percentile(finite, 2))
            hi = float(np.percentile(finite, 98))
        else:
            lo, hi = 0.0, 1.0
        if hi <= lo:
            hi = lo + 1.0
        rgb = np.clip((rgb.astype("float32") - lo) / (hi - lo), 0, 1) * 255.0
        rgb = rgb.astype(np.uint8)

    return np.ascontiguousarray(rgb), read_transform, crs


# ─── تحويل القناع → مضلّع GeoJSON ─────────────────────────────────────────
def _tol_in_crs_units(tol_m: float, crs) -> float:
    """حوّل مسافة بالأمتار إلى وحدات الـCRS للتبسيط قبل التحويل لـ4326.

    UTM (مُسقَط، وحدته المتر) ⇒ كما هي؛ CRS جغرافيّ (درجات) ⇒ تقريب ~111320م/درجة.
    نقيّ (بلا شبكة/GPU) فيُختبَر وحدةً."""
    try:
        if crs is not None and crs.is_geographic:
            return tol_m / 111_320.0
    except Exception:  # noqa: BLE001 — CRS بلا is_geographic ⇒ عامله كمُسقَط (أمتار)
        pass
    return tol_m


def _dedupe_ring(ring: list[list[float]], eps: float = 2e-7) -> list[list[float]]:
    """أزِل الرؤوس المتتالية شبه المكرّرة (ضمن eps) مع إبقاء الحلقة مغلقة.

    eps بالدرجات (~2e-7 ≈ 2سم) أكبر من دقّة toFixed(7) في حارس الواجهة، كي تختفي
    الرؤوس المنهارة التي تُطلِق تحذير «رأس مكرّر». يحفظ الترتيب والإغلاق. نقيّ ⇒ يُختبَر وحدةً."""
    if not ring:
        return ring
    out: list[list[float]] = [list(ring[0])]
    for p in ring[1:]:
        q = out[-1]
        if abs(p[0] - q[0]) > eps or abs(p[1] - q[1]) > eps:
            out.append(list(p))
    # أعِد الإغلاق: آخر رأس = الأوّل بالضبط (قد يكون أُزيل لقربه، أو نُطابقه صراحةً).
    if len(out) >= 2 and (abs(out[0][0] - out[-1][0]) > eps or abs(out[0][1] - out[-1][1]) > eps):
        out.append(list(out[0]))
    else:
        out[-1] = list(out[0])
    return out


def _mask_to_polygon(mask, transform, crs) -> dict:
    """يحوّل قناعاً ثنائيّاً [H,W] → GeoJSON Polygon (EPSG:4326، حلقة مغلقة).

    الخطوات: rasterio.features.shapes لاستخراج المضلّعات → أكبر حلقة → تبسيط خفيف
    → تحويل CRS لـ4326 إن لزم. يرفع HTTPException 5xx إن لم تنتج هندسة صالحة
    (لا اختراع مضلّع).
    """
    import numpy as np
    from rasterio.features import shapes as rio_shapes
    from rasterio.warp import transform_geom
    from shapely.geometry import mapping, shape

    mask_u8 = np.asarray(mask).astype(np.uint8)
    if int(mask_u8.sum()) == 0:
        raise HTTPException(
            status_code=500,
            detail={"error": "empty_mask", "note_ar": "القناع فارغ — لا تقطيع"},
        )

    # استخرج مضلّعات القيم == 1 فقط.
    polys = []
    for geom, val in rio_shapes(mask_u8, mask=(mask_u8 == 1), transform=transform):
        if val != 1:
            continue
        try:
            g = shape(geom)
        except Exception:  # noqa: BLE001
            continue
        if g.is_valid and not g.is_empty and g.area > 0:
            polys.append(g)

    if not polys:
        raise HTTPException(
            status_code=500,
            detail={"error": "no_polygon", "note_ar": "تعذّر تحويل القناع لمضلّع"},
        )

    # أكبر مضلّع (الحقل الرئيسيّ) ثمّ حلقته الخارجيّة.
    largest = max(polys, key=lambda g: g.area)
    # تبسيط معتدل بمقياس أمتار (لا بكسل واحد) لإزالة درج البكسل والرؤوس شبه المكرّرة
    # التي تُطلِق تحذير «تقاطع ذاتيّ/رأس مكرّر» في الواجهة. الأرضيّة = حجم البكسل كي لا
    # نُبسّط دون دقّة الصورة. preserve_topology يمنع التقاطع الذاتيّ من التبسيط نفسه.
    px = max(abs(transform.a), abs(transform.e))
    tol = max(px, _tol_in_crs_units(SIMPLIFY_TOLERANCE_M, crs))
    simplified = largest.simplify(tol, preserve_topology=True)
    if simplified.is_empty:
        simplified = largest
    # صلابة: إن أنتج التبسيط هندسة غير صالحة (نادر مع preserve_topology) صحّحها
    # عبر make_valid ثمّ buffer(0) كبديل — لا نُعيد هندسة غير صالحة أبداً.
    if not simplified.is_valid:
        try:
            from shapely.validation import make_valid

            simplified = make_valid(simplified)
        except Exception:  # noqa: BLE001 — بديل: buffer(0) يُصلح التقاطعات الذاتيّة
            simplified = simplified.buffer(0)
        # make_valid قد يُرجِع GeometryCollection — خذ أكبر مضلّع منها.
        if getattr(simplified, "geom_type", "") == "GeometryCollection":
            polys2 = [g for g in simplified.geoms if g.geom_type in ("Polygon", "MultiPolygon")]
            if not polys2:
                raise HTTPException(
                    status_code=500,
                    detail={"error": "no_polygon", "note_ar": "تعذّر تصحيح الهندسة بعد التبسيط"},
                )
            simplified = max(polys2, key=lambda g: g.area)

    geom_obj = mapping(simplified)

    # حوّل لـ4326 إن كانت الصورة بإسقاط آخر (UTM غالباً).
    try:
        if crs is not None and crs.to_epsg() != 4326:
            geom_obj = transform_geom(crs, "EPSG:4326", geom_obj)
    except Exception as e:  # noqa: BLE001 — فشل التحويل ⇒ هندسة غير موثوقة ⇒ 500
        raise HTTPException(
            status_code=500,
            detail={"error": "crs_transform_failed", "detail": str(e)},
        ) from e

    # استخرج الحلقة الخارجيّة كـ[[lon,lat], ...] مغلقة.
    coords = geom_obj.get("coordinates")
    gtype = str(geom_obj.get("type", "")).lower()
    if gtype == "multipolygon":
        # خذ أكبر مضلّع من الـMultiPolygon (الأطول حلقة خارجيّة).
        if not coords:
            raise HTTPException(500, detail={"error": "no_polygon"})
        ring = max((p[0] for p in coords if p), key=len)
    elif gtype == "polygon":
        if not coords or not coords[0]:
            raise HTTPException(500, detail={"error": "no_polygon"})
        ring = coords[0]
    else:
        raise HTTPException(500, detail={"error": "no_polygon"})

    cleaned = [[float(p[0]), float(p[1])] for p in ring]
    # إزالة الرؤوس المتتالية شبه المكرّرة (بعد التحويل لـ4326) — يُنظّف انهيار درج
    # البكسل عند دقّة toFixed(7) في حارس الواجهة، ويُبقي الحلقة مغلقة. المسافة بالأمتار
    # (SAM2_POLYGON_DEDUP_TOLERANCE_M) مُحوَّلة لدرجات (~111320م/درجة، تقريب استوائيّ كافٍ).
    cleaned = _dedupe_ring(cleaned, eps=DEDUP_TOLERANCE_M / 111_320.0)
    # تأكيد الإغلاق.
    if len(cleaned) >= 3 and cleaned[0] != cleaned[-1]:
        cleaned.append(list(cleaned[0]))
    if len(cleaned) < 4:
        raise HTTPException(
            status_code=500,
            detail={"error": "degenerate_polygon", "note_ar": "حلقة ناقصة الرؤوس"},
        )

    return {"type": "Polygon", "coordinates": [cleaned]}


# ─── حساب بادرة SAM2 (نقطة/مربّع) بإحداثيّات بكسل ───────────────────────────
def _lonlat_to_pixel(lon: float, lat: float, transform, crs):
    """يحوّل (lon,lat) 4326 → (col,row) بكسل في إطار transform/crs للصورة."""
    from rasterio.transform import rowcol
    from rasterio.warp import transform as warp_transform

    x, y = lon, lat
    try:
        if crs is not None and crs.to_epsg() != 4326:
            xs, ys = warp_transform("EPSG:4326", crs, [lon], [lat])
            x, y = xs[0], ys[0]
    except Exception:  # noqa: BLE001 — افترض الإحداثيّات بإطار الصورة
        pass
    row, col = rowcol(transform, x, y)
    return int(col), int(row)


def _build_prompt(mode: str, user_polygon, transform, crs, img_h: int, img_w: int):
    """يبني بادرة SAM2:
      • hybrid: نقطة موجبة عند مركز user_polygon (+ مربّع حدوده إن توفّر).
      • auto  : نقطة عند مركز الصورة (يمكن لاحقاً توسيعها لشبكة نقاط).
    يُرجِع (point_coords [N,2] np, point_labels [N] np, box [4] np|None).
    """
    import numpy as np

    if mode == "hybrid":
        ring = _coerce_user_ring(user_polygon)
        if ring and len(ring) >= 3:
            lons = [p[0] for p in ring]
            lats = [p[1] for p in ring]
            cx = sum(lons) / len(lons)
            cy = sum(lats) / len(lats)
            col, row = _lonlat_to_pixel(cx, cy, transform, crs)
            col = max(0, min(img_w - 1, col))
            row = max(0, min(img_h - 1, row))
            # مربّع حدود user_polygon (يقيّد القناع للحقل المقصود).
            cols = []
            rows = []
            for lon, lat in ring:
                c, r = _lonlat_to_pixel(lon, lat, transform, crs)
                cols.append(c)
                rows.append(r)
            x0 = max(0, min(cols))
            y0 = max(0, min(rows))
            x1 = min(img_w - 1, max(cols))
            y1 = min(img_h - 1, max(rows))
            box = None
            if x1 > x0 and y1 > y0:
                box = np.array([x0, y0, x1, y1], dtype=np.float32)
            return (
                np.array([[col, row]], dtype=np.float32),
                np.array([1], dtype=np.int32),
                box,
            )
        # لا user_polygon صالح في hybrid → نسقط لسلوك auto (مركز الصورة).

    # auto: نقطة موجبة عند مركز الصورة.
    cx_px = img_w // 2
    cy_px = img_h // 2
    return (
        np.array([[cx_px, cy_px]], dtype=np.float32),
        np.array([1], dtype=np.int32),
        None,
    )

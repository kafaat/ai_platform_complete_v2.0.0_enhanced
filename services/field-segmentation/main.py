"""
SAHOOL — services/field-segmentation/main.py
خدمة تقطيع الحقل (Field Auto-Segmentation).

سياسة الصدق (حرجة):
  • المسار اليدويّ (manual) حقيقيّ بالكامل: نتحقّق/نطبّع مضلّع المستخدم محليّاً
    (مدقّق هندسيّ خفيف، بلا تبعيّات ثقيلة) ونعيده مصدره "manual".
  • المساران auto/hybrid يتطلّبان نموذجاً حقيقيّاً (SAM2/GeoSAM) + أوزاناً + GPU.
    الأوزان وعتاد GPU يعيشان *خارج* هذه الخدمة، في خادم استدلال منفصل. هذه الخدمة
    عميل HTTP حقيقيّ مُدقَّق لذلك الخادم: تُرسِل الطلب، تتحقّق من الهندسة العائدة عبر
    normalize_polygon، ولا تُلفّق أقنعة أو هندسة إطلاقاً. حين لا يُهيّأ خادم استدلال
    (SEGMENTATION_BACKEND/SEGMENTATION_INFERENCE_URL غير مضبوطين) نُرجِع 503 صادقاً.
    حين يتعذّر الوصول للخادم أو يُرجِع هندسة ناقصة/فاسدة نُرجِع 5xx صادقاً (بلا اختراع
    مضلّع). أنظر run_segmentation_model أدناه.

المصادقة: خدمة-لخدمة عبر X-Agent-Token (مثل بقيّة الخدمات الداخليّة). تحقن البوّابة
(service_proxy) التوكن خادميّاً بعد التحقّق من JWT المستخدم.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import math
import os

import httpx
import numpy as np
from exg_preprocess import apply_exg_for_sam2
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field
from starlette.responses import JSONResponse

# بلا try/except قصداً: غيابُ الوحدة عطلُ توصيلٍ يُرى لا يُبتلَع.
from shared.security.trusted_tenant import service_token_ok

logging.basicConfig(
    level=logging.INFO,
    format='{"time":"%(asctime)s","svc":"field-segmentation","level":"%(levelname)s","msg":"%(message)s"}',
)
logger = logging.getLogger("field-segmentation")

VERSION = "1.0.0"

# مصادقة خدمة-لخدمة. غياب التوكن ⇒ فشل آمن (الخدمة معطّلة، لا مجهول).
AGENT_TOKEN = os.getenv("SAHOOL_AGENT_TOKEN", "")

# خطّاف النموذج (auto/hybrid). غيابهما ⇒ 503 صادق. لا تلفيق.
# SEGMENTATION_MODEL_PATH: اختياريّ/توثيقيّ — خادم الاستدلال البعيد يملك الأوزان.
SEGMENTATION_MODEL_PATH = os.getenv("SEGMENTATION_MODEL_PATH", "").strip()
# اسم الخلفيّة (مثل "sam2"/"geosam") — يُستخدم كـ source في الاستجابة.
SEGMENTATION_BACKEND = os.getenv("SEGMENTATION_BACKEND", "").strip()
# عنوان نقطة predict لخادم الاستدلال الخارجيّ (SAM2/GeoSAM). غيابه ⇒ 503 صادق.
SEGMENTATION_INFERENCE_URL = os.getenv("SEGMENTATION_INFERENCE_URL", "").strip()
# مهلة استدعاء الاستدلال (ثوانٍ) — قابلة للضبط بيئيّاً.
SEGMENTATION_TIMEOUT = float(os.getenv("SEGMENTATION_TIMEOUT", "30").strip() or "30")
# أدنى مساحة مقبولة للمضلّع (م²) — تُحسب بإسقاطٍ محلّيّ متساوي المساحة حول خطّ عرض الحلقة،
# لا بالدرجات (درجة الطول تنكمش بـcos(lat)). الافتراض 10 م² يطابق أرضيّة حفظ المنصّة
# (MIN_FIELD_AREA_HA = 0.001 في services/sahool-platform/api/field_geometry_save_guard.py)
# فلا يرفض التقطيعُ ما يقبله الحفظ، ويرفض شظايا الضجيج العشريّ وشبه المتسامتة.
SEGMENTATION_MIN_AREA_M2 = float(os.getenv("SEGMENTATION_MIN_AREA_M2", "10").strip() or "10")

app = FastAPI(title="SAHOOL Field Segmentation", version=VERSION)


def _payload_trace_hash(payload: dict) -> str:
    """Stable trace hash without serializing full base64 imagery into logs/CPU.

    The inference payload can contain a large PNG/JPEG base64 string. Hash only a
    digest + length for that field so request correlation stays deterministic
    without making the pre-SAM2 path expensive.
    """
    compact = dict(payload)
    image = compact.get("image_base64")
    if isinstance(image, str):
        compact["image_base64"] = {
            "sha256": hashlib.sha256(image.encode("utf-8")).hexdigest()[:16],
            "length": len(image),
        }
    return hashlib.sha256(
        json.dumps(compact, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()[:16]


def _require_service_token(x_agent_token: str | None) -> None:
    """يمنع الاستدعاء المجهول. فشل آمن لو التوكن غير مضبوط."""
    if not AGENT_TOKEN:
        raise HTTPException(503, "SAHOOL_AGENT_TOKEN غير مضبوط — الخدمة معطّلة بأمان")
    if not service_token_ok(x_agent_token, AGENT_TOKEN):
        raise HTTPException(401, "توكن خدمة غير صالح")


# ─── نماذج الطلب/الاستجابة ──────────────────────────────────────────────
class SegmentRequest(BaseModel):
    """طلب تقطيع حقل.

    mode:
      • manual : يتطلّب user_polygon (تحقّق/تطبيع حقيقيّ محليّاً).
      • auto   : تقطيع آليّ كامل من صورة (يتطلّب نموذجاً — 503 إن لم يُهيّأ).
      • hybrid : تقطيع آليّ مُوجَّه ببادرة المستخدم (يتطلّب نموذجاً — 503 إن لم يُهيّأ).

    ملاحظة التوافق: الواجهة الأماميّة ترسل ``bbox`` و``hints``؛ العقد الداخليّ
    مع خادم الاستدلال يستخدم ``field_bbox`` و``user_polygon``. كلا الاسمَين مقبولان.
    """

    mode: str = Field(pattern="^(manual|auto|hybrid)$")
    # [min_lon, min_lat, max_lon, max_lat] — اسمان مقبولان: field_bbox (داخليّ) / bbox (واجهة).
    field_bbox: list[float] | None = None
    bbox: list[float] | None = None
    # مرجع الصورة (مسار/معرّف مشهد) — يقرؤه خطّاف النموذج (auto/hybrid).
    image_ref: str | None = None
    # Optional client imagery for custom backends only. With SAM2 the server reads its
    # own georeferenced image (image_ref / STAC for the bbox) and runs ExG on it; a
    # browser screenshot has no georeference, so it is accepted for compatibility
    # with older web clients but never forwarded (metadata.client_image says so).
    image_base64: str | None = None
    preprocessing: str | None = Field(default=None, pattern="^(none|exg|auto_exg)$")
    fallback_to_original_on_low_exg: bool = True
    # مضلّع المستخدم (manual / بادرة hybrid) — اسمان: user_polygon (داخليّ) / hints (واجهة).
    user_polygon: list[list[float]] | dict | None = None
    hints: list[list[float]] | None = None


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
        if len(coords) != 1:
            raise HTTPException(422, "Polygon holes are not supported by segmentation")
        ring = coords[0]  # الحلقة الخارجيّة
    else:
        ring = user_polygon
    if not isinstance(ring, list):
        raise HTTPException(422, "حلقة الإحداثيّات غير صالحة")
    return ring


_MAX_RING_VERTICES = 2048
# متوسّط نصف قطر الأرض (IUGG) ⇒ أمتار لكلّ درجة على خطّ الطول/الاستواء.
_M_PER_DEG = 6_371_008.8 * math.pi / 180.0
# حجم دفعة الحواف في فحص التقاطع المتّجه (ذاكرة ثابتة ~ دفعة × عدد الحواف).
_EDGE_CHUNK = 128


def _drop_consecutive_duplicates(ring: list[list[float]]) -> list[list[float]]:
    """Drop exact consecutive repeats (a double click), keeping the ring order.

    Only *consecutive* duplicates are normalised; a vertex revisited later in the
    ring (pinch point) is still rejected by _validate_ring_topology.
    """
    out: list[list[float]] = []
    for pt in ring:
        if not out or pt != out[-1]:
            out.append(pt)
    return out


def _ring_area_m2(vertices: list[list[float]]) -> tuple[float, float]:
    """(signed twice-area in degrees², area in m² on a local equal-area projection)."""

    def cross(a, b, c):
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])

    # Translate to the first vertex before calculating area to avoid cancellation
    # for small fields located far from the coordinate origin.
    area2 = sum(
        cross(vertices[0], vertices[i], vertices[i + 1]) for i in range(1, len(vertices) - 1)
    )
    mean_lat = sum(p[1] for p in vertices) / len(vertices)
    # Sinusoidal-style local scaling: x shrinks by cos(lat), y does not ⇒ equal-area.
    area_m2 = abs(area2) / 2.0 * _M_PER_DEG * _M_PER_DEG * math.cos(math.radians(mean_lat))
    return area2, area_m2


def _ring_edges_intersect(ring: list[list[float]]) -> bool:
    """Vectorised exact edge-pair test (same float64 predicates as the scalar loop).

    Non-adjacent edges i<j (j >= i+2, except the first/last pair which share the
    closing vertex) intersect when they cross properly or one endpoint lies on the
    other segment (collinear touch/overlap). NumPy evaluates the very same IEEE-754
    expressions as the former pure-Python O(n²) loop in C (releasing the GIL), after
    an exact bounding-box prefilter, so the verdict is bit-identical but far cheaper.
    """
    pts = np.asarray(ring, dtype=np.float64)
    n = len(pts) - 1
    a_all, b_all = pts[:-1], pts[1:]
    lo, hi = np.minimum(a_all, b_all), np.maximum(a_all, b_all)  # edge bounding boxes
    idx = np.arange(n)

    def cross(p, q, r):
        return (q[:, 0] - p[:, 0]) * (r[:, 1] - p[:, 1]) - (q[:, 1] - p[:, 1]) * (r[:, 0] - p[:, 0])

    def on_segment(p, q, r):
        return (
            (np.minimum(p[:, 0], q[:, 0]) <= r[:, 0])
            & (r[:, 0] <= np.maximum(p[:, 0], q[:, 0]))
            & (np.minimum(p[:, 1], q[:, 1]) <= r[:, 1])
            & (r[:, 1] <= np.maximum(p[:, 1], q[:, 1]))
        )

    for start in range(0, max(0, n - 2), _EDGE_CHUNK):
        rows = idx[start : start + _EDGE_CHUNK]
        cols = idx[start + 2 :]
        # Pairs whose bounding boxes are disjoint can neither cross nor touch, so
        # this prefilter is exact; only overlapping pairs reach the predicates.
        candidate = (
            (cols[None, :] >= rows[:, None] + 2)
            & (lo[rows, None, 0] <= hi[None, cols, 0])
            & (lo[None, cols, 0] <= hi[rows, None, 0])
            & (lo[rows, None, 1] <= hi[None, cols, 1])
            & (lo[None, cols, 1] <= hi[rows, None, 1])
        )
        if start == 0:
            candidate[0, cols == n - 1] = False  # neighbours sharing the closing vertex
        ri, ci = np.nonzero(candidate)
        if not ri.size:
            continue
        i, j = rows[ri], cols[ci]
        a, b, c, d = a_all[i], b_all[i], a_all[j], b_all[j]
        ac, ad, ca, cb = cross(a, b, c), cross(a, b, d), cross(c, d, a), cross(c, d, b)
        hit = (
            ((ac * ad < 0) & (ca * cb < 0))
            | ((ac == 0) & on_segment(a, b, c))
            | ((ad == 0) & on_segment(a, b, d))
            | ((ca == 0) & on_segment(c, d, a))
            | ((cb == 0) & on_segment(c, d, b))
        )
        if bool(hit.any()):
            return True
    return False


def _validate_ring_topology(ring: list[list[float]]) -> None:
    """Reject pinched, sliver/zero-area and intersecting rings without a GIS dependency."""
    vertices = ring[:-1]
    if len(vertices) > _MAX_RING_VERTICES:
        raise HTTPException(422, f"segmentation polygon exceeds {_MAX_RING_VERTICES} vertices")
    if len(set(map(tuple, vertices))) != len(vertices):
        raise HTTPException(422, "polygon contains repeated vertices")

    area2, area_m2 = _ring_area_m2(vertices)
    if area2 == 0:
        raise HTTPException(422, "polygon must have nonzero area")
    if area_m2 < SEGMENTATION_MIN_AREA_M2:
        raise HTTPException(
            422,
            f"polygon area {area_m2:.3g} m² is below the minimum {SEGMENTATION_MIN_AREA_M2:g} m²",
        )

    if _ring_edges_intersect(ring):
        raise HTTPException(422, "polygon edges intersect")


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

    # رؤوس متتالية متطابقة تماماً (نقرة مزدوجة) تُطبَّع بإسقاطها لا برفض الحلقة؛
    # التكرار غير المتتالي (نقطة اختناق) يبقى مرفوضاً في _validate_ring_topology.
    cleaned = _drop_consecutive_duplicates(cleaned)
    # تطبيع الإغلاق: لو لم تُغلَق الحلقة، أغلِقها بتكرار الرأس الأوّل.
    if len(cleaned) >= 3 and cleaned[0] != cleaned[-1]:
        cleaned.append(list(cleaned[0]))

    if len(cleaned) < _MIN_RING_POINTS:
        raise HTTPException(422, "المضلّع يحتاج 3 رؤوس مميّزة على الأقلّ")

    _validate_ring_topology(cleaned)

    return {"type": "Polygon", "coordinates": [cleaned]}


# ─── محوّل الاستدلال البعيد (auto/hybrid) ────────────────────────────────
def _model_configured() -> bool:
    """هل هُيّئ خادم استدلال حقيقيّ؟ (خلفيّة + عنوان نقطة الاستدلال البعيدة).

    SEGMENTATION_MODEL_PATH اختياريّ/توثيقيّ: الخادم البعيد يملك الأوزان+GPU.
    التهيئة الصالحة = اسم خلفيّة + عنوان نقطة استدلال قابل للاستخدام.
    """
    return bool(SEGMENTATION_BACKEND) and bool(SEGMENTATION_INFERENCE_URL)


def _post_inference(payload: dict) -> httpx.Response:
    """مَفصِل (seam) لاستدعاء خادم الاستدلال البعيد عبر HTTP.

    مفصول قصداً في دالّة خاصّة صغيرة كي تتمكّن الاختبارات من ترقيعه
    (monkeypatch main._post_inference) دون لمس الشبكة. يُرجِع httpx.Response خاماً؛
    معالجة الأخطاء والتحقّق الهندسيّ يحدثان في run_segmentation_model.

    يُمرَّر توكن الخدمة عبر X-Agent-Token (نفس عقد المصادقة الداخليّ).
    """
    headers = {"X-Agent-Token": AGENT_TOKEN} if AGENT_TOKEN else {}
    with httpx.Client(timeout=SEGMENTATION_TIMEOUT, trust_env=False) as cli:
        return cli.post(SEGMENTATION_INFERENCE_URL, json=payload, headers=headers)


def run_segmentation_model(
    *,
    mode: str,
    field_bbox: list[float] | None,
    image_ref: str | None,
    user_polygon: list[list[float]] | dict | None,
    image_base64: str | None = None,
    preprocessing: str | None = None,
    fallback_to_original_on_low_exg: bool = True,
) -> tuple[dict, float | None, dict]:
    """محوّل استدلال بعيد لـSAM2 / GeoSAM (عميل HTTP حقيقيّ، بلا تلفيق).

    يُرجِع (الهندسة المُتحقَّقة، درجة الثقة|None). الثقة درجة النموذج (IoU متوقَّع) إن
    أخرجها الخادم؛ None إن غابت — لا نخترع درجة.

    TODO(segmentation-model): المحوّل البعيد مُنفَّذ. لتفعيل auto/hybrid إنتاجيّاً:
    انشر خادم استدلال SAM2/GeoSAM (أوزان+GPU خارج هذه الخدمة) واضبط
    SEGMENTATION_INFERENCE_URL (+ SEGMENTATION_BACKEND). لا تغيير كود لاحقاً.

    التدفّق: نُرسِل {mode, field_bbox, image_ref, user_polygon} (+ مع SAM2: preprocessing
    وfallback_to_original_on_low_exg — ExG يجري خادميّاً على صورته المُرجَعة جغرافيّاً، ولا
    تُمرَّر image_base64 إليه أبداً) إلى خادم الاستدلال،
    ننتظر استجابة تحوي GeoJSON Polygon (إمّا {"geometry": <Polygon>} أو Polygon خام)،
    *ونتحقّق منها عبر normalize_polygon الموجود* — فالاستجابة الفاسدة تُرفَع 502 بدل
    تمرير هندسة مُلفَّقة. لا نخترع مضلّعاً ولا قناعاً في أيّ مسار خطأ.

    خريطة الأخطاء الصادقة:
      • تعذّر اتصال/مهلة → 503 inference_unreachable.
      • استجابة غير 2xx → 502 inference_failed (+ status).
      • 2xx بهندسة ناقصة/فاسدة → 502 inference_bad_geometry.
    """
    payload = {
        "mode": mode,
        "field_bbox": field_bbox,
        "image_ref": image_ref,
        "user_polygon": user_polygon,
    }

    preprocessing_meta: dict = {
        "preprocessing": "none",
        "vegetation_ratio": None,
        "low_confidence": False,
        "candidate_count": 0,
    }
    server_preprocessing = SEGMENTATION_BACKEND.lower() == "sam2"
    client_image_note: str | None = None
    if server_preprocessing and image_base64:
        # A browser screenshot has no georeference: SAM2 never sees it. SAM2 reads its
        # own image for image_ref/field_bbox and runs ExG on that very raster window.
        # Dropped (not 422) so web clients that still attach it keep working.
        image_base64 = None
        client_image_note = "ignored_not_georeferenced"
    if server_preprocessing:
        payload["preprocessing"] = preprocessing or "none"
        payload["fallback_to_original_on_low_exg"] = fallback_to_original_on_low_exg
    elif image_base64:
        payload["image_base64"] = image_base64

    # Custom backends: improve true-color satellite/map imagery locally with ExG.
    # This does not fabricate geometry; it only changes the image/prompts sent to the
    # real inference service, and the returned geometry is still validated below.
    if (
        not server_preprocessing
        and mode in {"auto", "hybrid"}
        and preprocessing in {"exg", "auto_exg"}
        and image_base64
    ):
        try:
            exg = apply_exg_for_sam2(image_base64)
        except Exception as e:  # noqa: BLE001
            raise HTTPException(
                status_code=422,
                detail={
                    "error": "exg_preprocessing_failed",
                    "note_ar": "تعذّرت معالجة الصورة بمؤشر ExG",
                },
            ) from e

        preprocessing_meta = exg.metadata()
        use_original = bool(exg.low_confidence and fallback_to_original_on_low_exg)
        if use_original:
            preprocessing_meta["preprocessing"] = "exg_low_confidence_fallback_original"
        else:
            payload["image_base64"] = exg.image_base64

        # SAM2 responds better when it receives positive point/box prompts.
        # Use the top vegetation components only; no final polygon is inferred here.
        prompt_candidates = exg.candidates[:3]
        if prompt_candidates and not use_original:
            payload["boxes"] = [list(c.bbox) for c in prompt_candidates]
            payload["positive_points"] = [list(c.centroid) for c in prompt_candidates]
            payload["multimask_output"] = True

    elif (
        not server_preprocessing
        and mode in {"auto", "hybrid"}
        and preprocessing in {"exg", "auto_exg"}
        and not image_base64
    ):
        preprocessing_meta = {
            "preprocessing": "exg_skipped_no_image",
            "vegetation_ratio": None,
            "low_confidence": True,
            "candidate_count": 0,
        }

    if not server_preprocessing:
        payload["preprocessing"] = preprocessing_meta.get("preprocessing", "none")
    # Trace key only: no security semantics, useful for cache/log correlation.
    try:
        payload["request_hash"] = _payload_trace_hash(payload)
    except Exception:  # noqa: BLE001
        pass

    try:
        resp = _post_inference(payload)
    except (httpx.ConnectError, httpx.TimeoutException, httpx.TransportError) as e:
        # تعذّر الوصول لخادم الاستدلال — صادق، بلا اختراع نتيجة.
        raise HTTPException(
            status_code=503,
            detail={
                "error": "inference_unreachable",
                "note_ar": "تعذّر الوصول لخادم استدلال التقطيع (SAM2/GeoSAM)",
            },
        ) from e

    if resp.status_code < 200 or resp.status_code >= 300:
        # الخادم ردّ بفشل — لا نُلفّق هندسة بديلة.
        raise HTTPException(
            status_code=502,
            detail={"error": "inference_failed", "status": resp.status_code},
        )

    # استخراج دفاعيّ للهندسة: {"geometry": <Polygon>} أو Polygon خام.
    try:
        body = resp.json()
    except (ValueError, TypeError) as e:
        raise HTTPException(
            status_code=502,
            detail={"error": "inference_bad_geometry"},
        ) from e

    if isinstance(body, dict) and isinstance(body.get("geometry"), dict):
        candidate = body["geometry"]
    elif isinstance(body, dict) and str(body.get("type", "")).lower() == "polygon":
        candidate = body
    else:
        candidate = None

    if candidate is None:
        # 2xx لكن بلا هندسة قابلة للاستخراج — صادق، بلا تلفيق.
        raise HTTPException(
            status_code=502,
            detail={"error": "inference_bad_geometry"},
        )

    # درجة الثقة إن أخرجها الخادم (float ~[0,1]) — بلا اختراع درجة عند غيابها.
    confidence: float | None = None
    if isinstance(body, dict) and isinstance(body.get("confidence"), (int, float)):
        confidence = float(body["confidence"])

    metadata: dict = {
        "source": SEGMENTATION_BACKEND,
        "mode": mode,
        "confidence": confidence,
        **preprocessing_meta,
    }
    if client_image_note:
        metadata["client_image"] = client_image_note
    if isinstance(body, dict):
        upstream_meta = body.get("metadata")
        if isinstance(upstream_meta, dict):
            for key in (
                "imagery_source",
                "imagery_date",
                "cloud_cover",
                "model",
                "model_version",
                "checkpoint",
                "artifact_digest",
                "model_cfg",
                "post_processing",
                "vertices_before",
                "vertices_after",
                "inference_ms",
                "mask_area_px",
            ):
                if key in upstream_meta:
                    metadata[key] = upstream_meta[key]
            if server_preprocessing:
                for key in (
                    "preprocessing",
                    "vegetation_ratio",
                    "low_confidence",
                    "candidate_count",
                ):
                    if key in upstream_meta:
                        metadata[key] = upstream_meta[key]
        if server_preprocessing and preprocessing in {"exg", "auto_exg"}:
            if metadata.get("preprocessing") not in {"exg", "exg_low_confidence_fallback_original"}:
                raise HTTPException(502, detail={"error": "inference_preprocessing_unconfirmed"})

    # التحقّق الهندسيّ الحقيقيّ يُعاد استخدامه: هندسة الخادم الفاسدة تُرفَع هنا.
    try:
        return normalize_polygon(candidate), confidence, metadata
    except HTTPException as e:
        # normalize_polygon يرفع 422 على القمامة — نحوّله 502 (خطأ الخادم، لا المستخدم).
        raise HTTPException(
            status_code=502,
            detail={"error": "inference_bad_geometry"},
        ) from e


# ─── المسارات ───────────────────────────────────────────────────────────
@app.get("/healthz")
async def healthz():
    return {"status": "alive", "service": "field-segmentation", "version": VERSION}


@app.get("/health", include_in_schema=False)
async def legacy_health():
    return await healthz()


@app.get("/readyz")
async def readyz():
    configured = _model_configured()
    model_ready = False
    reason = "model_not_configured"
    if configured:
        try:
            url = httpx.URL(SEGMENTATION_INFERENCE_URL).copy_with(
                path="/readyz", query=None, fragment=None
            )
            async with httpx.AsyncClient(timeout=3.0, trust_env=False) as client:
                response = await client.get(url)
            state = response.json()
            model_ready = (
                response.status_code == 200
                and isinstance(state, dict)
                and (state.get("status") == "ready" or state.get("ready") is True)
                and state.get("ready") is not False
                and state.get("model_loaded") is not False
                and (SEGMENTATION_BACKEND.lower() != "sam2" or state.get("model_loaded") is True)
            )
            reason = "ready" if model_ready else "inference_not_ready"
        except (httpx.HTTPError, ValueError, TypeError):
            reason = "inference_unavailable"
    # Manual segmentation remains usable without any model. A configured but
    # unavailable backend must fail the full readiness probe; /healthz stays live.
    ready = not configured or model_ready
    model_state = {"ready": model_ready, "reason": reason}
    return JSONResponse(
        {
            "status": "ready" if ready else "degraded",
            "ready": ready,
            "service": "field-segmentation",
            "implemented_runtime": True,
            "model_configured": configured,
            "model_ready": model_ready,
            "capabilities": {
                "manual": {"ready": True},
                "auto": model_state,
                "hybrid": model_state,
            },
        },
        status_code=200 if ready else 503,
    )


@app.post("/v1/segment")
async def segment(req: SegmentRequest, x_agent_token: str = Header(None)):
    """تقطيع حقل.

    • manual : تحقّق/تطبيع مضلّع المستخدم محليّاً (حقيقيّ) → geometry + source=manual.
    • auto/hybrid : يتطلّب نموذجاً حقيقيّاً. غير مُهيّأ ⇒ 503 صادق (لا تلفيق)،
      مع خطّاف البيئة الموثّق SEGMENTATION_MODEL_PATH / SEGMENTATION_BACKEND.
    """
    _require_service_token(x_agent_token)

    # حلّ التوافق: قبول bbox (واجهة أماميّة) وfield_bbox (داخليّ) بالتوازي.
    resolved_bbox = req.field_bbox or req.bbox
    resolved_polygon = req.user_polygon or req.hints

    if req.mode == "manual":
        geometry = await asyncio.to_thread(normalize_polygon, resolved_polygon)
        # يدويّ = رسم المستخدم، لا درجة نموذج ⇒ confidence=None (صدق، لا اختراع درجة).
        return {
            "mode": "manual",
            "geometry": geometry,
            "source": "manual",
            "confidence": None,
            "metadata": {"source": "manual", "mode": "manual", "confidence": None},
        }

    # auto / hybrid — يتطلّبان نموذجاً حقيقيّاً.
    if not _model_configured():
        # 503 صادق: لا نُلفّق ولا نخترع. الخطّاف الموثّق أدناه.
        raise HTTPException(
            status_code=503,
            detail={
                "error": "model_not_configured",
                "note_ar": (
                    "خادم استدلال التقطيع (SAM2/GeoSAM) غير مُهيّأ — اضبط "
                    "SEGMENTATION_BACKEND وSEGMENTATION_INFERENCE_URL"
                ),
            },
        )

    # النموذج مُهيّأ (بيئة إنتاج بأوزان+GPU): فوّض لخطّاف التكامل.
    geometry, confidence, metadata = await asyncio.to_thread(
        run_segmentation_model,
        mode=req.mode,
        field_bbox=resolved_bbox,
        image_ref=req.image_ref,
        user_polygon=resolved_polygon,
        image_base64=req.image_base64,
        preprocessing=req.preprocessing,
        fallback_to_original_on_low_exg=req.fallback_to_original_on_low_exg,
    )
    return {
        "mode": req.mode,
        "geometry": geometry,
        "source": SEGMENTATION_BACKEND,
        "confidence": confidence,
        "metadata": metadata,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)

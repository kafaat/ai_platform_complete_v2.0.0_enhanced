"""cdse_client.py — تكامل Copernicus Data Space Ecosystem (CDSE) عبر Sentinel Hub Process API.

CDSE هو **المزوّد الافتراضيّ** للصور (أقوى من Element84): يُصادَق بـOAuth ويحسب المؤشّر
**خادميّاً** عبر ``evalscript`` على نطاقات Sentinel-2 L2A الكاملة (10م، فسيفساء أقلّ غيوماً)،
فيُرجِع GeoTIFF نطاق-واحد جاهزاً للمؤشّر — لا تنزيل نطاقات منفصلة ولا حساب عميل.

**التدرّج (fallback):** المنسّق (``api/imagery_automation.py``) يجرّب CDSE أوّلاً ثمّ يسقط تلقائيّاً
إلى Element84 Earth Search عند تعذّر CDSE (غير مُهيّأ / انقطاع / فشل). فلا توقّف ولا تلفيق.

صدق وأمان:
  - بلا ``CDSE_CLIENT_ID``/``CDSE_CLIENT_SECRET`` (أو ``CDSE_ENABLED=false``) ⇒ ``is_configured()=False``
    ⇒ يسقط المنسّق إلى Element84 (السلوك القائم تماماً — لا كسر).
  - الأسرار تُقرأ من **البيئة فقط** (``CDSE_CLIENT_SECRET``) ولا تُكتب في أيّ ملفّ متتبَّع.
  - دوالّ بناء evalscript/الأبعاد/الفحص **نقيّة** (قابلة للاختبار بلا شبكة).

المرجع: Sentinel Hub Process API على CDSE — https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/Process.html
"""

from __future__ import annotations

import logging
import math
import os
import threading
import time

logger = logging.getLogger("sahool.cdse")


def _clamp_cloud_pct(value: float | int | str | None) -> float:
    """Return a provider-safe cloud percentage in [0, 100]."""
    try:
        cloud = float(value) if value is not None else 40.0
    except (TypeError, ValueError):
        cloud = 40.0
    return max(0.0, min(cloud, 100.0))


def _to_rfc3339(value: str) -> str:
    """Normalize date/date-time text for Sentinel Hub STAC Catalog.

    The service accepts RFC3339 datetimes. UI/API calls often pass bare dates;
    make them explicit UTC datetimes to avoid provider-side 400s caused by
    ambiguous date intervals.
    """
    text = str(value or "").strip()
    if not text:
        raise ValueError("datetime value is required")
    if len(text) == 10 and text[4] == "-" and text[7] == "-":
        return f"{text}T00:00:00Z"
    if text.endswith("+00:00"):
        return text[:-6] + "Z"
    return text if text.endswith("Z") else text


def _validate_bbox_4326(values: list[float]) -> list[float]:
    if not isinstance(values, (list, tuple)) or len(values) != 4:
        raise ValueError("bbox must be [west,south,east,north]")
    west, south, east, north = [float(v) for v in values]
    if not all(math.isfinite(v) for v in (west, south, east, north)):
        raise ValueError(f"bbox contains non-finite values: {values!r}")
    if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
        raise ValueError(f"bbox must be EPSG:4326 [west,south,east,north], got {values!r}")
    return [west, south, east, north]


def _geometry_object(geometry: dict | None) -> dict | None:
    if not geometry:
        return None
    geom = geometry
    if geom.get("type") == "Feature":
        geom = geom.get("geometry") or {}
    elif geom.get("type") == "FeatureCollection":
        features = geom.get("features") or []
        geom = (features[0].get("geometry") if features else None) or {}
    if geom.get("type") not in {"Polygon", "MultiPolygon"}:
        raise ValueError(
            f"CDSE geometry must be Polygon/MultiPolygon EPSG:4326, got {geom.get('type')!r}"
        )
    return geom


def _safe_log_payload(payload: dict) -> dict:
    """Small, non-sensitive payload summary for provider error logs."""
    keys = ("collections", "bbox", "datetime", "filter", "filter-lang", "limit", "intersects")
    out = {k: payload.get(k) for k in keys if k in payload}
    if "intersects" in out:
        geom = out["intersects"] or {}
        out["intersects"] = {"type": geom.get("type"), "coordinates": "<omitted>"}
    return out


# نقاط CDSE الافتراضيّة (قابلة للتجاوز بالبيئة). الأسرار **ليست** هنا — البيئة فقط.
_TOKEN_URL = os.getenv(
    "SH_TOKEN_URL",
    "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token",
)
_BASE_URL = os.getenv("SH_BASE_URL", "https://sh.dataspace.copernicus.eu")
_COLLECTION = "sentinel-2-l2a"

# ─────────────────────────────────────────────────────────────────────────────
# تعريف المؤشّرات: index → (نطاقات Sentinel-2 المطلوبة، تعبير JS بدلالة s.Bxx).
# النطاقات انعكاس [0,1] كما يوفّرها Sentinel Hub. الصيغ تطابق مصدر الحقيقة في
# band_math.py/soil_indices.py (نفس المؤشّر المحسوب عميلاً في مسار Element84).
# ─────────────────────────────────────────────────────────────────────────────
# B02 أزرق · B03 أخضر · B04 أحمر · B05 حافّة حمراء · B08 NIR · B11 SWIR1 · B12 SWIR2
INDEX_EXPR: dict[str, tuple[tuple[str, ...], str]] = {
    "ndvi": (("B04", "B08"), "(s.B08 - s.B04) / (s.B08 + s.B04)"),
    "evi": (
        ("B02", "B04", "B08"),
        "2.5 * (s.B08 - s.B04) / (s.B08 + 6.0 * s.B04 - 7.5 * s.B02 + 1.0)",
    ),
    "savi": (("B04", "B08"), "1.5 * (s.B08 - s.B04) / (s.B08 + s.B04 + 0.5)"),
    "msavi": (
        ("B04", "B08"),
        "(2.0 * s.B08 + 1.0 - Math.sqrt(Math.pow(2.0 * s.B08 + 1.0, 2) "
        "- 8.0 * (s.B08 - s.B04))) / 2.0",
    ),
    "ndwi": (("B03", "B08"), "(s.B03 - s.B08) / (s.B03 + s.B08)"),
    "ndmi": (("B08", "B11"), "(s.B08 - s.B11) / (s.B08 + s.B11)"),
    "moisture": (("B08", "B11"), "(s.B08 - s.B11) / (s.B08 + s.B11)"),
    "gndvi": (("B03", "B08"), "(s.B08 - s.B03) / (s.B08 + s.B03)"),
    "ndre": (("B05", "B08"), "(s.B08 - s.B05) / (s.B08 + s.B05)"),
    "msi": (("B08", "B11"), "s.B11 / s.B08"),
    # ملوحة التربة (NDSI قائم على SWIR — حرج للسياق اليمنيّ): (SWIR1 - SWIR2)/(SWIR1 + SWIR2).
    # قشور الملح/الجبس لها امتصاص قرب 2200nm (B12) ⇒ B11 > B12 ⇒ قيمة أعلى للتربة المالحة.
    # (المؤشّر السابق كان (B04-B08)/(B04+B08) = NDVI معكوس — انعكاس غطاء نباتيّ لا ملوحة فعليّة.)
    # ⚠ يحتاج معايرة ميدانيّة (عيّنات EC أرضيّة) لربط القيمة بمستوى ملوحة فعليّ — fixed لا verified.
    "ndsi": (("B11", "B12"), "(s.B11 - s.B12) / (s.B11 + s.B12)"),
}


def supported_indices() -> set[str]:
    """المؤشّرات التي يدعمها CDSE Process API هنا (evalscript معرَّف)."""
    return set(INDEX_EXPR)


def _cdse_credentials() -> tuple[str | None, str | None]:
    """اعتماد Copernicus: ``CDSE_CLIENT_ID/SECRET`` مع ارتداد إلى ``SH_CLIENT_ID/SECRET``.

    ``SH_*`` و``CDSE_*`` كلاهما عميل OAuth على نفس realm الـCDSE (``SH_TOKEN_URL`` يؤكّده:
    ``identity.dataspace.copernicus.eu/.../CDSE``). خدمات أخرى تُلزِم ``SH_*`` (``:?``)، فإن
    ضبط المشغّل ``SH_*`` فقط دون ``CDSE_*`` كانت الصور تُعطَّل صامتاً (بلاطات شفّافة). نقرأ
    ``SH_*`` كبديل لسدّ فخّ تهيئة شائع (مزوّدان لنفس الاعتماد). فارغ ⇒ None.
    """
    cid = os.getenv("CDSE_CLIENT_ID") or os.getenv("SH_CLIENT_ID")
    secret = os.getenv("CDSE_CLIENT_SECRET") or os.getenv("SH_CLIENT_SECRET")
    return (cid or None), (secret or None)


def is_configured() -> bool:
    """هل CDSE مُهيّأ فعليّاً؟ (اعتمادات موجودة و``CDSE_ENABLED`` ليس ``false``).

    صدق: غيابها ⇒ False ⇒ يسقط المنسّق إلى Element84 دون كسر (لا توقّف، لا تلفيق).
    """
    if os.getenv("CDSE_ENABLED", "true").strip().lower() == "false":
        return False
    cid, secret = _cdse_credentials()
    return bool(cid and secret)


# أصناف SCL (Scene Classification) للغيوم/الظلال/السيرس/الثلج التي تُقنَّع per-pixel،
# مطابقةً لمسار Element84 (main.py ~1641): 3 ظلّ غيمة · 8 غيمة متوسّطة · 9 عالية ·
# 10 سيرس · 11 ثلج. أيّ بكسل في هذه الأصناف ⇒ NaN (مستبعَد من الإحصاء).
SCL_CLOUD_CLASSES: tuple[int, ...] = (3, 8, 9, 10, 11)


def build_evalscript(index: str) -> str:
    """يبني evalscript (V3) يحسب ``index`` ويُخرِجه FLOAT32 نطاقاً واحداً.

    نقيّ وقابل للاختبار. يقنّع per-pixel: يُرجِع ``NaN`` عندما يكون البكسل بلا
    بيانات (``dataMask !== 1``) **أو** يقع في صنف غيمة/ظلّ/سيرس/ثلج من نطاق
    ``SCL`` (الأصناف في ``SCL_CLOUD_CLASSES``) — نظير قناع SCL في مسار Element84.
    يرفع ``ValueError`` لمؤشّر غير مدعوم.
    """
    if index not in INDEX_EXPR:
        raise ValueError(f"مؤشّر غير مدعوم في CDSE: {index} (المتاح: {sorted(INDEX_EXPR)})")
    bands, expr = INDEX_EXPR[index]
    # نطلب نطاق "SCL" إلى جانب نطاقات المؤشّر + dataMask كي نقنّع الغيوم per-pixel.
    band_list = ", ".join(f'"{b}"' for b in (*bands, "SCL"))
    cloud_set = ", ".join(str(c) for c in SCL_CLOUD_CLASSES)
    return (
        "//VERSION=3\n"
        "function setup() {\n"
        f'  return {{ input: [{{ bands: [{band_list}, "dataMask"] }}],\n'
        '           output: { bands: 1, sampleType: "FLOAT32" } };\n'
        "}\n"
        f"const SCL_CLOUD = [{cloud_set}];\n"
        "function evaluatePixel(s) {\n"
        f"  let v = {expr};\n"
        "  let isCloud = SCL_CLOUD.indexOf(s.SCL) !== -1;\n"
        "  return [(s.dataMask === 1 && !isCloud) ? v : NaN];\n"
        "}\n"
    )


def bbox_dims(bbox: list[float], target_res_m: float = 10.0, max_px: int = 2500) -> tuple[int, int]:
    """يحسب أبعاد المُخرَج (عرض، ارتفاع) بكسلاً لمستطيل ``bbox`` (EPSG:4326) عند ~10م.

    نقيّ. يقيّد إلى [16, ``max_px``] (حدّ Sentinel Hub Process ~2500). تقدير الأمتار/درجة
    عند خطّ العرض الأوسط (طول الموجة الطوليّة يتقلّص بـcos(lat)).
    """
    west, south, east, north = _validate_bbox_4326(bbox)
    lat_mid = math.radians((south + north) / 2.0)
    m_per_deg_lat = 111_320.0
    m_per_deg_lon = 111_320.0 * max(math.cos(lat_mid), 0.01)
    width_m = abs(east - west) * m_per_deg_lon
    height_m = abs(north - south) * m_per_deg_lat
    w = int(round(width_m / target_res_m))
    h = int(round(height_m / target_res_m))
    w = max(16, min(w, max_px))
    h = max(16, min(h, max_px))
    return w, h


class CdseClient:
    """عميل Process API مع ذاكرة توكن OAuth (client_credentials) آمنة للخيوط.

    network فقط داخل الدوالّ (httpx كسول). لا حالة أسرار في الذاكرة سوى التوكن المؤقّت.
    """

    def __init__(self, *, token_url: str | None = None, base_url: str | None = None) -> None:
        self._token_url = token_url or _TOKEN_URL
        self._base_url = (base_url or _BASE_URL).rstrip("/")
        self._token: str | None = None
        self._token_exp: float = 0.0
        self._lock = threading.Lock()

    # ── OAuth ────────────────────────────────────────────────────────────────
    def _fetch_token(self) -> str:
        import httpx

        client_id, client_secret = _cdse_credentials()
        if not (client_id and client_secret):
            raise RuntimeError("CDSE غير مُهيّأ (لا CDSE_CLIENT_ID/SECRET ولا SH_CLIENT_ID/SECRET).")
        resp = httpx.post(
            self._token_url,
            data={
                "grant_type": "client_credentials",
                "client_id": client_id,
                "client_secret": client_secret,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=30.0,
        )
        resp.raise_for_status()
        body = resp.json()
        token = body.get("access_token")
        if not token:
            raise RuntimeError("استجابة توكن CDSE بلا access_token.")
        # نطرح هامش أمان 60ث من العمر كي لا نستخدم توكناً يوشك على الانتهاء.
        self._token = token
        self._token_exp = time.time() + max(float(body.get("expires_in", 600)) - 60.0, 30.0)
        return token

    def token(self) -> str:
        """يُرجِع توكناً صالحاً (من الذاكرة إن لم ينتهِ، وإلّا يجلب جديداً)."""
        with self._lock:
            if self._token and time.time() < self._token_exp:
                return self._token
            return self._fetch_token()

    # ── Process API ──────────────────────────────────────────────────────────
    def process_index(
        self,
        *,
        index: str,
        bbox: list[float],
        time_from: str,
        time_to: str,
        geometry: dict | None = None,
        max_cloud_pct: float = 40.0,
    ) -> bytes:
        """يطلب من Process API حساب ``index`` للفترة، ويُرجِع GeoTIFF (بايتات).

        المؤشّر يُحسَب خادميّاً (evalscript) فيُعاد نطاقاً واحداً FLOAT32. ``geometry``
        (Polygon EPSG:4326) يقصّ على الحقل؛ ``mosaickingOrder=leastCC`` يختار الأقلّ غيوماً.
        يرفع عند فشل الشبكة/التصديق (يلتقطه المنسّق → fallback إلى Element84).
        """
        import httpx

        evalscript = build_evalscript(index)
        bbox = _validate_bbox_4326(bbox)
        width, height = bbox_dims(bbox)
        bounds: dict = {
            "bbox": bbox,
            "properties": {"crs": "http://www.opengis.net/def/crs/EPSG/0/4326"},
        }
        geom = _geometry_object(geometry)
        if geom:
            bounds["geometry"] = geom
        payload = {
            "input": {
                "bounds": bounds,
                "data": [
                    {
                        "type": _COLLECTION,
                        "dataFilter": {
                            "timeRange": {"from": time_from, "to": time_to},
                            "maxCloudCoverage": _clamp_cloud_pct(max_cloud_pct),
                            "mosaickingOrder": "leastCC",
                        },
                    }
                ],
            },
            "output": {
                "width": width,
                "height": height,
                "responses": [{"identifier": "default", "format": {"type": "image/tiff"}}],
            },
            "evalscript": evalscript,
        }
        resp = httpx.post(
            f"{self._base_url}/api/v1/process",
            json=payload,
            headers={
                "Authorization": f"Bearer {self.token()}",
                "Accept": "image/tiff",
            },
            timeout=120.0,
        )
        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError:
            logger.warning(
                "CDSE Process API failed status=%s body=%s payload=%s",
                resp.status_code,
                resp.text[:1200],
                _safe_log_payload(payload),
            )
            raise
        return resp.content

    def search_scenes(
        self,
        *,
        bbox: list[float],
        time_from: str,
        time_to: str,
        max_cloud_pct: float = 40.0,
        limit: int = 20,
        geometry: dict | None = None,
    ) -> list[dict]:
        """Search CDSE Sentinel Hub Catalog for Sentinel-2 scenes.

        Hardened behavior:
        - normalizes date inputs to explicit RFC3339 intervals;
        - validates bbox before sending it to the provider;
        - uses provider-safe cloud limits;
        - tries CQL2 text first and falls back to a minimal STAC request if the
          provider rejects optional filtering syntax;
        - logs provider response body and safe payload summary on errors.
        """
        import httpx

        def _bbox(values: list[float]) -> list[float]:
            return _validate_bbox_4326(values)

        cloud = _clamp_cloud_pct(max_cloud_pct)
        dt = f"{_to_rfc3339(time_from)}/{_to_rfc3339(time_to)}"
        payload: dict = {
            "collections": [_COLLECTION],
            "datetime": dt,
            "limit": max(1, min(int(limit), 100)),
            "filter": f"eo:cloud_cover <= {cloud}",
            "filter-lang": "cql2-text",
            "fields": {
                "include": [
                    "id",
                    "bbox",
                    "properties.datetime",
                    "properties.eo:cloud_cover",
                    "properties.platform",
                    "properties.s2:mgrs_tile",
                ],
                "exclude": ["assets"],
            },
            "sortby": [{"field": "properties.datetime", "direction": "desc"}],
        }
        geom = _geometry_object(geometry)
        if geom:
            payload["intersects"] = geom
        else:
            payload["bbox"] = _bbox(bbox)

        headers = {
            "Authorization": f"Bearer {self.token()}",
            "Accept": "application/geo+json, application/json",
            "Content-Type": "application/json",
        }
        url = f"{self._base_url}/api/v1/catalog/1.0.0/search"

        def _minimal_fallback(base: dict) -> dict:
            # Keep only stable STAC fields. Client-side cloud/date sorting still
            # happens below, so removing optional filter syntax does not return
            # unsafe data to callers.
            keys = ("collections", "datetime", "limit", "bbox", "intersects")
            return {k: base[k] for k in keys if k in base}

        try:
            resp = httpx.post(url, json=payload, headers=headers, timeout=30.0)
            if resp.status_code >= 400:
                logger.warning(
                    "CDSE catalog search failed: status=%s body=%s payload=%s",
                    resp.status_code,
                    resp.text[:1200],
                    _safe_log_payload(payload),
                )
                fallback = _minimal_fallback(payload)
                resp = httpx.post(url, json=fallback, headers=headers, timeout=30.0)
                if resp.status_code >= 400:
                    logger.warning(
                        "CDSE catalog fallback failed: status=%s body=%s payload=%s",
                        resp.status_code,
                        resp.text[:1200],
                        _safe_log_payload(fallback),
                    )
                    return []
            data = resp.json()
            features = list(data.get("features") or [])
            # Defensive client-side cloud filter in case fallback removed the provider filter.
            filtered: list[dict] = []
            for feature in features:
                props = feature.get("properties") or {}
                cc = props.get("eo:cloud_cover")
                try:
                    if cc is not None and float(cc) > cloud:
                        continue
                except (TypeError, ValueError):
                    pass
                filtered.append(feature)
            return filtered
        except Exception as e:  # noqa: BLE001
            logger.warning(
                "CDSE catalog search failed — returning empty list: %s", e, exc_info=True
            )
            return []


# مثيل وحيد (يُعيد استخدام ذاكرة التوكن عبر الطلبات).
_client: CdseClient | None = None
_client_lock = threading.Lock()


def get_client() -> CdseClient:
    """يُرجِع المثيل الوحيد لـ:class:`CdseClient` (lazy، آمن للخيوط)."""
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                _client = CdseClient()
    return _client

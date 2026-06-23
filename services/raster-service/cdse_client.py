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
    # ملوحة (NDSI — حرج للسياق اليمنيّ): (red - nir) / (red + nir)
    "ndsi": (("B04", "B08"), "(s.B04 - s.B08) / (s.B04 + s.B08)"),
}


def supported_indices() -> set[str]:
    """المؤشّرات التي يدعمها CDSE Process API هنا (evalscript معرَّف)."""
    return set(INDEX_EXPR)


def is_configured() -> bool:
    """هل CDSE مُهيّأ فعليّاً؟ (اعتمادات موجودة و``CDSE_ENABLED`` ليس ``false``).

    صدق: غيابها ⇒ False ⇒ يسقط المنسّق إلى Element84 دون كسر (لا توقّف، لا تلفيق).
    """
    if os.getenv("CDSE_ENABLED", "true").strip().lower() == "false":
        return False
    return bool(os.getenv("CDSE_CLIENT_ID") and os.getenv("CDSE_CLIENT_SECRET"))


def build_evalscript(index: str) -> str:
    """يبني evalscript (V3) يحسب ``index`` ويُخرِجه FLOAT32 نطاقاً واحداً.

    نقيّ وقابل للاختبار. ``dataMask`` يحوّل البكسلات بلا بيانات إلى ``NaN`` كي لا
    تلوّث الإحصاء (نظير قناع SCL في مسار Element84). يرفع ``ValueError`` لمؤشّر غير مدعوم.
    """
    if index not in INDEX_EXPR:
        raise ValueError(f"مؤشّر غير مدعوم في CDSE: {index} (المتاح: {sorted(INDEX_EXPR)})")
    bands, expr = INDEX_EXPR[index]
    band_list = ", ".join(f'"{b}"' for b in bands)
    return (
        "//VERSION=3\n"
        "function setup() {\n"
        f'  return {{ input: [{{ bands: [{band_list}, "dataMask"] }}],\n'
        '           output: { bands: 1, sampleType: "FLOAT32" } };\n'
        "}\n"
        "function evaluatePixel(s) {\n"
        f"  let v = {expr};\n"
        "  return [s.dataMask === 1 ? v : NaN];\n"
        "}\n"
    )


def bbox_dims(bbox: list[float], target_res_m: float = 10.0, max_px: int = 2500) -> tuple[int, int]:
    """يحسب أبعاد المُخرَج (عرض، ارتفاع) بكسلاً لمستطيل ``bbox`` (EPSG:4326) عند ~10م.

    نقيّ. يقيّد إلى [16, ``max_px``] (حدّ Sentinel Hub Process ~2500). تقدير الأمتار/درجة
    عند خطّ العرض الأوسط (طول الموجة الطوليّة يتقلّص بـcos(lat)).
    """
    west, south, east, north = (float(x) for x in bbox)
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

        client_id = os.getenv("CDSE_CLIENT_ID")
        client_secret = os.getenv("CDSE_CLIENT_SECRET")
        if not (client_id and client_secret):
            raise RuntimeError("CDSE غير مُهيّأ (لا CDSE_CLIENT_ID/SECRET).")
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
        width, height = bbox_dims(bbox)
        bounds: dict = {
            "bbox": [float(x) for x in bbox],
            "properties": {"crs": "http://www.opengis.net/def/crs/EPSG/0/4326"},
        }
        if geometry:
            geom = geometry
            if geom.get("type") == "Feature":
                geom = geom["geometry"]
            elif geom.get("type") == "FeatureCollection":
                geom = geom["features"][0]["geometry"]
            bounds["geometry"] = geom
        payload = {
            "input": {
                "bounds": bounds,
                "data": [
                    {
                        "type": _COLLECTION,
                        "dataFilter": {
                            "timeRange": {"from": time_from, "to": time_to},
                            "maxCloudCoverage": float(max_cloud_pct),
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
        resp.raise_for_status()
        return resp.content


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

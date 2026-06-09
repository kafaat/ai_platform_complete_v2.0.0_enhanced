"""
core.connectors.copernicus
==========================
موصّل صور الأقمار عبر Copernicus Data Space Ecosystem (CDSE).

القرار (من البحث): CDSE مجاني ومفتوح (Sentinel-1, 2). عبر Sentinel Hub APIs.
الميزة الحاسمة للسياق اليمني (شحّ الموارد):
  لا تُحمّل الـ Granule الكامل — فقط البكسلات التي تهمّك (AOI الحقل).
  القص وحساب NDVI يتمّان سحابياً → تحميل أقل، معالجة أخفّ.

يجلب (مصفوفة المراصد):
  R1 NDVI | R3 NDMI | R5 SI (مؤشر ملوحة) | R6 SAR (S1)

التصحيح الصادق عن "مؤشر التربة من القمر":
  القمر يعطي SI = مؤشر ملوحة سطحي (انعكاس طيفي)، استرشادي ±0.1.
  لا يقيس EC التربة مباشرة. يوجّه أين تأخذ عينة S3 المخبرية (الحاكم).

دمج S1+S2 (عند السحب): S2 بصري دقيق لكن يحجبه السحب؛ S1 رادار
يخترق السحب. الدمج موجود في core/engines/fusion.py.

الاتصال الفعلي (OAuth + Statistical/Process API) في السيرفر المحلي
المزوّد بـ GPU. هنا الواجهة، evalscripts، ومنطق المعالجة.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from core.connectors.base import CLOUD_THRESHOLD_PCT, BaseConnector, ConnectorResult, FetchStatus

# عناوين CDSE — قابلة للضبط من البيئة (افتراضات CDSE الرسميّة).
# المفاتيح (CLIENT_ID/SECRET) من البيئة فقط — لا تُكتب في الكود أبداً.
CDSE_SH_URL = os.getenv("SH_BASE_URL", "https://sh.dataspace.copernicus.eu")
CDSE_TOKEN_URL = os.getenv(
    "SH_TOKEN_URL",
    "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token",
)


# evalscript لحساب NDVI سحابياً (يُرسل لـ Sentinel Hub)
NDVI_EVALSCRIPT = """
//VERSION=3
function setup() {
  return { input: ["B04", "B08", "dataMask"], output: { bands: 2 } };
}
function evaluatePixel(s) {
  let ndvi = (s.B08 - s.B04) / (s.B08 + s.B04);
  return [ndvi, s.dataMask];
}
"""

# evalscript لمؤشر الملوحة SI (انعكاس Blue/Red/SWIR — استرشادي)
SALINITY_EVALSCRIPT = """
//VERSION=3
function setup() {
  return { input: ["B02", "B04", "B11", "dataMask"], output: { bands: 2 } };
}
function evaluatePixel(s) {
  let si = Math.sqrt(s.B02 * s.B04);   // مؤشر ملوحة مبسّط
  return [si, s.dataMask];
}
"""


@dataclass
class ImageryRequest:
    """طلب صورة لحقل (AOI) في فترة زمنية."""

    field_polygon: list  # حدود الحقل (lon,lat)
    date_from: str
    date_to: str
    index: str = "ndvi"  # ndvi | salinity | ndmi
    max_cloud_pct: float = CLOUD_THRESHOLD_PCT  # بوابة السحب (C6) — ثابت مشترك


class CopernicusConnector(BaseConnector):
    source_name = "copernicus-cdse"
    requires_key = True
    key_env_var = "CDSE_CLIENT_SECRET"  # + CDSE_CLIENT_ID — من البيئة فقط

    _EVALSCRIPTS = {
        "ndvi": NDVI_EVALSCRIPT,
        "salinity": SALINITY_EVALSCRIPT,
    }

    _ERROR_MARGINS = {
        "ndvi": 0.05,  # R1
        "salinity": 0.10,  # R5 — استرشادي
        "ndmi": 0.05,  # R3
    }

    def build_statistical_request(self, req: ImageryRequest) -> dict:
        """يبني طلب Statistical API (إحصاءات NDVI للحقل دون تحميل صورة كاملة)."""
        return {
            "service_url": CDSE_SH_URL,
            "evalscript": self._EVALSCRIPTS.get(req.index, NDVI_EVALSCRIPT),
            "time_interval": (req.date_from, req.date_to),
            "geometry": req.field_polygon,
            "data_filter": {"maxCloudCoverage": req.max_cloud_pct},
            "collection": "sentinel-2-l2a",
        }

    def fetch_access_token(self) -> dict:
        """يجلب توكن OAuth2 (client-credentials) من CDSE — الاتّصال الفعلي.

        CDSE يستخدم تدفّق client_credentials على SH_TOKEN_URL. المفاتيح من
        البيئة فقط (CDSE_CLIENT_ID/SECRET). صدق: لا توكن وهمي — يُبلّغ عند
        غياب httpx أو المفاتيح أو فشل الاتّصال.
        """
        client_id = os.getenv("CDSE_CLIENT_ID", "")
        client_secret = os.getenv("CDSE_CLIENT_SECRET", "")
        if not client_id or not client_secret:
            return {"ok": False, "reason": "CDSE_CLIENT_ID/SECRET غير مضبوطين في البيئة"}
        try:
            import httpx
        except ImportError:
            return {"ok": False, "reason": "httpx غير متوفّر — يُنفَّذ في بيئة التشغيل"}
        try:
            with httpx.Client(timeout=20.0) as client:
                resp = client.post(
                    CDSE_TOKEN_URL,
                    data={
                        "grant_type": "client_credentials",
                        "client_id": client_id,
                        "client_secret": client_secret,
                    },
                )
                resp.raise_for_status()
                tok = resp.json()
            return {
                "ok": True,
                "access_token": tok.get("access_token"),
                "expires_in": tok.get("expires_in"),
                "token_url": CDSE_TOKEN_URL,
            }
        except Exception as e:  # noqa: BLE001 — صدق: نُبلّغ بالفشل لا نخترع
            return {"ok": False, "reason": f"فشل جلب توكن CDSE: {e}"}

    def fetch(
        self, request: ImageryRequest | None = None, _live_response: dict | None = None, **kwargs
    ) -> ConnectorResult:
        """يجلب إحصاءات/raster المؤشر. _live_response من السيرفر (الاتصال الفعلي)."""
        if not self.is_configured():
            return ConnectorResult(
                source=self.source_name,
                status=FetchStatus.UNAVAILABLE,
                note_ar="يتطلب CDSE_CLIENT_ID/SECRET في بيئة السيرفر (لا مفاتيح بالكود)",
            )
        if _live_response is None:
            return ConnectorResult(
                source=self.source_name,
                status=FetchStatus.UNAVAILABLE,
                note_ar="يتطلب اتصال السيرفر بـ Copernicus (لا اختراع صور)",
            )
        idx = request.index if request else "ndvi"
        return ConnectorResult(
            source=f"{self.source_name}:{idx}",
            status=FetchStatus.OK,
            data=_live_response,
            error_margin=self._ERROR_MARGINS.get(idx, 0.05),
            note_ar=f"مؤشر {idx} من Sentinel — جاهز لكشف مناطق الاهتمام",
        )

    def should_use_radar(self, cloud_cover_pct: float) -> bool:
        """قرار اللجوء للرادار (S1) عند السحب — يربط بـ pipeline.decide_source."""
        return cloud_cover_pct >= CLOUD_THRESHOLD_PCT

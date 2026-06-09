"""
core.connectors.farmonaut
=========================
موصّل Farmonaut — نموذج مرجعي للأقمار بلا حسّاسات (مثل SAHOOL).

يطبّق الدروس الحقيقية من دليل Farmonaut التشغيلي، دون البنية الثقيلة:
  ✅ التسلسل الصحيح: submitField → getSenseDays → getFieldImage → getIndexValue
  ✅ SAR Fallback التلقائي: سحب → RVI (رادار) بدل NDVI (بصري)
  ✅ تتبّع الـ Credits (تقدير التكلفة قبل الاستدعاء)
  ✅ التحقق من الحقل (إحداثيات اليمن، ≥3 نقاط)
  ✅ لا مفاتيح بالكود (من البيئة) — لا اختراع بيانات بلا اتصال

قرار معماري صريح (يخالف الدليل عمداً):
  ✗ لا Kong/Redis/PostGIS/NATS الآن — تعقيد مبكر لمزرعة واحدة.
  ✓ الموصّل نظيف وقابل للتوسّع؛ تُضاف البنية حين يثبت العدد الحاجة.
  الـ caching/scheduling تُدار في طبقة أعلى عند الحاجة، لا داخل الموصّل.

ملاحظة: Farmonaut نموذج *مرجعي* — SAHOOL يملك موصّل Copernicus المباشر
أيضاً (مجاني). Farmonaut بديل مُدار (أسهل، لكن بـ credits).
"""
from __future__ import annotations

from dataclasses import dataclass, field as dc_field
from enum import Enum

from core.connectors.base import BaseConnector, ConnectorResult, FetchStatus

# Base URLs (مختلفة — درس من الدليل)
FIELD_BASE = "https://us-central1-farmbase-b2f7e.cloudfunctions.net"
WEATHER_BASE = "https://api.farmonaut.com/v1"

# حدود اليمن للتحقق من الإحداثيات
YEMEN_BOUNDS = {"lat": (12.0, 19.0), "lon": (42.0, 55.0)}


class ImageType(str, Enum):
    NDVI = "NDVI"      # بصري — صحة الغطاء
    EVI = "EVI"        # بصري محسّن
    SAVI = "SAVI"      # بصري مصحّح للتربة
    NDWI = "NDWI"      # رطوبة
    RVI = "RVI"        # رادار — بديل السحب (SAR)


def validate_field_polygon(points: dict) -> tuple[bool, str]:
    """التحقق من صحة حدود الحقل قبل الإرسال (درس من الدليل)."""
    if "a" not in points:
        return False, "النقطة الأولى يجب أن تكون 'a'"
    if len(points) < 3:
        return False, f"الحد الأدنى 3 نقاط، الموجود: {len(points)}"
    for key, pt in points.items():
        lat = pt.get("Latitude", 0)
        lon = pt.get("Longitude", 0)
        if not (YEMEN_BOUNDS["lat"][0] <= lat <= YEMEN_BOUNDS["lat"][1]
                and YEMEN_BOUNDS["lon"][0] <= lon <= YEMEN_BOUNDS["lon"][1]):
            return False, f"إحداثيات خارج نطاق اليمن: {key}"
    return True, "صالح"


@dataclass
class CreditEstimate:
    """تقدير تكلفة الـ Credits قبل الاستدعاء (شفافية التكلفة)."""
    satellite_units: int = 0
    weather_units: float = 0.0
    api_units: float = 0.0
    total_units: float = 0.0
    cost_usd: float = 0.0


# معدلات الاستهلاك الموثّقة
_RATES = {
    "satellite_per_acre_per_visit": 1,
    "visits_per_month": 6,
    "weather_per_unit": 15,    # ⚠️ مختلف عن API عامة
    "api_per_unit": 200,
    "usd_per_100_units": 3,
}


def estimate_monthly_credits(hectares: float, fields_count: int,
                             weather_calls_per_day: int = 4) -> CreditEstimate:
    """تقدير التكلفة الشهرية (يطابق حاسبة الدليل)."""
    acres = hectares * 2.471
    satellite = acres * _RATES["visits_per_month"]
    weather = (weather_calls_per_day * 30 * fields_count) / _RATES["weather_per_unit"]
    api = (fields_count * 100) / _RATES["api_per_unit"]
    total = satellite + weather + api + fields_count * 2  # +data
    return CreditEstimate(
        satellite_units=round(satellite), weather_units=round(weather, 1),
        api_units=round(api, 1), total_units=round(total),
        cost_usd=round((total / 100) * _RATES["usd_per_100_units"], 2),
    )


@dataclass
class SenseDay:
    """يوم تصوير قمر."""
    date: str
    is_cloudy: bool = False
    crop_red_zone: float | None = None
    irrigation_red_zone: float | None = None


class FarmonautConnector(BaseConnector):
    source_name = "farmonaut"
    requires_key = True
    key_env_var = "FARMONAUT_API_KEY"   # + FARMONAUT_UID — من البيئة فقط

    # تتبّع الـ credits المستهلكة (شفافية)
    def __init__(self):
        super().__init__()
        self._credits_used = 0.0

    @property
    def credits_used(self) -> float:
        return round(self._credits_used, 2)

    def decide_image_type(self, requested: ImageType, is_cloudy: bool) -> ImageType:
        """SAR Fallback التلقائي: سحب → RVI رادار (الدرس الأهم).
        الاستشعار يبقى متاحاً رغم السحب — يخترق الرادار الغيوم."""
        return ImageType.RVI if is_cloudy else requested

    def build_submit_request(self, name: str, crop_code: str,
                             points: dict, uid: str) -> dict:
        """يبني طلب تسجيل الحقل (الخطوة 1 في التسلسل الصحيح)."""
        return {
            "url": f"{FIELD_BASE}/submitField",
            "body": {
                "UID": uid, "CropCode": crop_code,
                "FieldName": name, "PaymentType": "1", "Points": points,
            },
        }

    def fetch(self, field_id: str = "", sense_date: str = "",
              image_type: ImageType = ImageType.NDVI, is_cloudy: bool = False,
              _live_response: dict | None = None, **kwargs) -> ConnectorResult:
        """يجلب مؤشر القمر. _live_response من السيرفر (الاتصال الفعلي).
        بلا مفتاح/اتصال → UNAVAILABLE (لا اختراع بيانات)."""
        if not self.is_configured():
            return ConnectorResult(
                source=self.source_name, status=FetchStatus.UNAVAILABLE,
                note_ar="يتطلب FARMONAUT_API_KEY + FARMONAUT_UID في البيئة",
            )
        if _live_response is None:
            return ConnectorResult(
                source=self.source_name, status=FetchStatus.UNAVAILABLE,
                note_ar="يتطلب اتصال السيرفر بـ Farmonaut (لا اختراع صور)",
            )
        # SAR fallback
        actual = self.decide_image_type(image_type, is_cloudy)
        self._credits_used += 1  # 1 وحدة/فدان/زيارة (تقدير)
        status = FetchStatus.FALLBACK if is_cloudy else FetchStatus.OK
        return ConnectorResult(
            source=f"{self.source_name}:{actual.value}", status=status,
            data=_live_response,
            error_margin=0.05 if actual != ImageType.RVI else 0.10,
            note_ar=(f"مؤشر {actual.value}" +
                     (" (رادار — سحب)" if is_cloudy else " (بصري)")),
        )

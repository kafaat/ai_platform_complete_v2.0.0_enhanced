"""
core.connectors.weather_openmeteo
=================================
موصّل الطقس عبر Open-Meteo (مجاني، بلا مفتاح API).

يجلب مدخلات FAO-56 الجوية (مصفوفة المراصد C1-C5):
  C1 حرارة (max/min) | C2 رطوبة | C3 رياح | C4 إشعاع | C5 مطر

نسب الخطأ المرجعية (من دستور المعلومة):
  • قياس: ±0.5°م، توقّع 48س: ±2-3°م
  • Open-Meteo نموذج إعادة تحليل — جيد للمناطق بلا محطات (كاليمن)

الاتصال الفعلي (requests/httpx) يحدث في السيرفر المحلي. هنا الواجهة
والمنطق وتحويل الاستجابة لمدخلات FAO-56 الجاهزة للمحرّك.
"""

from __future__ import annotations

from dataclasses import dataclass

from core.connectors.base import BaseConnector, ConnectorResult, FetchStatus

OPENMETEO_URL = "https://api.open-meteo.com/v1/forecast"


@dataclass
class WeatherInputs:
    """مدخلات FAO-56 الجوية — جاهزة لـ fao56.WeatherDay."""

    temp_max_c: float
    temp_min_c: float
    humidity_pct: float
    wind_speed_ms: float
    solar_radiation_mj: float
    rainfall_mm: float
    latitude: float
    elevation_m: float


class OpenMeteoConnector(BaseConnector):
    source_name = "open-meteo"
    requires_key = False  # مجاني بلا مفتاح — مثالي للسياق اليمني

    def build_request(self, lat: float, lon: float) -> dict:
        """يبني معاملات الطلب (يُنفّذه السيرفر فعلياً)."""
        return {
            "url": OPENMETEO_URL,
            "params": {
                "latitude": lat,
                "longitude": lon,
                "daily": ",".join(
                    [
                        "temperature_2m_max",
                        "temperature_2m_min",
                        "relative_humidity_2m_mean",
                        "wind_speed_10m_max",
                        "shortwave_radiation_sum",
                        "precipitation_sum",
                    ]
                ),
                "timezone": "auto",
            },
        }

    def parse_response(
        self, resp: dict, lat: float, elevation_m: float, day_index: int = 0
    ) -> WeatherInputs:
        """يحوّل استجابة Open-Meteo لمدخلات FAO-56."""
        d = resp["daily"]
        return WeatherInputs(
            temp_max_c=d["temperature_2m_max"][day_index],
            temp_min_c=d["temperature_2m_min"][day_index],
            humidity_pct=d["relative_humidity_2m_mean"][day_index],
            wind_speed_ms=d["wind_speed_10m_max"][day_index] / 3.6,  # km/h→m/s
            solar_radiation_mj=d["shortwave_radiation_sum"][day_index],
            rainfall_mm=d["precipitation_sum"][day_index],
            latitude=lat,
            elevation_m=elevation_m,
        )

    def fetch(
        self,
        lat: float = 0,
        lon: float = 0,
        elevation_m: float = 0,
        _live_response: dict | None = None,
        **kwargs,
    ) -> ConnectorResult:
        """يجلب الطقس. _live_response يُمرَّر من السيرفر (الاتصال الفعلي).
        بدونه → حالة UNAVAILABLE (لا اختراع بيانات)."""
        if _live_response is None:
            return ConnectorResult(
                source=self.source_name,
                status=FetchStatus.UNAVAILABLE,
                note_ar="يتطلب اتصال السيرفر بـ Open-Meteo (لا اختراع بيانات)",
                error_margin=-1.0,
            )
        try:
            wx = self.parse_response(_live_response, lat, elevation_m)
            return ConnectorResult(
                source=self.source_name,
                status=FetchStatus.OK,
                data=wx.__dict__,
                error_margin=0.03,  # ±2-3% توقّع
                note_ar="طقس Open-Meteo — جاهز لـ FAO-56",
            )
        except (KeyError, IndexError) as e:
            return ConnectorResult(
                source=self.source_name,
                status=FetchStatus.UNAVAILABLE,
                note_ar=f"استجابة غير صالحة: {e}",
            )

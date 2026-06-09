"""
api/weather_automation.py — أتمتة سحب الطقس من Open-Meteo

الفجوة التي يسدّها:
  endpoints الطقس (/weather/current، /weather/forecast) تعمل عند الطلب فقط
  — كلّ استدعاء يضرب Open-Meteo. لا يوجد سحب دوري يحدّث الطقس للحقول
  المسجّلة مسبقاً (proactive)، ولا cache يقلّل الضغط على المصدر الخارجي.

ما يفعله:
  ✓ يسحب الطقس دوريّاً (عبر scheduler) لإحداثيّات مسجّلة
  ✓ يخزّنه في cache بالذاكرة (TTL) — endpoints تقرأ منه بسرعة
  ✓ يعيد استخدام connector openmeteo الموجود (لا تكرار)
  ✓ معزول: فشل إحداثيّة واحدة لا يوقف البقيّة
  ✗ ليس تخزيناً دائماً (لا DB هنا) — cache بالذاكرة للجلسة
  ✗ لا يخترع حقولاً — يسحب فقط للإحداثيّات المسجّلة صراحةً

مبدأ الصدق: لو لم تُسجَّل إحداثيّات، المهمّة لا تفعل شيئاً (لا تخمّن مواقع).
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

logger = logging.getLogger("sahool.weather_automation")

# مدّة صلاحيّة الـcache (الطقس يوميّ، نحدّثه كلّ ساعة كحدّ أقصى)
WEATHER_TTL_SECONDS = 3600.0


@dataclass
class CachedWeather:
    lat: float
    lon: float
    data: dict
    fetched_at: float  # epoch seconds

    @property
    def age_seconds(self) -> float:
        return time.time() - self.fetched_at

    @property
    def is_stale(self) -> bool:
        return self.age_seconds > WEATHER_TTL_SECONDS

    def to_dict(self) -> dict:
        return {
            "lat": self.lat,
            "lon": self.lon,
            "data": self.data,
            "fetched_at_epoch": round(self.fetched_at, 1),
            "age_seconds": round(self.age_seconds, 1),
            "is_stale": self.is_stale,
        }


class WeatherAutomation:
    """يدير الإحداثيّات المسجّلة + cache الطقس + السحب الدوري.

    التخزين: بالذاكرة افتراضيّاً، مع استمرار اختياري لقاعدة البيانات
    (load_from_db / persist) — لو توفّر pool. بلا pool يعمل بالذاكرة فقط
    (صدق: لا يدّعي استمراريّة لا يملكها).
    """

    def __init__(self) -> None:
        # مفتاح: (round(lat,3), round(lon,3)) لتجنّب ازدواج طفيف
        self._locations: dict[tuple[float, float], dict] = {}
        self._cache: dict[tuple[float, float], CachedWeather] = {}
        self._pool = None  # asyncpg pool — يُضبط عبر set_pool

    def set_pool(self, pool) -> None:
        """يربط pool القاعدة لتمكين الاستمرار الدائم."""
        self._pool = pool

    @staticmethod
    def _key(lat: float, lon: float) -> tuple[float, float]:
        return (round(lat, 3), round(lon, 3))

    @staticmethod
    def _key_str(lat: float, lon: float) -> str:
        return f"{round(lat, 3)},{round(lon, 3)}"

    async def load_from_db(self) -> int:
        """يحمّل الإحداثيّات المسجّلة + آخر cache من القاعدة عند الإقلاع.

        صدق: لو لا pool، لا يفعل شيئاً ويُرجع 0.
        """
        if self._pool is None:
            return 0
        loaded = 0
        try:
            async with self._pool.acquire() as conn:
                rows = await conn.fetch(
                    "SELECT location_key, lat, lon, field_id FROM weather_automation_locations"
                )
                for r in rows:
                    k = self._key(r["lat"], r["lon"])
                    self._locations[k] = {
                        "lat": r["lat"],
                        "lon": r["lon"],
                        "field_id": r["field_id"],
                    }
                    loaded += 1
                # حمّل آخر cache (إن وُجد)
                crows = await conn.fetch(
                    "SELECT c.location_key, l.lat, l.lon, c.data_json, "
                    "EXTRACT(EPOCH FROM c.fetched_at) AS fetched_epoch "
                    "FROM weather_automation_cache c "
                    "JOIN weather_automation_locations l "
                    "  ON l.location_key = c.location_key"
                )
                import json as _json

                for r in crows:
                    k = self._key(r["lat"], r["lon"])
                    data = r["data_json"]
                    if isinstance(data, str):
                        data = _json.loads(data)
                    self._cache[k] = CachedWeather(
                        r["lat"],
                        r["lon"],
                        data,
                        float(r["fetched_epoch"]),
                    )
        except Exception as e:  # noqa: BLE001
            logger.warning("فشل تحميل أتمتة الطقس من القاعدة: %s", e)
        return loaded

    async def _persist_location(self, lat: float, lon: float, field_id: str | None) -> None:
        if self._pool is None:
            return
        try:
            async with self._pool.acquire() as conn:
                await conn.execute(
                    "INSERT INTO weather_automation_locations "
                    "(location_key, lat, lon, field_id) VALUES ($1,$2,$3,$4) "
                    "ON CONFLICT (location_key) DO UPDATE SET "
                    "lat=EXCLUDED.lat, lon=EXCLUDED.lon, field_id=EXCLUDED.field_id",
                    self._key_str(lat, lon),
                    lat,
                    lon,
                    field_id,
                )
        except Exception as e:  # noqa: BLE001
            logger.warning("فشل حفظ إحداثيّة الطقس: %s", e)

    async def _persist_cache(self, lat: float, lon: float, payload: dict) -> None:
        if self._pool is None:
            return
        try:
            import json as _json

            async with self._pool.acquire() as conn:
                await conn.execute(
                    "INSERT INTO weather_automation_cache "
                    "(location_key, data_json, fetched_at) VALUES ($1,$2,NOW()) "
                    "ON CONFLICT (location_key) DO UPDATE SET "
                    "data_json=EXCLUDED.data_json, fetched_at=NOW()",
                    self._key_str(lat, lon),
                    _json.dumps(payload),
                )
        except Exception as e:  # noqa: BLE001
            logger.warning("فشل حفظ cache الطقس: %s", e)

    def register_location(self, lat: float, lon: float, field_id: str | None = None) -> None:
        """يسجّل إحداثيّة لسحب طقسها دوريّاً (بالذاكرة فوراً)."""
        k = self._key(lat, lon)
        self._locations[k] = {"lat": lat, "lon": lon, "field_id": field_id}

    async def register_location_persistent(
        self, lat: float, lon: float, field_id: str | None = None
    ) -> None:
        """يسجّل + يحفظ في القاعدة (لو توفّر pool)."""
        self.register_location(lat, lon, field_id)
        await self._persist_location(lat, lon, field_id)

    def unregister_location(self, lat: float, lon: float) -> bool:
        k = self._key(lat, lon)
        existed = k in self._locations
        self._locations.pop(k, None)
        self._cache.pop(k, None)
        return existed

    def get_cached(self, lat: float, lon: float) -> CachedWeather | None:
        """يقرأ من الـcache (قد يكون stale — على الـcaller الفحص)."""
        return self._cache.get(self._key(lat, lon))

    def registered_count(self) -> int:
        return len(self._locations)

    def status(self) -> dict:
        return {
            "registered_locations": len(self._locations),
            "cached_entries": len(self._cache),
            "ttl_seconds": WEATHER_TTL_SECONDS,
            "entries": [c.to_dict() for c in self._cache.values()],
        }

    async def refresh_all(self) -> dict:
        """يسحب الطقس لكلّ الإحداثيّات المسجّلة (تُستدعى من scheduler).

        معزول: فشل إحداثيّة لا يوقف البقيّة. يُرجع ملخّص النجاح/الفشل.
        صدق: لو لا إحداثيّات مسجّلة، لا يفعل شيئاً (لا يضرب المصدر بلا داعٍ).
        """
        if not self._locations:
            return {"refreshed": 0, "failed": 0, "note": "لا إحداثيّات مسجّلة"}

        # استيراد متأخّر — connector قد يحتاج httpx (متاح في الحاوية)
        from api.connectors.openmeteo import describe_weather_ar, fetch_current

        refreshed = 0
        failed = 0
        errors: list[str] = []
        for k, loc in list(self._locations.items()):
            try:
                d = await fetch_current(loc["lat"], loc["lon"])
                payload = {
                    "temperature_c": d.temperature_c,
                    "humidity_pct": d.humidity_pct,
                    "wind_speed_ms": d.wind_speed_ms,
                    "precipitation_mm": d.precipitation_mm,
                    "cloud_cover_pct": d.cloud_cover_pct,
                    "weather_code": d.weather_code,
                    "weather_ar": describe_weather_ar(d.weather_code),
                    "timestamp": d.timestamp,
                    "source": "open-meteo",
                    "field_id": loc.get("field_id"),
                }
                self._cache[k] = CachedWeather(loc["lat"], loc["lon"], payload, time.time())
                await self._persist_cache(loc["lat"], loc["lon"], payload)
                refreshed += 1
            except Exception as e:  # noqa: BLE001 — عزل لكلّ إحداثيّة
                failed += 1
                errors.append(f"({loc['lat']},{loc['lon']}): {type(e).__name__}")
                logger.warning("فشل سحب طقس %s,%s: %s", loc["lat"], loc["lon"], e)

        return {
            "refreshed": refreshed,
            "failed": failed,
            "errors": errors[:10],
        }


# مثيل وحيد للتطبيق
weather_automation = WeatherAutomation()

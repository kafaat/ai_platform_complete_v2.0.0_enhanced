"""موصّل احتياطيّ لاتّجاه الرياح من MET Norway (api.met.no, locationforecast 2.0).

مصدر مفتوح (بيانات CC-BY 4.0) من معهد النرويج للأرصاد، تغطية عالميّة. يُستعمَل
**احتياطاً فقط** حين يغيب اتّجاه الرياح من Open-Meteo (المزوّد الأساسيّ) — فلا نلجأ
إلى قيمة وهميّة (سابقاً 315°). صدق: يعيد الاتّجاه الحقيقيّ بالدرجات أو ``None``.

قيود MET.no: يتطلّب ترويسة ``User-Agent`` مُعرِّفة (يرفض الطلبات بدونها). نضبطها من
البيئة ``METNO_USER_AGENT``. مُفعَّل افتراضيّاً ويُعطَّل عبر ``METNO_WIND_FALLBACK_ENABLED=0``.

fail-safe: أيّ فشل (شبكة/ترويسة/بنية غير متوقّعة) ⇒ ``None`` بلا رفع استثناء — لا
يكسر بلاطة الطقس ولا نافذة الفحص. مُخبّأ بإحداثيّة مُقرَّبة لتقليل الطلبات.
"""

from __future__ import annotations

import logging
import os
import time

import httpx

logger = logging.getLogger("sahool.metno_wind")

_BASE_URL = "https://api.met.no/weatherapi/locationforecast/2.0/compact"
_DEFAULT_UA = "SAHOOL-AgriPlatform/1.0 (https://sahool.ye; ops@sahool.ye)"
_CACHE_TTL_S = 1800.0  # نصف ساعة — اتّجاه الرياح لا يتغيّر لحظيّاً للبلاطة المُقرَّبة.
# مخبّأ بسيط في الذاكرة: (lat2, lon2) → (انتهاء, الاتّجاه|None).
_cache: dict[tuple[float, float], tuple[float, float | None]] = {}


def _truthy(raw: str | None, default: bool) -> bool:
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on", "enabled"}


def is_enabled() -> bool:
    """مُفعَّل افتراضيّاً؛ يُعطَّل عبر METNO_WIND_FALLBACK_ENABLED=0 (مثلاً لبيئة معزولة)."""
    return _truthy(os.getenv("METNO_WIND_FALLBACK_ENABLED"), True)


def _user_agent() -> str:
    return (os.getenv("METNO_USER_AGENT") or _DEFAULT_UA).strip() or _DEFAULT_UA


def parse_wind_from_direction(payload: dict) -> float | None:
    """يستخرج ``wind_from_direction`` (درجات) من أوّل خطوة زمنيّة في ردّ MET.no.

    دالّة نقيّة قابلة للاختبار بلا شبكة. بنية غير متوقّعة ⇒ ``None``.
    """
    try:
        series = payload["properties"]["timeseries"]
        details = series[0]["data"]["instant"]["details"]
        deg = details.get("wind_from_direction")
        return float(deg) if deg is not None else None
    except (KeyError, IndexError, TypeError, ValueError):
        return None


async def fetch_wind_direction_deg(
    lat: float, lon: float, *, timeout_s: float = 8.0
) -> float | None:
    """اتّجاه الرياح الحقيقيّ (درجات) من MET.no، أو ``None`` (للسقوط الصادق).

    مُخبّأ بإحداثيّة مُقرَّبة لخانتين. لا يرفع استثناءً مهما فشل.
    """
    if not is_enabled():
        return None
    key = (round(float(lat), 2), round(float(lon), 2))
    now = time.monotonic()
    hit = _cache.get(key)
    if hit and hit[0] > now:
        return hit[1]
    deg: float | None = None
    try:
        headers = {"User-Agent": _user_agent(), "Accept": "application/json"}
        params = {"lat": round(float(lat), 4), "lon": round(float(lon), 4)}
        async with httpx.AsyncClient(timeout=timeout_s, headers=headers) as client:
            resp = await client.get(_BASE_URL, params=params)
        if resp.status_code >= 400:
            logger.info("met.no wind fallback HTTP %s (%s,%s)", resp.status_code, key[0], key[1])
        else:
            deg = parse_wind_from_direction(resp.json())
    except Exception as exc:  # noqa: BLE001 — أيّ فشل ⇒ None (سقوط صادق)
        logger.info("met.no wind fallback تعذّر: %s", type(exc).__name__)
        deg = None
    _cache[key] = (now + _CACHE_TTL_S, deg)
    return deg

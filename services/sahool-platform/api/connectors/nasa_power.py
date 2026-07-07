"""api/connectors/nasa_power.py — موصّل NASA POWER (تاريخ الرياح) — مصدر مجّانيّ بلا مفتاح.

يجلب اتّجاه/سرعة الرياح اليوميّة التاريخيّة (WD10M/WS10M عند 10م) لنقطة، لتغذية وردة
الرياح ومحرّك المصدّات (``core.wind_geometry``). NASA POWER: ``community=AG``، دقّة ~0.5°،
تغطّي اليمن، بلا اعتماد. **صدق:** أيّ تعذّر (شبكة/تفكيك/غياب httpx) ⇒ ``None`` (لا اختراع
تاريخ)؛ قيمة الحارس ``-999`` تُسقَط. الجلب I/O؛ التفكيك (``parse_wind_history``) نقيّ مُختبَر.
"""

from __future__ import annotations

POWER_DAILY_URL = "https://power.larc.nasa.gov/api/temporal/daily/point"
_FILL = -999.0  # قيمة حارس NASA POWER (بيانات مفقودة) — تُسقَط لا تُعامَل صفراً.


def parse_wind_history(data: dict | None) -> list[tuple[float, float | None]] | None:
    """منطق صرف: يستخرج ``[(اتّجاه°, سرعة م/ث|None), …]`` من ردّ NASA POWER اليوميّ.

    يُسقِط قيم الحارس ``-999`` (اتّجاه غير صالح ⇒ يُتخطّى؛ سرعة غير صالحة ⇒ ``None``
    لكنّ الاتّجاه يبقى). ردّ شاذّ/فارغ ⇒ ``None`` (لا تلفيق).
    """
    try:
        params = data["properties"]["parameter"]
        wd = params["WD10M"]
    except (KeyError, TypeError):
        return None
    if not isinstance(wd, dict):
        return None
    ws = params.get("WS10M") if isinstance(params.get("WS10M"), dict) else {}
    out: list[tuple[float, float | None]] = []
    for date_key, dval in wd.items():
        try:
            deg = float(dval)
        except (TypeError, ValueError):
            continue
        if deg <= _FILL:
            continue
        spd: float | None = None
        try:
            s = float(ws.get(date_key))
            spd = s if s > _FILL else None
        except (TypeError, ValueError):
            spd = None
        out.append((deg, spd))
    return out or None


async def fetch_wind_history(
    lat: float, lon: float, start: str, end: str, *, timeout_s: float = 30.0
) -> list[tuple[float, float | None]] | None:
    """يجلب رياح NASA POWER اليوميّة في ``[start, end]`` (YYYYMMDD). ``None`` عند أيّ تعذّر."""
    try:
        import httpx
    except ImportError:
        return None
    params = {
        "parameters": "WD10M,WS10M",
        "community": "AG",
        "longitude": lon,
        "latitude": lat,
        "start": start,
        "end": end,
        "format": "JSON",
    }
    try:
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            resp = await client.get(POWER_DAILY_URL, params=params)
            resp.raise_for_status()
            data = resp.json()
    except Exception:  # noqa: BLE001 — أيّ فشل ⇒ متعذّر (لا نُسقط الطلب)
        return None
    return parse_wind_history(data)

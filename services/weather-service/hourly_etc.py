"""Native hourly ETc product (WX-I1) — weather-engine owned, pure, fail-closed.

خلفيّة: جدولة M3 الساعيّة كانت ستُبنى على تفكيك زمنيّ لرقم ETc يوميّ. هذا المنتج يُلغي
ذلك: يستهلك ET0 **الساعيّ القانونيّ** من محرّك الطقس (متغيّر Open-Meteo ``et0_fao_evapotranspiration``
الساعيّ — لا نواة ET0 محلّيّة موازية) ويحسب لكلّ ساعة Kc (مُحقَن من سياق المحصول/NDVI من
المُستهلِك، تماماً كما يُحقَن ET0 في ``compute_etc_dual`` اليوميّ) وETc=Kc·ET0 والمطر الفعّال،
ثمّ يُغلِّفها في منتج قانونيّ بجودة/نَسَب/بصمة حتميّة على نمط ``et0.py``/``canonical_daily_weather_series.py``.

صدق معماريّ: محرّك الطقس حياديّ الحقل (lat/lon)، فلا يملك سياق المحصول. لذلك Kc يُحقَن (لا
يُختلَق): ساعة بلا Kc �⇒ ``etc_mm=None`` + قيد مُصرَّح (لا ETc مُختلَق). ET0 المصدر الوحيد هو
المنتج الساعيّ للمحرّك — لا تفكيك ولا احتياطيّ صامت. Penman-Monteith المحلّيّ (إن لزم لاحقاً)
مسار تحقّق/احتياطيّ **مُعلَن** فقط، لا نواة موازية.
"""

from __future__ import annotations

import hashlib
import json

PRODUCT_ID = "etc_hourly"
FORMULA_VERSION = "etc/fao56-dual/1.0.0"  # ETc = Kc·ET0 (Kc مُحقَن؛ ET0 من منتج المحرّك)
SCHEMA_VERSION = "wx-i1/hourly-etc-series/1.0.0"
SNAPSHOT_SCHEME = "wsnap/sha1/1"
OWNER = "weather-service"
UNIT = "mm/h"

# نموذج المطر الفعّال الساعيّ (مُصرَّح، قابل للمعايرة): جزء ثابت من هطول الساعة يصل الجذور.
# ⚠ منحنى USDA-SCS اليوميّ (نقطة كسر 75mm) مُعرَّف على عمق يوميّ لا ساعيّ، فلا يُطبَّق هنا؛
# نستعمل جزء ترشّح ساعيّاً (افتراض 1.0 = الهطول الخام) ونُصرّح بذلك كقيد. راجع
# water_balance._effective_rain للمسار اليوميّ (منحنى SCS) — مصدرا حقيقة منفصلان قصداً.
DEFAULT_HOURLY_INFILTRATION = 1.0


def _num(value: object) -> float | None:
    """يحوّل إلى float موجب-الدلالة أو None (لا يُسقِط، لا يختلق)."""
    if value is None:
        return None
    try:
        out = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if out != out:  # NaN
        return None
    return out


def _hourly_snapshot_id(records: list[dict]) -> str:
    """بصمة حتميّة لمتّجه الساعات المُستخدَم — هويّة اللقطة (لا زمن/عشوائيّة).

    نفس المدخلات ⇒ نفس المُعرِّف (dedup/shadow-compare). sha1 لـJSON مقنَّن للحقول
    المؤثّرة فقط (الوقت + ET0 + الهطول + Kc) مُقرَّبة، بترتيب زمنيّ ثابت.
    """
    canonical = [
        {
            "t": r.get("hour"),
            "et0": round(v, 4) if isinstance((v := _num(r.get("et0_mm"))), float) else None,
            "p": round(v, 4) if isinstance((v := _num(r.get("precip_mm"))), float) else None,
            "kc": round(v, 4) if isinstance((v := _num(r.get("kc"))), float) else None,
        }
        for r in records
    ]
    digest = hashlib.sha1(  # بصمة/هويّة لا أمان تعميّة (bandit B324 / ruff S324)
        json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode("utf-8"),
        usedforsecurity=False,
    ).hexdigest()[:16]
    return f"{SNAPSHOT_SCHEME}:{digest}"


def _effective_rain_hourly(precip_mm: float | None, infiltration: float) -> float | None:
    """المطر الفعّال الساعيّ = هطول الساعة × جزء الترشّح (مُصرَّح، لا منحنى يوميّ)."""
    p = _num(precip_mm)
    if p is None:
        return None
    if p <= 0:
        return 0.0
    return round(p * infiltration, 4)


def hourly_etc_product(
    *,
    records: list[dict],
    infiltration_fraction: float = DEFAULT_HOURLY_INFILTRATION,
    valid_time: str | None = None,
    hourly_snapshot_id_override: str | None = None,
) -> dict:
    """يبني منتج ETc الساعيّ القانونيّ من سجلّات ساعيّة.

    كلّ سجلّ مدخل: ``{hour(ISO-8601 UTC), et0_mm(من منتج المحرّك), precip_mm, kc(مُحقَن أو None)}``.
    المخرَج لكلّ ساعة: ``{hour, et0_mm, kc, etc_mm, effective_rain_mm}`` — و``etc_mm=kc·et0``
    فقط حين توفّر كلاهما (وإلّا None + قيد). الغلاف يحمل جودة/نَسَب/بصمة حتميّة.

    fail-closed: بلا ساعات صالحة ⇒ ``quality_status="unavailable"`` + سبب (لا 5xx، لا اختلاق).
    """
    infiltration = _num(infiltration_fraction)
    if infiltration is None or infiltration < 0:
        infiltration = DEFAULT_HOURLY_INFILTRATION

    hours: list[dict] = []
    limitations: list[str] = []
    missing_et0 = 0
    missing_kc = 0
    computed = 0

    for raw in records:
        when = raw.get("hour")
        et0 = _num(raw.get("et0_mm"))
        kc = _num(raw.get("kc"))
        p_eff = _effective_rain_hourly(raw.get("precip_mm"), infiltration)
        if when is None:
            continue  # سجلّ بلا وقت لا يدخل السلسلة (لا نختلق ترتيباً)
        if et0 is None:
            missing_et0 += 1
        etc = None
        if et0 is not None and kc is not None:
            if kc < 0:
                kc = None
                missing_kc += 1
            else:
                etc = round(kc * et0, 4)
                computed += 1
        if kc is None and et0 is not None:
            missing_kc += 1
        hours.append(
            {
                "hour": when,
                "et0_mm": round(et0, 4) if et0 is not None else None,
                "kc": round(kc, 4) if kc is not None else None,
                "etc_mm": etc,
                "effective_rain_mm": p_eff,
            }
        )

    # ترتيب زمنيّ ثابت + إزالة تكرار الساعة نفسها (آخر قيمة تفوز) — حتميّة النَّسَب.
    seen: dict[str, dict] = {}
    for h in hours:
        seen[str(h["hour"])] = h
    ordered = [seen[k] for k in sorted(seen)]

    total_hours = len(ordered)
    if total_hours == 0:
        quality_status = "unavailable"
        limitations.append("no valid hourly records supplied")
    elif missing_et0 == total_hours:
        quality_status = "unavailable"
        limitations.append("hourly ET0 missing for all hours (weather-engine product required)")
    elif missing_et0 or missing_kc:
        quality_status = "partial"
        if missing_et0:
            limitations.append(f"hourly ET0 missing for {missing_et0}/{total_hours} hours")
        if missing_kc:
            limitations.append(
                f"Kc not injected for {missing_kc}/{total_hours} hours — ETc omitted there"
            )
    else:
        quality_status = "ok"

    # المطر الفعّال الساعيّ نموذج جزء ثابت (مُصرَّح دائماً، لا منحنى SCS اليوميّ).
    limitations.append(
        f"effective rainfall uses a fixed hourly infiltration fraction ({infiltration}); "
        "not the daily USDA-SCS curve"
    )
    if valid_time is None:
        limitations.append("valid_time not supplied by consumer")

    snap_id = hourly_snapshot_id_override or _hourly_snapshot_id(ordered)
    et0_provided = total_hours - missing_et0
    input_completeness = round(et0_provided / total_hours, 4) if total_hours else 0.0

    return {
        "product": PRODUCT_ID,
        "product_id": PRODUCT_ID,
        "schema_version": SCHEMA_VERSION,
        "formula_version": FORMULA_VERSION,
        "owner": OWNER,
        "unit": UNIT,
        "method": "hourly-native-et0 × injected-Kc (no daily disaggregation)",
        "hours": ordered,
        "hours_count": total_hours,
        "hours_with_etc": computed,
        "input_completeness": input_completeness,
        "quality_status": quality_status,
        "weather_snapshot_id": snap_id,
        "valid_time": valid_time,
        "provenance": {
            "et0_source": "weather-engine hourly product (et0_fao_evapotranspiration)",
            "kc_source": "injected by consumer (crop stage / NDVI, platform fao56)",
            "effective_rain_model": f"fixed hourly infiltration={infiltration}",
        },
        "limitations": limitations,
    }

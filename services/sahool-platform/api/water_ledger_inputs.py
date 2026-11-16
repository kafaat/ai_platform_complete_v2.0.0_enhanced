"""مدخلات دفتر الماء اليوميّ — نقيّة، خارج المسار المجمَّد، ومختبرة.

العامل اليوميّ (``phase_runtime_workers.run_water_ledger_once``، مسار GATE-01 مجمَّد) كان
يكتب قيد اليوم بمدخلاتٍ لا تمثّل الحقل، وكلّ واحدةٍ منها مقيسة في الكود:

* **Kc منتصف الموسم كلَّ يوم** (``kc_from_ndvi(None, kc_map, "mid")``)، والقمحُ لأيّ محصولٍ
  غير معروف — فبادرةُ الذرة تُحسَب بـKc 1.20 بدل 0.30 (FAO-56 Fig. 34).
* **عمق جذورٍ افتراضيّ 0.6م** من جدول قوام (``root_depth_m=None``) بدل منطقة الجذور
  القانونيّة (طبقات التربة المقيسة × سياسة جذور المحصول).
* **ET0 بـHargreaves دائماً:** لا تُمرَّر الرطوبة النسبيّة، فلا يعمل Penman-Monteith أبداً،
  وتُسقَط جودةُ ET0 (``degraded``) فلا تنعكس على ثقة القيد.

وكان يُخشى خطأٌ رابع كامن: الرياحُ المتاحة ``wind_speed_10m_max`` — **قصوى اليوم على
ارتفاع 10م** — تُمرَّر بوصفها ``wind_2m_ms``. لا تؤثّر اليوم لأنّ PM لا يعمل، لكنّها كانت
ستدخل حين تُضاف الرطوبة. فهنا: الرياحُ تُؤخَذ من **المتوسّط** فقط، وتُحوَّل إلى ارتفاع 2م
بمعادلة FAO-56 47، ولا تُشتقّ من القصوى أبداً.

ولا يُختلَق شيء: محصولٌ بلا بطاقة أو موسمٌ بلا تاريخ زراعة ⇒ ``None`` ويتخطّى العامل الحقل
بسببٍ معلن، ومنطقةُ جذورٍ محجوبة ⇒ احتياطُ القوام **بعلَمٍ** يُخفّض الثقة.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from core.engines.fao56 import kc_for_age
from core.season_phenology import crop_kc_profile, resolve_crop_id

#: FAO-56 Eq. 47 — تحويل سرعة الريح المقيسة على ارتفاع ``z`` م إلى ارتفاع 2م.
WIND_MEASUREMENT_HEIGHT_M = 10.0


def wind_2m_from_height(u_z_ms: float, z_m: float = WIND_MEASUREMENT_HEIGHT_M) -> float:
    """``u2 = uz · 4.87 / ln(67.8·z − 5.42)`` (FAO-56 Eq. 47). لـz=10م المعامل ≈ 0.748."""
    if z_m <= 0.1:
        raise ValueError("ارتفاع القياس يجب أن يتجاوز 0.1م")
    return u_z_ms * 4.87 / math.log(67.8 * z_m - 5.42)


def _finite(value) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(value) else None


def et0_weather_inputs(day: dict | None) -> dict:
    """مدخلات PM الإضافيّة من يوم التوقّع المُطبَّع — **المتوسّط لا القصوى**.

    ``wind_mean_10m_ms`` ⇒ ``wind_2m_ms`` بالمعادلة 47. ``wind_max_ms`` لا يُستعمَل: قصوى
    اليوم تُضخّم ET0، ولا تحويلَ موثوقاً من القصوى إلى المتوسّط. غيابُ أيٍّ منها ⇒ ``None``
    فيسقط المحرّك إلى Hargreaves **مُعلَناً** (``degraded``) لا مُخفىً.
    """
    day = day or {}
    wind_mean = _finite(day.get("wind_mean_10m_ms"))
    rh = _finite(day.get("rh_mean_pct"))
    return {
        "solar_rad_mj_m2": _finite(day.get("solar_radiation_mj_m2")),
        "rh_mean_pct": rh if rh is not None and 0.0 <= rh <= 100.0 else None,
        "wind_2m_ms": (
            round(wind_2m_from_height(wind_mean), 3)
            if wind_mean is not None and wind_mean >= 0
            else None
        ),
    }


def et0_is_reference(product: dict | None) -> bool:
    """ET0 مرجعيّ (FAO-56 PM) أم احتياطٌ متدهور؟ ما لا يُعلِن طريقته يُعدّ متدهوراً.

    للطريقة وحدها: سلسلةُ ET0 (``/agro/et0/series``) تُعلِن ``methods`` لكلّ يوم ولا تُعلِن
    جودته، ومستهلكُها (``canonical_water_state``) يحجب قبلها إن غاب الارتفاع. لمنتجٍ واحدٍ
    يُعلِن جودته استعمل ``et0_product_is_reference``.
    """
    return (product or {}).get("method") == "fao56_penman_monteith"


def et0_product_is_reference(product: dict | None) -> bool:
    """منتجُ ET0 الواحد (``/agro/et0``) مرجعيّ؟ PM **و** ``quality_status='validated'``.

    weather-7: الطريقةُ وحدها لا تكفي. المحرّك يحسب PM بارتفاعٍ مفقود عند مستوى البحر، أو
    بمدخلٍ مرفوض، ويُعلِن ذلك ``degraded`` — وكان العامل يعدّه مرجعاً لأنّه يقرأ ``method``
    وحده. ما لا يُعلِن جودته يُعدّ متدهوراً.
    """
    return et0_is_reference(product) and (product or {}).get("quality_status") == "validated"


def field_elevation_m(value) -> float | None:
    """ارتفاع الحقل من ``fields.elevation_m`` (NUMERIC ⇒ ``Decimal``) أو ``None``.

    weather-7: كان العامل لا يمرّر الارتفاع فيحسب المحرّك PM عند مستوى البحر (ضغطٌ 101.3
    كيلوباسكال بدل ~77 عند 2300م). غائبٌ أو غيرُ منتهٍ ⇒ ``None`` ويتخطّى العامل اليوم
    بسببٍ معلن؛ لا يُفترَض ارتفاعٌ (لا 0 ولا 2000).
    """
    if isinstance(value, Decimal):
        value = float(value)
    return _finite(value)


#: مصدر ``water_ledger.rain_mm`` (v278): توقّعُ اليوم حين يُكتب القيد، والأرشيفُ المرصود
#: حين يُعاد تسجيله بعد أن يمتلئ الأرشيف.
RAIN_SOURCE_FORECAST = "forecast"
RAIN_SOURCE_OBSERVED = "observed"

#: نافذةُ إعادة تسجيل المطر (أيّام قبل اليوم). أرشيفُ خدمة الطقس (إعادة تحليل ERA5) يتأخّر
#: نحو خمسة أيّام (``season_simulation._ERA5_LAG_DAYS``): مطرُ الأمس غائبٌ عنه عادةً. لذلك
#: لا يُفحَص قيدُ الأمس وحده بل كلُّ قيدٍ آليٍّ متوقَّع المطر في النافذة، كلَّ دورة، حتّى
#: يمتلئ الأرشيف. النافذةُ أطولُ من التأخّر بهامش؛ ما يخرج منها متوقَّعاً يبقى معلَناً
#: ``rain_source='forecast'`` لا مرصوداً.
RAIN_RECONCILE_WINDOW_DAYS = 10


def observed_rain_by_date(historical: dict | None) -> dict[date, float]:
    """هطولُ كلّ يومٍ مرصود في عرض الأرشيف (``/v1/weather/historical``).

    يُطابَق اليومُ بتاريخه لا بموضعه، ولا يُقرأ الغيابُ صفراً: يومٌ بلا ``precipitation_mm``
    منتهٍ غير سالب لا يظهر في الناتج، فيبقى قيدُه على التوقّع معلَناً.
    """
    out: dict[date, float] = {}
    for entry in (historical or {}).get("days") or []:
        if not isinstance(entry, dict):
            continue
        try:
            day = date.fromisoformat(str(entry.get("date") or "")[:10])
        except ValueError:
            continue
        rain = _finite(entry.get("precipitation_mm"))
        if rain is not None and rain >= 0:
            out[day] = rain
    return out


def observed_rain_for_date(historical: dict | None, day: date) -> float | None:
    """هطولُ ``day`` من عرض الأرشيف أو ``None`` (الغيابُ ليس صفراً)."""
    return observed_rain_by_date(historical).get(day)


def _row_rebuildable(row, auto_created_by: str) -> bool:
    """قيدٌ يمكن إعادة بناء استنزافه من بداية يومه؟

    كتبه العامل نفسه (اليدويّ وقيدُ الريّ المطبَّق لا يُلمَسان)، بأعلامٍ مقروءة، بلا أيّامٍ
    متخطّاةٍ قبله (بدايتُه عندئذٍ تقديرٌ لا يُعاد بناؤه)، بمدخلاتٍ منتهية، و**بـTAW/RAW
    المخزَّنين معه** (v278): لا يُعاد حسابُ قيدٍ قديمٍ بنسيج اليوم أو جذور اليوم.
    """
    from api.water_ledger_auto import ledger_notes_from_decision

    if row is None or row["ledger_date"] is None or row["created_by"] != auto_created_by:
        return False
    notes = ledger_notes_from_decision(row["decision"])
    if notes is None or "missing_days_consumption_estimated" in notes:
        return False
    if any(_finite(row[k]) is None for k in ("etc_mm", "irrigation_mm", "rain_mm")):
        return False
    taw, raw = _finite(row["taw_mm"]), _finite(row["raw_mm"])
    return taw is not None and taw > 0 and raw is not None and 0 <= raw <= taw


def rain_reconcile_start(
    rows, today: date, auto_created_by: str, *, window_days: int = RAIN_RECONCILE_WINDOW_DAYS
) -> date | None:
    """أقدمُ يومٍ في النافذة قيدُه آليٌّ متوقَّعُ المطر قابلٌ لإعادة البناء، أو ``None``.

    ``None`` ⇒ لا طلبَ إلى الأرشيف في هذه الدورة (لا نداءَ شبكةٍ بلا قيدٍ ينتظره).
    """
    first = today - timedelta(days=window_days)
    for row in rows or []:
        day = row["ledger_date"]
        if (
            day is not None
            and first <= day < today
            and row["rain_source"] == RAIN_SOURCE_FORECAST
            and _row_rebuildable(row, auto_created_by)
        ):
            return day
    return None


def rebuild_ledger_row(
    row,
    *,
    start_depletion_mm: float | None,
    rain_mm: float,
    rain_source: str | None,
    taw_mm: float,
    raw_mm: float,
) -> dict | None:
    """قيدٌ آليٌّ مُعاداً حسابُه من بداية يومه — نقيّ.

    ``Dr = clamp(Dr_start + ETc − P_eff(rain) − I, 0, TAW)`` بالمعادلة نفسها في
    ``compute_daily_ledger_entry``، و``Dr_start`` استنزافُ القيد السابق (مُعاداً بناؤه إن
    تغيّر)، أو التهيئة المعلنة Dr=0 إن حمل القيدُ ``bootstrap_assumed_field_capacity``.
    بدايةٌ مفقودة في غير التهيئة ⇒ ``None`` (لا يُختلَق صفر). مطرٌ صار مرصوداً يُسقِط علَمَ
    ``precipitation_assumed_zero``؛ وتُشتقّ الثقةُ من الأعلام الباقية كما يشتقّها المُنتِج.
    """
    from api.water_balance import _effective_rain
    from api.water_ledger_auto import (
        _BIASING_ASSUMPTIONS,
        _BOOTSTRAP_NOTE,
        CONFIDENCE_AUTO,
        CONFIDENCE_BOOTSTRAP,
        applied_water_status,
        ledger_notes_from_decision,
    )

    rain = _finite(rain_mm)
    if rain is None or rain < 0:
        raise ValueError(f"rain_mm يجب أن يكون عدداً منتهياً ≥ 0 — وصل {rain_mm!r}")
    if not (_finite(taw_mm) and taw_mm > 0) or _finite(raw_mm) is None or raw_mm > taw_mm:
        raise ValueError("TAW/RAW غير صالحين لإعادة حساب القيد")
    dropped = {"depletion_capped_at_taw"}
    if rain_source == RAIN_SOURCE_OBSERVED:
        dropped.add("precipitation_assumed_zero")
    notes = [n for n in (ledger_notes_from_decision(row["decision"]) or []) if n not in dropped]
    if _BOOTSTRAP_NOTE in notes:
        start = 0.0
    elif _finite(start_depletion_mm) is None:
        return None
    else:
        start = min(max(float(start_depletion_mm), 0.0), taw_mm)
    raw = start + float(row["etc_mm"]) - _effective_rain(rain) - float(row["irrigation_mm"])
    depletion = round(min(max(raw, 0.0), taw_mm), 2)
    if raw > taw_mm:
        notes.append("depletion_capped_at_taw")
    return {
        "rain_mm": rain,
        "rain_source": rain_source,
        "depletion_mm": depletion,
        "deficit_mm": round(max(depletion - raw_mm, 0.0), 2),
        "confidence": (
            CONFIDENCE_BOOTSTRAP
            if (_BOOTSTRAP_NOTE in notes or _BIASING_ASSUMPTIONS.intersection(notes))
            else CONFIDENCE_AUTO
        ),
        "decision": "auto:" + (";".join(notes) if notes else "daily_balance"),
        "applied_water_status": applied_water_status(notes),
    }


def reconcile_forecast_rain(
    prev,
    *,
    start_depletion_mm: float | None,
    observed_rain_mm: float,
    taw_mm: float,
    raw_mm: float,
) -> dict | None:
    """قيدٌ مُعاداً حسابُه بالمطر المرصود بدل المتوقَّع (``rebuild_ledger_row`` بمطرٍ مرصود)."""
    return rebuild_ledger_row(
        prev,
        start_depletion_mm=start_depletion_mm,
        rain_mm=observed_rain_mm,
        rain_source=RAIN_SOURCE_OBSERVED,
        taw_mm=taw_mm,
        raw_mm=raw_mm,
    )


def rebuild_rain_chain(
    rows,
    observed: dict[date, float],
    today: date,
    auto_created_by: str,
    *,
    window_days: int = RAIN_RECONCILE_WINDOW_DAYS,
) -> tuple[list[dict], float | None]:
    """إعادةُ تسجيل المطر المرصود في النافذة وإعادةُ بناء السلسلة بعده — نقيّ.

    ``rows`` قيودُ الحقل قبل اليوم تصاعديّاً (بما فيها يومٌ قبل النافذة مرساةً). لكلّ قيد:

    * آليٌّ متوقَّعُ المطر داخل النافذة وله رصدٌ ⇒ مطرُه مرصودٌ واستنزافُه من بداية يومه؛
    * آليٌّ تغيّرت بدايتُه (القيدُ السابق المتّصل أُعيد بناؤه) ⇒ يُعاد بناؤه بمطره كما هو
      ومصدره كما هو (توقّعٌ لم يُرصَد بعد يبقى توقّعاً)؛
    * غيرُ ذلك (يدويّ، بعد فجوة، بلا TAW مخزَّن، …) ⇒ لا يُلمَس وتنقطع السلسلة عنده: قيمتُه
      هي البداية لما بعده كما هي مخزَّنة.

    يعيد ``(updates, carry)``: التحديثات بالترتيب، كلٌّ يحمل ما كان عليه القيد
    (``expected_*``) ليُشترَط في UPDATE، و``carry`` استنزافُ آخر قيدٍ إن أُعيد بناؤه (بدايةُ
    اليوم) أو ``None``.
    """
    first = today - timedelta(days=window_days)
    updates: list[dict] = []
    carry: float | None = None
    previous = None
    for row in rows or []:
        day = row["ledger_date"]
        contiguous = (
            previous is not None
            and day is not None
            and previous["ledger_date"] is not None
            and day == previous["ledger_date"] + timedelta(days=1)
        )
        in_window = day is not None and first <= day < today
        rebuildable = in_window and _row_rebuildable(row, auto_created_by)
        rain_fix = rebuildable and row["rain_source"] == RAIN_SOURCE_FORECAST and day in observed
        start_changed = carry is not None and contiguous
        fixed = None
        if rebuildable and (rain_fix or start_changed):
            if start_changed:
                start = carry
            elif contiguous:
                start = _finite(previous["depletion_mm"])
            else:
                start = None
            fixed = rebuild_ledger_row(
                row,
                start_depletion_mm=start,
                rain_mm=observed[day] if rain_fix else float(row["rain_mm"]),
                rain_source=RAIN_SOURCE_OBSERVED if rain_fix else row["rain_source"],
                taw_mm=float(row["taw_mm"]),
                raw_mm=float(row["raw_mm"]),
            )
        if fixed is None:
            carry = None
        else:
            updates.append(
                {
                    **fixed,
                    "ledger_date": day,
                    "expected_rain_source": row["rain_source"],
                    "expected_depletion_mm": row["depletion_mm"],
                }
            )
            carry = fixed["depletion_mm"]
        previous = row
    return updates, carry


@dataclass(frozen=True)
class DailyKc:
    crop_id: str
    kc: float
    stage: str
    days_since_sowing: int
    phenology_progress: float


#: أسماء مراحل ``water_ledger.stage`` باصطلاح المنصّة (كما في ``v226`` ``phenology_stage``)
#: لا أسماء ``GrowthStage`` الداخليّة.
_LEDGER_STAGE = {"mid_season": "mid", "late_season": "late"}


def daily_kc(crop: str | None, sowing_date: date | None, today: date) -> DailyKc | None:
    """Kc الطوريّ لليوم من بطاقة المحصول (منحنى FAO-56 الرباعيّ) — أو ``None`` إن جُهِل.

    لا احتياطَ إلى محصولٍ آخر ولا إلى Kc منتصف الموسم: محصولٌ بلا بطاقة، أو بلا تاريخ
    زراعة، أو تاريخٌ في المستقبل ⇒ ``None``.
    """
    crop_id = resolve_crop_id(crop)
    profile = crop_kc_profile(crop_id)
    if profile is None or not isinstance(sowing_date, date):
        return None
    days = (today - sowing_date).days
    if days < 0:
        return None
    kc, stage = kc_for_age(profile, days)
    stage_label = _LEDGER_STAGE.get(stage.value, stage.value)
    season_days = max(1.0, float(sum(profile.stage_days)))
    return DailyKc(
        crop_id=str(crop_id),
        kc=round(float(kc), 3),
        stage=stage_label,
        days_since_sowing=days,
        phenology_progress=min(1.0, days / season_days),
    )


#: FAO-56 Table 22 — نسبة الاستنزاف المسموح ``p`` عند ETc ≈ 5 مم/يوم. القيمُ مُدخَلةٌ من
#: الجدول للمحاصيل التي تحمل بطاقةً هنا؛ ما ليس فيها يبقى على 0.5 **بعلَم** لا بصمت.
DEPLETION_FRACTION_TABLE22: dict[str, float] = {
    "maize": 0.55,
    "wheat": 0.55,
    "barley": 0.55,
    "sorghum": 0.55,
    "millet": 0.55,
    "alfalfa": 0.55,
    "cotton": 0.65,
    "sunflower": 0.45,
    "peanut": 0.50,
    "chickpea": 0.50,
    "lentil": 0.50,
    "faba_bean": 0.45,
    "pea": 0.35,
    "tomato": 0.40,
    "pepper": 0.30,
    "eggplant": 0.45,
    "potato": 0.35,
    "onion": 0.30,
    "garlic": 0.30,
    "cucumber": 0.50,
    "melon": 0.40,
    "watermelon": 0.40,
    "citrus": 0.50,
    "date_palm": 0.50,
}
DEPLETION_FRACTION_DEFAULT = 0.5


def depletion_fraction(crop: str | None, etc_mm_day: float | None) -> tuple[float, bool]:
    """``p`` للمحصول مُعدَّلاً بـETc: ``p = p_table + 0.04·(5 − ETc)`` محصوراً في [0.1, 0.8].

    (FAO-56، الحاشية على Table 22.) تُرجِع ``(p, is_default)``؛ محصولٌ بلا قيمة جدول ⇒
    ``(0.5 مُعدَّلة, True)`` — والمستدعي يعلن العلَم.
    """
    crop_id = resolve_crop_id(crop)
    base = DEPLETION_FRACTION_TABLE22.get(str(crop_id)) if crop_id else None
    is_default = base is None
    p = DEPLETION_FRACTION_DEFAULT if base is None else base
    etc = _finite(etc_mm_day)
    if etc is not None and etc >= 0:
        p = p + 0.04 * (5.0 - etc)
    return round(min(0.8, max(0.1, p)), 3), is_default


async def ledger_root_zone(
    conn,
    *,
    tenant_id: str,
    field_id: str,
    season_id: str | None,
    crop_kc: DailyKc,
    variety: str | None,
    texture: str | None,
    etc_mm_day: float,
) -> dict:
    """TAW/RAW لقيد اليوم: منطقة الجذور القانونيّة أوّلاً، واحتياطُ القوام **بعلَم**.

    ``p`` من FAO-56 Table 22 مُعدَّلاً بـETc اليوم (لا 0.5 ثابتة). المسار القانونيّ يتطلّب
    طبقات تربة مقيسة وسياسة جذور مُعتمَدة للمحصول؛ حجبُه (سببٌ معلن) ⇒ جدول القوام بعمقٍ
    افتراضيّ، و``root_zone_texture_fallback=True`` يُخفّض ثقة القيد. لا يُختلَق عمق.
    """
    from api.canonical_root_zone_profile import resolve_canonical_root_zone_profile
    from api.soil_water import soil_water_params

    p, p_default = depletion_fraction(crop_kc.crop_id, etc_mm_day)
    blocked_reason = "season_unknown"
    if season_id:
        profile = await resolve_canonical_root_zone_profile(
            conn,
            tenant_id=tenant_id,
            field_id=field_id,
            season_id=season_id,
            crop=crop_kc.crop_id,
            variety=variety,
            phenology_progress=crop_kc.phenology_progress,
            raw_fraction=p,
        )
        if not isinstance(profile, dict):
            return {
                "taw_mm": float(profile.taw_mm),
                "raw_mm": float(profile.raw_mm),
                "root_depth_m": float(profile.root_depth_m),
                "source": "canonical_root_zone",
                "root_zone_texture_fallback": False,
                "depletion_fraction": p,
                "depletion_fraction_default": p_default,
            }
        blocked_reason = str(profile.get("reason") or "canonical_root_zone_blocked")
    sw = soil_water_params(texture=texture, root_depth_m=None, raw_fraction=p)
    return {
        "taw_mm": float(sw["taw_mm"]),
        "raw_mm": float(sw["raw_mm"]),
        "root_depth_m": None,
        "source": f"texture_table_fallback:{blocked_reason}",
        "root_zone_texture_fallback": True,
        "depletion_fraction": p,
        "depletion_fraction_default": p_default,
    }

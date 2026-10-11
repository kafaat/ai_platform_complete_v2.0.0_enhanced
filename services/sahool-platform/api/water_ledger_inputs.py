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
from datetime import date

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
    """ET0 مرجعيّ (FAO-56 PM) أم احتياطٌ متدهور؟ ما لا يُعلِن طريقته يُعدّ متدهوراً."""
    return (product or {}).get("method") == "fao56_penman_monteith"


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

"""core/season_phenology.py — مراحل نموّ الموسم المدفوعة ببطاقة المحصول (Phenology).

يربط بطاقات المحاصيل (core.crop_cards، كتلة phenology + Kc) بحالة موسم حقيقيّ
(تاريخ البذار + اليوم) ليُنتج: المرحلة الحاليّة المُسمّاة، معامل المحصول Kc الطوريّ
(FAO-56 عبر core.engines.fao56)، وخطّ زمن المراحل بتواريخ مطلقة وحالة (ماضٍ/حاليّ/قادم)،
وعلَم المرحلة التكاثريّة (التزهير) — أدقّ من التقدير العامّ في main._STAGE_DAY_BOUNDS.

دالّة نقيّة بالكامل (لا قاعدة، لا I/O، لا شبكة) — تُختبَر offline. تُغذّي توصيات الريّ
(Kc الطوريّ)، تصعيد التنبيهات (إجهاد عند التزهير)، ومهامّ الطور المقترَحة. الحقل غير
المعرَّف في بطاقة المحصول ⇒ None/قائمة فارغة (صدق: لا تقدير مُلفَّق).
"""

from __future__ import annotations

from datetime import date, timedelta

from core.crop_cards.loader import load_crop_card
from core.engines.fao56 import CropKcProfile, kc_for_age

# اسم المحصول (كما يخزَّن في الموسم: عربيّ/إنجليزيّ شائع) → crop_id لبطاقة المحصول.
# صدق: الاسم غير المعروف يُعاد None فيتدهور المستدعي إلى المنطق العامّ (لا تخمين).
_CROP_ALIASES: dict[str, str] = {
    "قمح": "wheat",
    "شعير": "barley",
    "دخن": "millet",
    "ذرة رفيعة": "sorghum",
    "ذرة": "sorghum",
    "sorghum": "sorghum",
    "فاصوليا": "common_bean",
    "فاصولياء": "common_bean",
    "common bean": "common_bean",
    "bean": "common_bean",
    "فول": "faba_bean",
    "باقلاء": "faba_bean",
    "faba bean": "faba_bean",
    "faba": "faba_bean",
    "عدس": "lentil",
    "lentil": "lentil",
    "حلبة": "fenugreek",
    "fenugreek": "fenugreek",
    "بازلاء": "pea",
    "عتر": "pea",
    "pea": "pea",
    "فول سوداني": "peanut",
    "فول السوداني": "peanut",
    "peanut": "peanut",
    "groundnut": "peanut",
}


def resolve_crop_id(crop: str | None) -> str | None:
    """يحوّل اسم محصول (عربيّ/إنجليزيّ) إلى crop_id لبطاقة موجودة، أو None إن جُهِل.

    يجرّب التطابق المباشر مع crop_id أوّلاً (بطاقة موجودة)، ثمّ جدول المرادفات.
    """
    if not crop:
        return None
    raw = crop.strip()
    key = raw.lower()
    # crop_id مباشر (بطاقة موجودة)
    if load_crop_card(key) is not None:
        return key
    return _CROP_ALIASES.get(raw) or _CROP_ALIASES.get(key)


def _stages(crop_id: str | None) -> list[dict]:
    card = load_crop_card(crop_id) if crop_id else None
    if card is None:
        return []
    return list(card.get("phenology", {}).get("stages", []))


def current_stage(crop_id: str | None, days_since_sowing: int | None) -> dict | None:
    """المرحلة الطوريّة الحاليّة (dict من phenology.stages) لعمر المحصول — أو None.

    None حين: لا crop_id/عمر، أو لا كتلة phenology، أو تجاوز العمر آخر مرحلة
    (ما بعد دورة المحصول — صدق: لا مرحلة مُلفَّقة).
    """
    if crop_id is None or days_since_sowing is None:
        return None
    stages = _stages(crop_id)
    for st in stages:
        if st["day_start"] <= days_since_sowing < st["day_end"]:
            return st
    return None


def stage_kc(crop_id: str | None, days_since_sowing: int | None) -> float | None:
    """معامل المحصول Kc الطوريّ (FAO-56 kc_for_age) لعمر المحصول — أو None إن جُهِل.

    يستخدم كتلة kc من بطاقة المحصول (منحنى FAO-56 الرباعيّ) — أدقّ من Kc ثابت.
    """
    if crop_id is None or days_since_sowing is None:
        return None
    card = load_crop_card(crop_id)
    kc = (card or {}).get("kc")
    if not kc:
        return None
    sal = (card or {}).get("salinity", {})
    profile = CropKcProfile(
        crop_id=crop_id,
        kc_initial=kc.get("initial", 0.3),
        kc_mid=kc.get("mid", 1.0),
        kc_end=kc.get("end", 0.4),
        stage_days=kc.get("stage_days", [15, 25, 50, 30]),
        salt_tolerance_ece=sal.get("threshold_ece_ds_m", 4.0),
        salt_slope_pct=sal.get("slope_pct_per_ds_m", 0.0),
    )
    val, _ = kc_for_age(profile, days_since_sowing)
    return round(val, 2)


def is_reproductive_stage(crop_id: str | None, days_since_sowing: int | None) -> bool:
    """هل المحصول في الطور التكاثريّ (التزهير/تكوين الثمار = مرحلة 'mid')؟

    الطور الأكثر حساسيّة للإجهاد الحراريّ/المائيّ — يُستخدَم لتصعيد التنبيهات.
    """
    st = current_stage(crop_id, days_since_sowing)
    return bool(st and st.get("stage") == "mid")


def season_timeline(
    crop_id: str | None, sowing_date: date | None, today: date | None = None
) -> list[dict]:
    """خطّ زمن مراحل الموسم: كلّ مرحلة بتاريخَي بداية/نهاية مطلقَين + حالة + إجراء.

    status: past (انقضت) / current (جارية) / upcoming (قادمة). يُرجع قائمة فارغة
    إن غاب crop_id/تاريخ البذار/كتلة phenology (صدق: لا خطّ زمن مُلفَّق).
    """
    if crop_id is None or sowing_date is None:
        return []
    stages = _stages(crop_id)
    if not stages:
        return []
    ref = today or date.today()
    das = (ref - sowing_date).days
    out: list[dict] = []
    for st in stages:
        start = sowing_date + timedelta(days=st["day_start"])
        end = sowing_date + timedelta(days=st["day_end"])
        if das >= st["day_end"]:
            status = "past"
        elif das >= st["day_start"]:
            status = "current"
        else:
            status = "upcoming"
        out.append(
            {
                "stage": st["stage"],
                "name_ar": st["name_ar"],
                "day_start": st["day_start"],
                "day_end": st["day_end"],
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
                "kc": st.get("kc"),
                "key_action_ar": st.get("key_action_ar"),
                "status": status,
            }
        )
    return out

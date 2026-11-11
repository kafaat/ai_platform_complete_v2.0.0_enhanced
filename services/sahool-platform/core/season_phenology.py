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

import re
from datetime import date, timedelta
from functools import lru_cache

from core.crop_cards.loader import list_crop_cards, load_crop_card
from core.engines.fao56 import CropKcProfile, kc_for_age

# اسم المحصول (كما يخزَّن في الموسم: عربيّ/إنجليزيّ شائع) → crop_id لبطاقة المحصول.
# صدق: الاسم غير المعروف يُعاد None فيتدهور المستدعي إلى المنطق العامّ (لا تخمين).
#
# «ذرة» — قرار واحد موثَّق لكلّ المنصّة: في الاستعمال اليمنيّ «ذرة» مفردةً تعني الذرة
# الرفيعة (sorghum)، أمّا الذرة الشاميّة (maize) فتُسمّى «ذرة شامية/صفراء». كلّ محلِّل محصول
# آخر يمرّ بـ resolve_crop_id فلا يعود «ذرة» → maize في مكان و→ sorghum في آخر.
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
    # المفتاح القديم لجدول Kc الموازي المحذوف (water_balance) — يبقى مقبولاً كمدخَل.
    "dates": "date_palm",
    "date palm": "date_palm",
}


# التشكيل (الحركات/الشدّة/السكون/الألف الخنجريّة) والتطويل لا يغيّران الاسم.
_TASHKEEL = re.compile("[\u064b-\u0652\u0670\u0640]")
_PAREN = re.compile(r"\([^)]*\)")


def normalize_crop_name(text: str | None) -> str:
    """تطبيع اسم محصول للمطابقة: بلا تشكيل، أحرف صغيرة، فراغات موحّدة، بلا «ال» التعريف.

    «الذرة الشاميّة» و«ذرة شامية» و«ذرة_شامية» تتطابق؛ لا يُخمَّن ما وراء ذلك.
    """
    if not text:
        return ""
    t = _TASHKEEL.sub("", str(text)).strip().lower()
    t = re.sub(r"[_\s]+", " ", t)
    words = [w[2:] if w.startswith("ال") and len(w) >= 4 else w for w in t.split(" ")]
    return " ".join(w for w in words if w)


@lru_cache(maxsize=1)
def _card_name_index() -> dict[str, str]:
    """فهرس الأسماء → crop_id من البطاقات نفسها (name_ar · name_en · aliases · crop_id).

    يُفهرَس الاسم **خارج** الأقواس فقط (ما بين القوسين مؤهِّلات مثل «grain»/«table» لا
    أسماء)؛ المرادفات الصريحة تُعلَن في ``aliases:`` بالبطاقة. اسمٌ تدّعيه بطاقتان يُسقَط
    (ملتبس ⇒ None، لا اختيار اعتباطيّ).
    """
    claims: dict[str, set[str]] = {}
    for crop_id in list_crop_cards():
        card = load_crop_card(crop_id) or {}
        names: list[str] = [crop_id.replace("_", " ")]
        for field in ("name_ar", "name_en"):
            value = card.get(field)
            if isinstance(value, str):
                names.extend(part for part in _PAREN.sub(" ", value).split("/"))
        aliases = card.get("aliases")
        if isinstance(aliases, list):
            names.extend(a for a in aliases if isinstance(a, str))
        for name in names:
            key = normalize_crop_name(name)
            if key:
                claims.setdefault(key, set()).add(crop_id)
    return {key: next(iter(ids)) for key, ids in claims.items() if len(ids) == 1}


_NORMALIZED_ALIASES: dict[str, str] = {normalize_crop_name(k): v for k, v in _CROP_ALIASES.items()}


def resolve_crop_id(crop: str | None) -> str | None:
    """يحوّل اسم محصول (عربيّ/إنجليزيّ) إلى crop_id لبطاقة موجودة، أو None إن جُهِل.

    الترتيب: crop_id مباشر (بطاقة موجودة) ← جدول المرادفات أعلاه ← أسماء البطاقات
    ومرادفاتها المُعلَنة (``aliases:``). اسم عامّ مثل «خضروات» يبقى None (لا تخمين).
    """
    if not crop:
        return None
    raw = crop.strip()
    key = raw.lower()
    # crop_id مباشر (بطاقة موجودة)
    if load_crop_card(key) is not None:
        return key
    direct = _CROP_ALIASES.get(raw) or _CROP_ALIASES.get(key)
    if direct:
        return direct
    norm = normalize_crop_name(raw)
    if not norm:
        return None
    return _NORMALIZED_ALIASES.get(norm) or _card_name_index().get(norm)


def is_perennial(crop: str | None) -> bool:
    """هل المحصول مُعمِّر بحسب بطاقته (``life_form: perennial``)؟ مجهول ⇒ False."""
    crop_id = resolve_crop_id(crop)
    if crop_id is None:
        return False
    return (load_crop_card(crop_id) or {}).get("life_form") == "perennial"


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


def crop_kc_profile(crop_id: str | None) -> CropKcProfile | None:
    """يبني :class:`CropKcProfile` (منحنى FAO-56 الرباعيّ + تحمّل الملوحة) من بطاقة المحصول.

    مصدر واحد للحقيقة لبناء البروفايل من البطاقة (يُستدعى من ``stage_kc`` ومن نقطة ETc المزدوج).
    صدق: بطاقة مفقودة أو بلا كتلة ``kc`` ⇒ ``None`` (المستدعي يتدهور بصدق، لا بروفايل مُلفَّق).
    """
    if crop_id is None:
        return None
    card = load_crop_card(crop_id)
    kc = (card or {}).get("kc")
    if not kc:
        return None
    sal = (card or {}).get("salinity", {})
    return CropKcProfile(
        crop_id=crop_id,
        kc_initial=kc.get("initial", 0.3),
        kc_mid=kc.get("mid", 1.0),
        kc_end=kc.get("end", 0.4),
        stage_days=kc.get("stage_days", [15, 25, 50, 30]),
        salt_tolerance_ece=sal.get("threshold_ece_ds_m", 4.0),
        salt_slope_pct=sal.get("slope_pct_per_ds_m", 0.0),
    )


# منحنى Kc عامّ (initial/development/mid/late) **للمحاصيل بلا بطاقة فقط** — المصدر الوحيد
# لهذا الاحتياطيّ (PARALLEL-TAW-AND-KC-TABLES-DISAGREE-01): كانت أربع نسخ منه متفرّقة
# (water_balance · season_simulation · weather_advice · routers/crop_twin) وإحداها تخالف
# الباقي (0.75/0.50 بدل 0.8/0.6). تقدير عامّ موسوم «غير مُعرّف» عند المستهلك — لا يُنسَب لمحصول.
GENERIC_STAGE_KC: dict[str, float] = {"initial": 0.4, "development": 0.8, "mid": 1.1, "late": 0.6}


def stage_kc_map(crop_id: str | None) -> dict[str, float] | None:
    """Kc لكلّ مرحلة مُسمّاة من بطاقة المحصول (المصدر الوحيد لـKc) — أو ``None`` بلا بطاقة.

    الإسقاط من منحنى FAO-56 الرباعيّ (Kc_ini, Kc_mid, Kc_end) إلى أربع مراحل مُسمّاة —
    كلّ مرحلة بمتوسّط المنحنى عليها (FAO-56 Fig.25/Eq.66: الصعود والهبوط خطّيّان):
      initial = Kc_ini · development = (Kc_ini + Kc_mid)/2 (منتصف الصعود الخطّيّ)
      mid = Kc_mid · late = (Kc_mid + Kc_end)/2 (منتصف الهبوط الخطّيّ).
    G1: كان late = Kc_end لكامل المرحلة ⇒ قمح يوم 92 يأخذ 0.40 بدل ~1.10 (−64% ماء).
    Kc_end قيمة يوم الحصاد فقط. المستهلك الذي يعرف عمر المحصول يستعمل ``stage_kc``
    (المنحنى اليوميّ) لا هذا الإسقاط المرحليّ.
    صدق: لا قيمة مرحلة تُكتَب يدويّاً في أيّ مستهلك — كلّها من البطاقة عبر هذا الإسقاط.
    """
    profile = crop_kc_profile(crop_id)
    if profile is None:
        return None
    ini, mid, end = profile.kc_initial, profile.kc_mid, profile.kc_end
    return {
        "initial": ini,
        "development": round((ini + mid) / 2.0, 3),
        "mid": mid,
        "late": round((mid + end) / 2.0, 3),
    }


def stage_kc(crop_id: str | None, days_since_sowing: int | None) -> float | None:
    """معامل المحصول Kc الطوريّ (FAO-56 kc_for_age) لعمر المحصول — أو None إن جُهِل.

    يستخدم كتلة kc من بطاقة المحصول (منحنى FAO-56 الرباعيّ): ini ثابت · dev خطّيّ
    ini→mid · mid ثابت · late خطّيّ mid→end. العمر خارج الموسم يُقصّ: قبل البذار ⇒
    Kc_ini، بعد الحصاد ⇒ Kc_end (لا استقراء خارج المنحنى).
    """
    if days_since_sowing is None:
        return None
    profile = crop_kc_profile(crop_id)
    if profile is None:
        return None
    day = min(max(0, int(days_since_sowing)), profile.total_season_days)
    val, _ = kc_for_age(profile, day)
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

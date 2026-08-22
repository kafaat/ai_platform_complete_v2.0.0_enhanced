"""
sahool_core.crop_cards.loader
==============================
مُحمّل بطاقات المحاصيل + متحقّق من مطابقة القالب المعياري.

كل بطاقة محصول تتبع القالب (_TEMPLATE.yaml): محايدة الموقع، فيزياء
وفسيولوجيا فقط، بمصادر موثّقة (FAO-56, Maas-Hoffman, ECOCROP, NGRC).
المعايرة والإنتاج ممنوعة في البطاقة (مخرجات districts/tenant).
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

CARDS_DIR = Path(__file__).parent


def _safe_id(card_id: str) -> str | None:
    """يعقّم معرّف البطاقة لمنع path traversal.
    يسمح فقط بحروف/أرقام/شرطة سفلية — يرفض المسارات الصاعدة والفواصل."""
    if not card_id or not re.fullmatch(r"[A-Za-z0-9_]+", card_id):
        return None
    return card_id


# الحقول الإلزامية في كل بطاقة (المعيار المتّبع)
REQUIRED_TOP = {
    "crop_id",
    "name_ar",
    "name_en",
    "crop_family",
    "kc",
    "salinity",
    "thermal",
    "governing",
    "modifying",
}
REQUIRED_KC = {"initial", "mid", "end", "stage_days", "source"}
REQUIRED_SALINITY = {"threshold_ece_ds_m", "slope_pct_per_ds_m", "source"}
# مراحل النمو (phenology) — كتلة اختياريّة محايدة الموقع. تُتحقَّق فقط إن وُجدت.
REQUIRED_PHENOLOGY_STAGE = {"stage", "name_ar", "day_start", "day_end"}
# الطلب الغذائيّ لكلّ مرحلة (nutrient_demand) — كتلة اختياريّة داخل كلّ مرحلة:
# كسر امتصاص كلّ عنصر خلال المرحلة من الإجماليّ الموسميّ (وليس تراكميّاً)، بمصدر موثّق.
REQUIRED_STAGE_NUTRIENT = {"n_fraction", "p_fraction", "k_fraction", "source"}
NUTRIENT_SUM_TOLERANCE = 0.02  # كسور العنصر عبر المراحل يجب أن تجمع إلى 1.0 ± التفاوت
# سلسلة اشتقاق الكسور (nutrient_demand_provenance على مستوى phenology) — إلزاميّة
# متى وُجدت منحنيات طلب: مرجع أوّليّ + اشتقاق قابل لإعادة البناء + تعيين مراحل
# V/R→مراحل البطاقة + تصريح تقريب صريح. تحقّق بنيويّ — لا يجمّد القيم العلميّة.
REQUIRED_NUTRIENT_PROVENANCE = {
    "primary_reference",
    "derivation",
    "stage_mapping",
    "approximation",
}
# حقول ممنوعة (تكسر حياد الموقع)
FORBIDDEN = {"zone_factor", "yield", "expected_yield", "calibration", "region", "farm", "tenant"}


def _validate_nutrient_demand(stages: list, errors: list) -> None:
    """يتحقّق من منحنيات الطلب الغذائيّ لكلّ مرحلة (إن وُجدت) — قاعدة الكلّ أو لا شيء.

    إن حملت أيّ مرحلة `nutrient_demand` وجب أن تحمله كلّ المراحل (وإلاّ انحرفت
    الجموع)، وكلّ كتلة تلزمها REQUIRED_STAGE_NUTRIENT وكسور في [0, 1]، وتجمع
    كسور كلّ عنصر عبر المراحل إلى 1.0 ± NUTRIENT_SUM_TOLERANCE. البطاقات
    القديمة (بلا nutrient_demand إطلاقاً) لا يتغيّر سلوكها.
    """
    carrying = [
        (i, st["nutrient_demand"])
        for i, st in enumerate(stages)
        if isinstance(st, dict) and st.get("nutrient_demand") is not None
    ]
    if not carrying:
        return
    if len(carrying) != len(stages):
        missing = [
            st.get("stage", f"[{i}]")
            for i, st in enumerate(stages)
            if not (isinstance(st, dict) and st.get("nutrient_demand") is not None)
        ]
        errors.append(
            f"nutrient_demand جزئيّ: مراحل بلا منحنى طلب: {missing} (القاعدة: الكلّ أو لا شيء)"
        )
    sums = {"n_fraction": 0.0, "p_fraction": 0.0, "k_fraction": 0.0}
    for i, nd in carrying:
        if not isinstance(nd, dict):
            errors.append(f"مرحلة[{i}]: nutrient_demand ليس كتلة")
            continue
        miss = REQUIRED_STAGE_NUTRIENT - set(nd.keys())
        if miss:
            errors.append(f"مرحلة[{i}]: nutrient_demand ناقص: {miss}")
            continue
        for k in sums:
            v = nd[k]
            if not isinstance(v, (int, float)) or not 0.0 <= v <= 1.0:
                errors.append(f"مرحلة[{i}]: {k} خارج [0, 1]: {v!r}")
            else:
                sums[k] += v
    for k, total in sums.items():
        if abs(total - 1.0) > NUTRIENT_SUM_TOLERANCE:
            errors.append(
                f"مجموع {k} عبر المراحل = {total:.4f} (المطلوب 1.0 ± {NUTRIENT_SUM_TOLERANCE})"
            )


def _validate_nutrient_provenance(ph: dict, stages: list, errors: list) -> None:
    """يلزم سلسلة اشتقاق موثّقة (nutrient_demand_provenance) متى حملت المراحل منحنيات طلب.

    «approximate» بلا سلسلة قابلة لإعادة البناء لا يكفي: كلّ كسور طلبٍ غذائيّ يلزمها
    مرجع أوّليّ ومنهج اشتقاق وتعيين مراحل V/R→مراحل البطاقة وتصريح approximation
    صريح — حتى تتبعها الذرة والقمح والذرة الرفيعة والطماطم والبطاطس بالمنهج نفسه.
    تحقّق بنيويّ فحسب: لا يجمّد القيم العلميّة، بل يمنع كسراً بلا مصدر قابل للتتبّع.
    """
    if not any(isinstance(st, dict) and st.get("nutrient_demand") is not None for st in stages):
        return
    prov = ph.get("nutrient_demand_provenance")
    if not isinstance(prov, dict):
        errors.append("nutrient_demand بلا كتلة nutrient_demand_provenance على مستوى phenology")
        return
    miss = REQUIRED_NUTRIENT_PROVENANCE - set(prov.keys())
    if miss:
        errors.append(f"nutrient_demand_provenance ناقصة: {miss}")
        return
    for k in ("primary_reference", "derivation", "stage_mapping"):
        if not isinstance(prov[k], str) or not prov[k].strip():
            errors.append(f"nutrient_demand_provenance.{k} يجب أن يكون نصّاً غير فارغ")
    if prov["approximation"] is not True:
        errors.append("nutrient_demand_provenance.approximation يجب أن يكون true صراحةً")


def _validate_phenology(card: dict, errors: list) -> None:
    """يتحقّق من كتلة مراحل النمو (إن وُجدت) — اختياريّة لكلّ البطاقات.

    لبطاقة المحصول: stages قائمة مراحل مُرتّبة بمصدر، كلّ مرحلة بمفاتيح
    REQUIRED_PHENOLOGY_STAGE وحدود يوميّة متّسقة (day_start < day_end، وتسلسل غير متراجع).
    لا تُغيّر سلوك البطاقات القديمة (التي بلا phenology).
    """
    ph = card.get("phenology")
    if ph is None:
        return
    if "source" not in ph:
        errors.append("phenology بلا مصدر موثّق")
    stages = ph.get("stages")
    if not isinstance(stages, list) or not stages:
        errors.append("phenology بلا قائمة stages")
        return
    prev_end = None
    for i, st in enumerate(stages):
        miss = REQUIRED_PHENOLOGY_STAGE - set(st.keys())
        if miss:
            errors.append(f"مرحلة[{i}] ينقصها: {miss}")
            continue
        if st["day_start"] >= st["day_end"]:
            errors.append(f"مرحلة '{st['stage']}': day_start ≥ day_end")
        if prev_end is not None and st["day_start"] < prev_end:
            errors.append(f"مرحلة '{st['stage']}': تتداخل مع السابقة (تسلسل متراجع)")
        prev_end = st["day_end"]
    _validate_nutrient_demand(stages, errors)  # منحنيات الطلب الغذائيّ (اختياريّة — كلّ أو لا شيء)
    _validate_nutrient_provenance(ph, stages, errors)  # سلسلة الاشتقاق إلزاميّة متى وُجدت المنحنيات


def load_crop_card(crop_id: str) -> dict | None:
    """يحمّل بطاقة محصول بمعرّفها (مع حماية من path traversal)."""
    safe = _safe_id(crop_id)
    if safe is None:
        return None
    path = CARDS_DIR / f"{safe}.yaml"
    if not path.exists():
        return None
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def list_crop_cards() -> list[str]:
    """يُرجع معرّفات كل البطاقات المتاحة (عدا القالب)."""
    return sorted(p.stem for p in CARDS_DIR.glob("*.yaml") if not p.stem.startswith("_"))


def validate_crop_card(card: dict) -> dict:
    """يتحقّق أن البطاقة تتبع القالب المعياري وتحترم حياد الموقع."""
    errors = []
    missing = REQUIRED_TOP - set(card.keys())
    if missing:
        errors.append(f"حقول مفقودة: {missing}")
    if "kc" in card and (REQUIRED_KC - set(card["kc"].keys())):
        errors.append(f"kc ناقص: {REQUIRED_KC - set(card['kc'].keys())}")
    if "salinity" in card and (REQUIRED_SALINITY - set(card["salinity"].keys())):
        errors.append(f"salinity ناقص: {REQUIRED_SALINITY - set(card['salinity'].keys())}")
    # حياد الموقع: لا حقول معايرة/إنتاج/منطقة
    forbidden_found = FORBIDDEN & set(card.keys())
    if forbidden_found:
        errors.append(f"حقول تكسر حياد الموقع: {forbidden_found}")
    # كل كتلة فيزيائية يجب أن تذكر مصدرها
    for block in ("kc", "salinity"):
        if block in card and "source" not in card[block]:
            errors.append(f"{block} بلا مصدر موثّق")
    _validate_phenology(card, errors)  # مراحل النمو (اختياريّة — تُتحقَّق إن وُجدت)
    return {"valid": len(errors) == 0, "errors": errors, "crop_id": card.get("crop_id", "?")}


def growth_stages(crop_id: str) -> list[dict]:
    """يُرجع مراحل نمو المحصول (phenology.stages) أو قائمة فارغة إن لم تُعرَّف.

    مراحل مُهيكَلة محايدة الموقع (بداية/نهاية باليوم + Kc + إجراء مفتاحيّ) — أدقّ من
    التقدير العامّ في main._STAGE_DAY_BOUNDS؛ تُغذّي «بطاقة المحصول» وتوقيت التوصيات.
    """
    card = load_crop_card(crop_id)
    if card is None:
        return []
    return list(card.get("phenology", {}).get("stages", []))


def stage_nutrient_demand(crop_id: str) -> list[dict]:
    """يُرجع منحنى الطلب الغذائيّ لكلّ مرحلة: [{stage, day_start, day_end, n/p/k_fraction, source}].

    الكسور **خلال المرحلة** من الإجماليّ الموسميّ (تجمع إلى 1.0 لكلّ عنصر) — كسورٌ بلا
    وحدات فحسب. هذه الوحدة **لا** تُحوّلها إلى kg/ha: التحويل (بضرب الكسر في احتياجٍ
    موسميّ موثّق) مسؤوليّة المُستدعي خارج loader، ولا حقل في البطاقة يُثبته هنا.
    قائمة فارغة إن لم تُعرَّف المنحنيات بعد.
    """
    out = []
    for st in growth_stages(crop_id):
        nd = st.get("nutrient_demand")
        if nd:
            out.append(
                {
                    "stage": st["stage"],
                    "day_start": st["day_start"],
                    "day_end": st["day_end"],
                    "n_fraction": nd["n_fraction"],
                    "p_fraction": nd["p_fraction"],
                    "k_fraction": nd["k_fraction"],
                    "source": nd["source"],
                }
            )
    return out


# ════════════════════════════════════════════════════════════
# بطاقات الأصناف (Varieties) — مستوى أدقّ من المحصول
# ════════════════════════════════════════════════════════════
VARIETIES_DIR = CARDS_DIR / "varieties"

REQUIRED_VARIETY = {
    "variety_id",
    "parent_crop_id",
    "name_ar",
    "name_en",
    "passport",
    "distinctness",
    "variety_traits",
}


def load_variety_card(variety_id: str) -> dict | None:
    """يحمّل بطاقة صنف بمعرّفها (مع حماية من path traversal)."""
    safe = _safe_id(variety_id)
    if safe is None:
        return None
    path = VARIETIES_DIR / f"{safe}.yaml"
    if not path.exists():
        return None
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def list_variety_cards() -> list[str]:
    """يُرجع معرّفات كل الأصناف المتاحة."""
    if not VARIETIES_DIR.exists():
        return []
    return sorted(p.stem for p in VARIETIES_DIR.glob("*.yaml") if not p.stem.startswith("_"))


def varieties_of_crop(crop_id: str) -> list[str]:
    """يُرجع أصناف محصول معيّن (ربط الصنف بمحصوله الأمّ)."""
    out = []
    for vid in list_variety_cards():
        v = load_variety_card(vid)
        if v and v.get("parent_crop_id") == crop_id:
            out.append(vid)
    return out


def validate_variety_card(card: dict) -> dict:
    """يتحقّق أن بطاقة الصنف تتبع UPOV/Bioversity وتربط بمحصول موجود."""
    errors = []
    missing = REQUIRED_VARIETY - set(card.keys())
    if missing:
        errors.append(f"حقول مفقودة: {missing}")
    # يجب أن يربط بمحصول أمّ موجود فعلاً
    parent = card.get("parent_crop_id")
    if parent and load_crop_card(parent) is None:
        errors.append(f"المحصول الأمّ '{parent}' غير موجود في البطاقات")
    # passport يجب أن يحوي المصدر والمنشأ (UPOV/Bioversity)
    if "passport" in card:
        if "origin_type" not in card["passport"]:
            errors.append("passport بلا origin_type (landrace/improved/introduced)")
        if "source_ar" not in card["passport"]:
            errors.append("passport بلا مصدر موثّق")
    # حياد الموقع
    forbidden = FORBIDDEN & set(card.keys())
    if forbidden:
        errors.append(f"حقول تكسر حياد الموقع: {forbidden}")
    # توقيت مراحل النمو للصنف (اختياريّ): إن وُجد فلا بدّ من مصدر + نضج موثّق.
    ph = card.get("phenology")
    if ph is not None:
        if "source" not in ph:
            errors.append("phenology بلا مصدر موثّق")
        if "days_to_maturity" not in ph:
            errors.append("phenology بلا days_to_maturity")
    return {"valid": len(errors) == 0, "errors": errors, "variety_id": card.get("variety_id", "?")}

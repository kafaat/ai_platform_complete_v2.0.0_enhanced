"""
api/crop_rotation.py — إرشاد الدورة الزراعيّة (تعاقب المحاصيل)

جانب جديد يكمّل المنظومة: التسميد يعالج النقص الحالي، لكن الدورة الزراعيّة
حلّ **وقائي بنيوي** لخصوبة التربة وكسر دورات الآفات — توصية رسميّة من هيئة
البحوث الزراعيّة اليمنيّة.

المبادئ (من أدبيّات الزراعة + سياق اليمن):
  • تعاقب البقوليات (تثبّت النيتروجين الجوي + تُطلق الفوسفور المرتبط) مع
    الحبوب → حلّ طبيعي لنقص N والفوسفور المثبّت في التربة القلويّة اليمنيّة
  • تجنّب تعاقب محاصيل متشابهة الاحتياج/العائلة (تستنزف نفس العناصر، تراكم آفات)
  • تنويع عميق/سطحي الجذور، وشتوي/صيفي
  • التسميد الأخضر والتغطية ضدّ التعرية

⚠ إرشاد عامّ من أدبيّات موثّقة — يوجّه التخطيط، لا يفرض. القرار للمزارع
حسب سوقه وأرضه (human-in-the-loop).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class CropFamily(str, Enum):
    GRASS = "grass"  # نجيليّة: قمح، شعير، ذرة، دخن — مستهلكة للنيتروجين
    LEGUME = "legume"  # بقوليّة: عدس، فول، لوبيا — مثبّتة للنيتروجين
    SOLANACEAE = "solanaceae"  # باذنجانيّة: طماطم، بطاطس، فلفل
    CUCURBIT = "cucurbit"  # قرعيّة: بطيخ، خيار
    ALLIUM = "allium"  # بصليّة: بصل، ثوم
    FORAGE = "forage"  # علفيّة: برسيم (بقولي علفي)


# تصنيف المحاصيل اليمنيّة الشائعة → عائلة + خصائص الدورة
_CROP_INFO: dict[str, dict] = {
    "wheat": {
        "name_ar": "القمح",
        "family": CropFamily.GRASS,
        "root": "سطحي",
        "n_effect": "مستهلك",
        "season": "شتوي",
    },
    "barley": {
        "name_ar": "الشعير",
        "family": CropFamily.GRASS,
        "root": "سطحي",
        "n_effect": "مستهلك",
        "season": "شتوي",
    },
    "maize": {
        "name_ar": "الذرة الشاميّة",
        "family": CropFamily.GRASS,
        "root": "متوسّط",
        "n_effect": "مستهلك بشدّة",
        "season": "صيفي",
    },
    "sorghum": {
        "name_ar": "الذرة الرفيعة",
        "family": CropFamily.GRASS,
        "root": "عميق",
        "n_effect": "مستهلك",
        "season": "صيفي",
    },
    "millet": {
        "name_ar": "الدخن",
        "family": CropFamily.GRASS,
        "root": "متوسّط",
        "n_effect": "مستهلك",
        "season": "صيفي",
    },
    "lentil": {
        "name_ar": "العدس",
        "family": CropFamily.LEGUME,
        "root": "متوسّط",
        "n_effect": "مثبّت",
        "season": "شتوي",
    },
    "faba_bean": {
        "name_ar": "الفول",
        "family": CropFamily.LEGUME,
        "root": "عميق",
        "n_effect": "مثبّت",
        "season": "شتوي",
    },
    "cowpea": {
        "name_ar": "اللوبيا",
        "family": CropFamily.LEGUME,
        "root": "عميق",
        "n_effect": "مثبّت",
        "season": "صيفي",
    },
    "alfalfa": {
        "name_ar": "البرسيم",
        "family": CropFamily.FORAGE,
        "root": "عميق جدّاً",
        "n_effect": "مثبّت",
        "season": "دائم",
    },
    "potato": {
        "name_ar": "البطاطس",
        "family": CropFamily.SOLANACEAE,
        "root": "سطحي",
        "n_effect": "مستهلك",
        "season": "متعدّد",
    },
    "tomato": {
        "name_ar": "الطماطم",
        "family": CropFamily.SOLANACEAE,
        "root": "متوسّط",
        "n_effect": "مستهلك",
        "season": "متعدّد",
    },
    "onion": {
        "name_ar": "البصل",
        "family": CropFamily.ALLIUM,
        "root": "سطحي",
        "n_effect": "مستهلك",
        "season": "شتوي",
    },
}

_ALIASES = {
    "قمح": "wheat",
    "شعير": "barley",
    "ذرة شامية": "maize",
    "ذرة شاميّة": "maize",
    "ذرة رفيعة": "sorghum",
    "دخن": "millet",
    "عدس": "lentil",
    "فول": "faba_bean",
    "لوبيا": "cowpea",
    "برسيم": "alfalfa",
    "بطاطس": "potato",
    "طماطم": "tomato",
    "بصل": "onion",
}


def _resolve(crop: str) -> str | None:
    c = crop.strip().lower()
    if c in _CROP_INFO:
        return c
    return _ALIASES.get(crop.strip())


@dataclass
class RotationAdvice:
    previous_crop: str
    candidate_crop: str
    rating: str  # good / acceptable / avoid
    rating_ar: str
    reasons_ar: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "previous_crop": self.previous_crop,
            "candidate_crop": self.candidate_crop,
            "rating": self.rating,
            "rating_ar": self.rating_ar,
            "reasons_ar": self.reasons_ar,
        }


def evaluate_rotation(previous: str, candidate: str) -> dict:
    """يقيّم تعاقب محصولَين: هل candidate خيار جيّد بعد previous؟"""
    pk, ck = _resolve(previous), _resolve(candidate)
    if not pk or not ck:
        unknown = previous if not pk else candidate
        return {"supported": False, "message_ar": f"المحصول «{unknown}» غير معروف في جدول الدورة."}

    p, c = _CROP_INFO[pk], _CROP_INFO[ck]
    reasons: list[str] = []
    score = 0

    # نفس العائلة = سيّئ (نفس الآفات + نفس استنزاف العناصر) — عقوبة غالبة
    same_family = p["family"] == c["family"]
    if same_family:
        reasons.append(f"⚠ نفس العائلة ({p['family'].value}) — تراكم آفات واستنزاف متشابه. تجنّب.")
        score -= 4
    else:
        reasons.append("عائلتان مختلفتان — يكسر دورات الآفات. جيّد.")
        score += 1

    # بقولي بعد نجيلي (أو العكس) = ممتاز
    if p["family"] == CropFamily.GRASS and c["family"] in (CropFamily.LEGUME, CropFamily.FORAGE):
        reasons.append(
            "✓ بقولي بعد حبوب: يثبّت النيتروجين ويطلق الفوسفور المرتبط — مثالي لتربة اليمن القلويّة."
        )
        score += 3
    elif p["family"] in (CropFamily.LEGUME, CropFamily.FORAGE) and c["family"] == CropFamily.GRASS:
        reasons.append("✓ حبوب بعد بقولي: تستفيد من النيتروجين المتبقّي — يقلّل حاجة التسميد.")
        score += 3

    # تعاقب جذور مختلفة العمق = جيّد
    if p["root"] != c["root"]:
        reasons.append(f"تعاقب جذور ({p['root']} ← {c['root']}): يستغلّ أعماقاً مختلفة من التربة.")
        score += 1

    # تعاقب موسمي (شتوي ↔ صيفي) منطقي
    if p["season"] != c["season"] and "دائم" not in (p["season"], c["season"]):
        reasons.append(f"تعاقب موسمي ({p['season']} ← {c['season']}): استغلال جيّد للأرض.")
        score += 1

    if same_family:
        rating, rating_ar = "avoid", "يُفضّل تجنّبه ✗"
    elif score >= 3:
        rating, rating_ar = "good", "تعاقب جيّد ✓"
    elif score >= 0:
        rating, rating_ar = "acceptable", "مقبول"
    else:
        rating, rating_ar = "avoid", "يُفضّل تجنّبه ✗"

    return RotationAdvice(p["name_ar"], c["name_ar"], rating, rating_ar, reasons).to_dict() | {
        "supported": True
    }


def suggest_next_crop(previous: str) -> dict:
    """يقترح أفضل المحاصيل التالية بعد محصول معيّن (مرتّبة)."""
    pk = _resolve(previous)
    if not pk:
        return {"supported": False, "message_ar": f"المحصول «{previous}» غير معروف."}

    candidates = []
    for ck in _CROP_INFO:
        if ck == pk:
            continue
        ev = evaluate_rotation(previous, ck)
        if ev.get("supported"):
            # رتبة عدديّة بسيطة للترتيب
            rank = {"good": 2, "acceptable": 1, "avoid": 0}[ev["rating"]]
            candidates.append((rank, ev))
    candidates.sort(key=lambda x: -x[0])

    return {
        "supported": True,
        "previous_crop": _CROP_INFO[pk]["name_ar"],
        "yemen_note_ar": (
            "في تربة اليمن القلويّة الكلسيّة، إدخال بقولي (عدس/فول/لوبيا) في الدورة "
            "يثبّت النيتروجين ويحرّر الفوسفور المثبّت — يقلّل تكلفة التسميد طبيعيّاً."
        ),
        "ranked": [ev for _, ev in candidates],
        "disclaimer_ar": (
            "إرشاد عامّ من أدبيّات الدورة الزراعيّة. القرار النهائي للمزارع حسب سوقه وأرضه ومياهه."
        ),
    }


def rotation_principles() -> dict:
    """مبادئ الدورة الزراعيّة (للعرض التثقيفي)."""
    return {
        "principles_ar": [
            "تعاقب البقوليات (مثبّتة للنيتروجين) مع الحبوب (مستهلكة له).",
            "تجنّب تعاقب محاصيل من نفس العائلة (تراكم آفات + استنزاف متشابه).",
            "تنويع عمق الجذور (عميق ← سطحي) لاستغلال طبقات التربة.",
            "موازنة شتوي/صيفي للاستفادة القصوى من الأرض.",
            "إدخال التسميد الأخضر والتغطية ضدّ التعرية.",
        ],
        "yemen_context_ar": (
            "هيئة البحوث الزراعيّة اليمنيّة توصي بنظام الدورة الزراعيّة. البقوليات "
            "حلّ مزدوج: تثبّت النيتروجين وتحرّر الفوسفور المثبّت في التربة القلويّة."
        ),
        "supported_crops": [
            {
                "crop": k,
                "name_ar": v["name_ar"],
                "family": v["family"].value,
                "n_effect": v["n_effect"],
                "season": v["season"],
            }
            for k, v in _CROP_INFO.items()
        ],
    }

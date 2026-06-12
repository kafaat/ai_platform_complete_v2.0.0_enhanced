"""core/engines/candidate_generator.py — توليد بدائل زراعيّة موزونة حسب الهدف.

الفكرة (الاستخلاص الصادق الوحيد من مقترح v9→v19): المنصّة توصي **بخيار مفرد**؛
هذا المكوّن يولّد **٢–٣ بدائل مُقيَّمة حسب هدف المزارع** (ربح/أمن غذائي/ترشيد ماء/
صمود جفاف) ثمّ يرتّبها — مع إبقاء **كلّ الخيارات مرئيّة** (استقلاليّة المزارع).

⚠ المبدأ (اتّساقاً مع economic_adaptation + farmer_agency + صدق المصدر):
  • حتميّ بالكامل: أوزان صريحة موثّقة على صفات مُعطاة — لا نموذج، لا تعلّم
  • **لا فبركة**: يأخذ صفات موثّقة كمُدخلات (ملاءمة/تحمّل جفاف/حاجة ماء/كلفة)؛
    الصفة المجهولة تُسهم محايدةً وتُعلَن — لا اختراع رقم
  • **لا حذف**: الخيار غير المناسب يُرتَّب أدنى لكن **يبقى معروضاً** (الوكالة)
  • شفّاف: يُظهر تفكيك الدرجة (كلّ مكوّن + وزنه + إسهامه) ومصدر كلّ صفة
  • **اقتراح لا فرض**: الترتيب توجيه؛ القرار للمزارع

⚠ ليس Candidate Generator بـML من المقترح — مُرتّب حتميّ شفّاف يركّب محرّكات
سهول القائمة (الملاءمة الإقليميّة + تحمّل الجفاف + حسّاسيّة الماء + تكييف القدرة).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class FarmerGoal(str, Enum):
    """هدف المزارع — يحوكم أوزان التقييم (لا يحذف خياراً)."""

    MAX_PROFIT = "max_profit"  # تعظيم الربح
    FOOD_SECURITY = "food_security"  # الأمن الغذائي (محاصيل أساسيّة موثوقة)
    MIN_WATER = "min_water"  # ترشيد الماء
    DROUGHT_RESILIENCE = "drought_resilience"  # الصمود للجفاف

    @property
    def label_ar(self) -> str:
        return {
            "max_profit": "تعظيم الربح",
            "food_security": "الأمن الغذائي",
            "min_water": "ترشيد الماء",
            "drought_resilience": "الصمود للجفاف",
        }[self.value]


_LEVEL = {"low": 0.0, "mid": 0.5, "high": 1.0}


@dataclass
class CropCandidate:
    """خيار محصول بصفاته الموثّقة (تُملأ من محرّكات سهول القائمة)."""

    crop_id: str
    name_ar: str
    is_suited: bool  # من suited_for_zone (ملاءمة إقليميّة موثّقة)
    water_need_level: str = "mid"  # low/mid/high (crop_water_sensitivity)
    upfront_cost_level: str = "mid"  # low/mid/high (economic_adaptation)
    profit_potential_level: str = "unknown"  # low/mid/high/unknown
    is_staple: bool = False  # محصول أساسي (للأمن الغذائي)
    drought_score: float | None = None  # من drought_resilience [0,1] أو None


# أوزان كلّ هدف (شفّافة، تُجمَع إلى 1.0). الملاءمة حاضرة في كلّ هدف كي يبقى
# غير المناسب أدنى دون حذف.
_GOAL_WEIGHTS: dict[FarmerGoal, dict[str, float]] = {
    FarmerGoal.MAX_PROFIT: {
        "profit": 0.55,  # الربح يقود الهدف؛ التكلفة تُسهم باعتدال (لا تطغى)
        "suitability": 0.20,
        "affordability": 0.15,
        "drought": 0.10,
    },
    FarmerGoal.FOOD_SECURITY: {"staple": 0.35, "suitability": 0.30, "drought": 0.25, "water": 0.10},
    FarmerGoal.MIN_WATER: {
        "water": 0.50,
        "suitability": 0.25,
        "drought": 0.15,
        "affordability": 0.10,
    },
    FarmerGoal.DROUGHT_RESILIENCE: {
        "drought": 0.45,
        "water": 0.25,
        "suitability": 0.20,
        "affordability": 0.10,
    },
}


def _components(c: CropCandidate) -> dict[str, tuple[float, str]]:
    """قيم المكوّنات [0,1] + مصدر/ملاحظة كلّ منها (شفافيّة)."""
    water_eff = 1.0 - _LEVEL.get(c.water_need_level, 0.5)  # حاجة أقلّ = أكفأ
    profit = _LEVEL.get(c.profit_potential_level, 0.5)  # unknown → محايد 0.5
    return {
        "suitability": (1.0 if c.is_suited else 0.2, "ملاءمة إقليميّة (suited_for_zone)"),
        "drought": (
            c.drought_score if c.drought_score is not None else 0.5,
            "تحمّل الجفاف (drought_resilience)"
            + ("" if c.drought_score is not None else " — مجهول، محايد"),
        ),
        "water": (water_eff, "كفاءة الماء (حاجة أقلّ أفضل)"),
        "affordability": (1.0 - _LEVEL.get(c.upfront_cost_level, 0.5), "يُسر التكلفة المسبقة"),
        "profit": (
            profit,
            "إمكان الربح" + ("" if c.profit_potential_level != "unknown" else " — مجهول، محايد"),
        ),
        "staple": (1.0 if c.is_staple else 0.4, "محصول أساسي (أمن غذائي)"),
    }


def score_candidate(c: CropCandidate, goal: FarmerGoal) -> dict:
    """يقيّم خياراً حسب الهدف (حتميّ، شفّاف) — يُظهر تفكيك الدرجة ومصادرها."""
    comps = _components(c)
    weights = _GOAL_WEIGHTS[goal]
    breakdown = {}
    total = 0.0
    for key, w in weights.items():
        val, src = comps[key]
        contribution = round(val * w, 4)
        total += contribution
        breakdown[key] = {
            "value": round(val, 3),
            "weight": w,
            "contribution": contribution,
            "source_ar": src,
        }
    flags = []
    if not c.is_suited:
        flags.append("غير مناسب إقليميّاً (معروض للوكالة، مُرتَّب أدنى)")
    if c.drought_score is None:
        flags.append("تحمّل الجفاف مجهول (محايد)")
    if c.profit_potential_level == "unknown":
        flags.append("إمكان الربح مجهول (محايد)")
    return {
        "crop_id": c.crop_id,
        "name_ar": c.name_ar,
        "score": round(total, 4),
        "is_suited": c.is_suited,
        "breakdown": breakdown,
        "flags_ar": flags,
    }


def generate_candidates(candidates: list[CropCandidate], goal: FarmerGoal, top_n: int = 3) -> dict:
    """يولّد بدائل مُقيَّمة مرتّبة حسب الهدف — كلّها مرئيّة، الأعلى مُبرَزة.

    لا حذف: الخيار غير المناسب يُرتَّب أدنى لكن يبقى معروضاً (استقلاليّة المزارع).
    """
    scored = [score_candidate(c, goal) for c in candidates]
    scored.sort(key=lambda s: s["score"], reverse=True)
    for i, s in enumerate(scored):
        s["rank"] = i + 1
        s["highlighted"] = i < top_n  # ضمن الأعلى المُقترَحة
    return {
        "goal": goal.value,
        "goal_ar": goal.label_ar,
        "display_only": True,  # طبقة استرشاد — لا تفرض قراراً
        "total_candidates": len(scored),
        "recommended": scored[0] if scored else None,
        "candidates": scored,  # كلّها (مرتّبة) — لا حذف
        "all_options_visible": True,
        "weights_used": _GOAL_WEIGHTS[goal],
        "agency_note_ar": (
            "ترتيب مقترح حسب هدفك المُعلَن — لا حصر. كلّ الخيارات معروضة (حتى "
            "غير المناسب إقليميّاً)؛ لك أن تختار ما يوافق رؤيتك وظروفك."
        ),
        "honesty_note_ar": (
            "تقييم حتميّ بأوزان صريحة على صفات موثّقة (ملاءمة/تحمّل جفاف/حاجة ماء/"
            "تكلفة). الصفة المجهولة تُسهم محايدةً وتُعلَن — لا اختراع. ليس نموذجاً "
            "يتعلّم؛ يركّب محرّكات سهول القائمة في بدائل شفّافة قابلة للمراجعة."
        ),
    }

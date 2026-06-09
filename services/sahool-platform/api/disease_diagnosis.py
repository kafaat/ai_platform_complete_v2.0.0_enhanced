"""
api/disease_diagnosis.py — تشخيص بقواعد الأعراض (لا تعلّم آلي)

خارطة الطريق: المرحلة ٣، البند ١٦.

المبدأ الحاكم: "rule-based before ML". بدل تشخيص صورة بنموذج (يحتاج بيانات
يمنيّة مُوسومة لا نملكها، ويخاطر بثقة زائفة)، نبني شجرة قواعد شفّافة تربط
الأعراض المرئيّة → مرشّحين مرتّبين من تصنيف scouting_pins، مع شرح كلّ مطابقة.

المخرج صريح: قائمة مرشّحين باحتمال نسبي + خطوة تالية (غالباً: ثبّت بصورة/
مهندس/مختبر). لا يدّعي يقيناً — الاستشعار/الأعراض توجّه، التأكيد بشري.

⚠ هذه قواعد أعراض عامّة من أدبيّات وقاية النبات — ليست تشخيصاً قاطعاً.
كلّ نتيجة تنتهي بتوصية تأكيد (صورة عالية الدقّة / مهندس / مختبر).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Set


# قواعد الأعراض: كلّ قاعدة تربط مجموعة أعراض → كود مرض/آفة/نقص + ثقة أساس
# الأعراض رموز بسيطة يختارها المزارع من قائمة (لا نصّ حرّ — أدقّ للمطابقة)
@dataclass
class SymptomRule:
    issue_code: str
    name_ar: str
    category: str               # disease | pest | nutrient | water_stress
    required_symptoms: Set[str]  # يجب توفّرها كلّها
    supporting_symptoms: Set[str]  # تزيد الثقة
    crops: Set[str]             # المحاصيل التي تنطبق عليها (فارغة = الكلّ)
    base_confidence: float       # 0-1 عند تطابق الأعراض المطلوبة


# قاعدة المعرفة (أعراض → مرشّحين). رموز الأعراض موحّدة.
SYMPTOM_RULES: List[SymptomRule] = [
    SymptomRule(
        "wheat.rust", "صدأ القمح", "disease",
        required_symptoms={"orange_pustules"},
        supporting_symptoms={"leaf_yellowing", "powder_on_touch"},
        crops={"wheat", "barley"}, base_confidence=0.7,
    ),
    SymptomRule(
        "wheat.fe_deficiency", "نقص حديد", "nutrient",
        required_symptoms={"interveinal_chlorosis", "young_leaves_affected"},
        supporting_symptoms={"alkaline_soil"},
        crops={"wheat", "barley", "coffee"}, base_confidence=0.6,
    ),
    SymptomRule(
        "wheat.n_deficiency", "نقص نيتروجين", "nutrient",
        required_symptoms={"general_yellowing", "old_leaves_affected"},
        supporting_symptoms={"stunted_growth"},
        crops=set(), base_confidence=0.6,
    ),
    SymptomRule(
        "coffee.zn_deficiency", "نقص زنك", "nutrient",
        required_symptoms={"interveinal_chlorosis", "small_leaves"},
        supporting_symptoms={"short_internodes"},
        crops={"coffee", "citrus"}, base_confidence=0.55,
    ),
    SymptomRule(
        "wheat.aphid", "منّ", "pest",
        required_symptoms={"insects_on_leaves"},
        supporting_symptoms={"sticky_honeydew", "curled_leaves", "ants_present"},
        crops=set(), base_confidence=0.65,
    ),
    SymptomRule(
        "coffee.leaf_rust", "صدأ أوراق البنّ", "disease",
        required_symptoms={"orange_powder_underside"},
        supporting_symptoms={"leaf_drop", "yellow_spots_upperside"},
        crops={"coffee"}, base_confidence=0.7,
    ),
    SymptomRule(
        "qat.water_stress", "إجهاد مائي", "water_stress",
        required_symptoms={"wilting"},
        supporting_symptoms={"leaf_curl", "dry_soil", "midday_drooping"},
        crops=set(), base_confidence=0.6,
    ),
    SymptomRule(
        "generic.salinity", "إجهاد ملوحة", "water_stress",
        required_symptoms={"leaf_tip_burn"},
        supporting_symptoms={"white_soil_crust", "stunted_growth"},
        crops=set(), base_confidence=0.55,
    ),
]


@dataclass
class DiagnosisCandidate:
    issue_code: str
    name_ar: str
    category: str
    confidence: float
    matched_ar: str

    def to_dict(self) -> Dict:
        return {
            "issue_code": self.issue_code,
            "name_ar": self.name_ar,
            "category": self.category,
            "confidence": round(self.confidence, 2),
            "matched_ar": self.matched_ar,
        }


@dataclass
class DiagnosisResult:
    crop: str
    observed_symptoms: List[str]
    candidates: List[DiagnosisCandidate]
    next_step_ar: str

    def to_dict(self) -> Dict:
        return {
            "crop": self.crop,
            "observed_symptoms": self.observed_symptoms,
            "candidates": [c.to_dict() for c in self.candidates],
            "next_step_ar": self.next_step_ar,
        }


def diagnose(crop: str, symptoms: List[str]) -> DiagnosisResult:
    """يطابق الأعراض المرصودة مع قواعد المعرفة ويرتّب المرشّحين.

    لا يدّعي يقيناً — يعيد قائمة احتمالات + خطوة تأكيد.
    """
    observed: Set[str] = set(symptoms)
    candidates: List[DiagnosisCandidate] = []

    for rule in SYMPTOM_RULES:
        # تحقّق المحصول
        if rule.crops and crop not in rule.crops:
            continue
        # يجب توفّر كلّ الأعراض المطلوبة
        if not rule.required_symptoms.issubset(observed):
            continue
        # احسب الثقة: أساس + دعم
        support_hits = len(rule.supporting_symptoms & observed)
        support_bonus = 0.1 * support_hits
        conf = min(0.95, rule.base_confidence + support_bonus)
        matched = rule.required_symptoms | (rule.supporting_symptoms & observed)
        candidates.append(DiagnosisCandidate(
            issue_code=rule.issue_code, name_ar=rule.name_ar,
            category=rule.category, confidence=conf,
            matched_ar=f"تطابق: {', '.join(sorted(matched))}",
        ))

    candidates.sort(key=lambda c: c.confidence, reverse=True)

    if not candidates:
        next_step = (
            "لا تطابق واضح مع الأعراض المُدخَلة. أضف صورة عالية الدقّة وأنشئ "
            "نقطة استكشاف (scouting pin)، أو استشر مهندساً زراعيّاً."
        )
    else:
        top = candidates[0]
        if top.category == "nutrient":
            next_step = (
                f"الأرجح: {top.name_ar}. لكنّ تأكيد نقص العناصر يحتاج تحليل "
                "تربة/نسيج مختبري قبل التسميد (لا تُسمّد على التخمين)."
            )
        else:
            next_step = (
                f"الأرجح: {top.name_ar} (ثقة {top.confidence:.0%}). ثبّت بصورة "
                "عالية الدقّة + مهندس قبل أيّ مبيد. هذا تشخيص أوّلي لا قاطع."
            )

    return DiagnosisResult(
        crop=crop, observed_symptoms=sorted(observed),
        candidates=candidates, next_step_ar=next_step,
    )


def list_symptoms() -> List[Dict[str, str]]:
    """قائمة الأعراض المتاحة للاختيار (واجهة الموبايل)."""
    catalog = {
        "orange_pustules": "بثور برتقاليّة على الأوراق",
        "leaf_yellowing": "اصفرار الأوراق",
        "powder_on_touch": "مسحوق عند اللمس",
        "interveinal_chlorosis": "اصفرار بين العروق",
        "young_leaves_affected": "الأوراق الحديثة متأثّرة",
        "old_leaves_affected": "الأوراق القديمة متأثّرة",
        "general_yellowing": "اصفرار عامّ",
        "stunted_growth": "نموّ متقزّم",
        "small_leaves": "أوراق صغيرة",
        "short_internodes": "سلاميّات قصيرة",
        "insects_on_leaves": "حشرات على الأوراق",
        "sticky_honeydew": "ندوة عسليّة لزجة",
        "curled_leaves": "أوراق ملتفّة",
        "ants_present": "وجود نمل",
        "orange_powder_underside": "مسحوق برتقالي أسفل الورقة",
        "leaf_drop": "تساقط الأوراق",
        "yellow_spots_upperside": "بقع صفراء أعلى الورقة",
        "wilting": "ذبول",
        "leaf_curl": "تجعّد الأوراق",
        "dry_soil": "تربة جافّة",
        "midday_drooping": "تدلٍّ وقت الظهيرة",
        "leaf_tip_burn": "احتراق أطراف الأوراق",
        "white_soil_crust": "قشرة بيضاء على التربة",
        "alkaline_soil": "تربة قلويّة",
    }
    return [{"code": k, "name_ar": v} for k, v in catalog.items()]

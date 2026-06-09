"""
services/sahool-platform/api/onboarding.py — استبيان دخول المزارع

المرجع: docs/history/ONBOARDING_QUESTIONNAIRE.md (بحث الوكيل المجالي).

التصميم للسياق اليمني (كما حدّد البحث):
- offline-first: كلّ الأسئلة تُحمّل دفعةً ثمّ تُملأ بلا اتّصال
- RTL + عربيّة: كلّ نصّ بالعربيّة
- أمّيّة رقميّة منخفضة: أسئلة قليلة إلزاميّة، الباقي اختياري متدرّج، وحدات
  مألوفة (فدان/دونم بجانب الهكتار)، خيارات جاهزة بدل إدخال حرّ حيث أمكن

البنية: 9 أقسام، كلّ سؤال له: id, label_ar, type, required, options/unit.
المرحلة الأولى (الإلزاميّة) قصيرة جدّاً لتقليل الاحتكاك؛ الباقي "تعميق"
اختياري يملؤه المزارع لاحقاً ويحسّن دقّة التوصيات.
"""

from __future__ import annotations

from pydantic import BaseModel


class OnboardingQuestion(BaseModel):
    id: str
    label_ar: str
    type: str  # text|number|select|multiselect|date|gps|polygon|photo|audio
    required: bool = False
    unit: str | None = None
    options: list[str] | None = None
    hint_ar: str | None = None


class OnboardingSection(BaseModel):
    id: str
    title_ar: str
    phase: int  # 1 = إلزامي مبدئي · 2 = تعميق اختياري
    questions: list[OnboardingQuestion]


# ─── تعريف الاستبيان (9 أقسام) ──────────────────────────────────
# المرحلة 1 (phase=1): الحدّ الأدنى لبدء الاستخدام — قليلة ومألوفة.
# المرحلة 2 (phase=2): تعميق اختياري يحسّن دقّة التوصيات.

ONBOARDING_SECTIONS: list[OnboardingSection] = [
    OnboardingSection(
        id="identity",
        title_ar="التعريف",
        phase=1,
        questions=[
            OnboardingQuestion(
                id="farmer_name", label_ar="اسمك أو اسم المزرعة", type="text", required=True
            ),
            OnboardingQuestion(
                id="field_name",
                label_ar="اسم الحقل",
                type="text",
                required=True,
                hint_ar="اسم تتذكّره بسهولة، مثل: حقل الشمال",
            ),
        ],
    ),
    OnboardingSection(
        id="spatial",
        title_ar="المكان",
        phase=1,
        questions=[
            OnboardingQuestion(
                id="district", label_ar="المديريّة/القرية", type="text", required=True
            ),
            OnboardingQuestion(
                id="boundary",
                label_ar="ارسم حدود حقلك على الخريطة",
                type="polygon",
                required=False,
                hint_ar="ارسم الحدود لحساب المساحة تلقائيّاً",
            ),
            OnboardingQuestion(id="gps", label_ar="موقع الحقل (GPS)", type="gps", required=False),
        ],
    ),
    OnboardingSection(
        id="agronomic",
        title_ar="المحصول",
        phase=1,
        questions=[
            OnboardingQuestion(
                id="crop",
                label_ar="المحصول الرئيسي",
                type="select",
                required=True,
                options=[
                    "قمح",
                    "شعير",
                    "ذرة",
                    "ذرة رفيعة",
                    "سمسم",
                    "بطاطس",
                    "بصل",
                    "طماطم",
                    "بُن",
                    "قات",
                    "أخرى",
                ],
            ),
            OnboardingQuestion(
                id="area",
                label_ar="مساحة الحقل",
                type="number",
                required=True,
                unit="اختر الوحدة",
                hint_ar="أو ارسم الحدود ونحسبها لك",
            ),
            OnboardingQuestion(
                id="area_unit",
                label_ar="وحدة المساحة",
                type="select",
                required=True,
                options=["هكتار", "فدان", "دونم", "لِبنة"],
            ),
            OnboardingQuestion(id="variety", label_ar="الصنف (إن عُرف)", type="text"),
        ],
    ),
    OnboardingSection(
        id="temporal",
        title_ar="التواريخ",
        phase=2,
        questions=[
            OnboardingQuestion(id="sowing_date", label_ar="تاريخ البذار", type="date"),
            OnboardingQuestion(id="harvest_date", label_ar="تاريخ الحصاد المتوقّع", type="date"),
        ],
    ),
    OnboardingSection(
        id="soil_water",
        title_ar="التربة والماء",
        phase=2,
        questions=[
            OnboardingQuestion(
                id="soil_type",
                label_ar="نوع التربة",
                type="select",
                options=["طيني", "رملي", "طمي", "مختلط", "لا أعرف"],
            ),
            OnboardingQuestion(
                id="water_source",
                label_ar="مصدر مياه الري",
                type="select",
                options=["بئر", "سدّ", "مطر", "فيضان/سيل", "شبكة"],
            ),
            OnboardingQuestion(
                id="irrigation_system",
                label_ar="نظام الري",
                type="select",
                options=["محوري", "تنقيط", "سطحي", "سيلي", "بدون (مطري)"],
            ),
            OnboardingQuestion(
                id="water_ec", label_ar="ملوحة ماء الري (إن عُرفت)", type="number", unit="dS/m"
            ),
        ],
    ),
    OnboardingSection(
        id="inputs",
        title_ar="المدخلات",
        phase=2,
        questions=[
            OnboardingQuestion(
                id="seed_rate", label_ar="كميّة البذور", type="number", unit="كجم/هكتار"
            ),
            OnboardingQuestion(
                id="fertilizer",
                label_ar="السماد المستخدم",
                type="multiselect",
                options=["DAP", "Urea", "NPK", "سماد عضوي", "بدون"],
            ),
            OnboardingQuestion(
                id="irrigation_count", label_ar="عدد الريّات في الموسم", type="number"
            ),
        ],
    ),
    OnboardingSection(
        id="pests",
        title_ar="الآفات والأمراض",
        phase=2,
        questions=[
            OnboardingQuestion(id="pest_notes", label_ar="ملاحظات آفات/أمراض", type="text"),
            OnboardingQuestion(
                id="loss_pct", label_ar="نسبة الخسائر التقديريّة", type="number", unit="%"
            ),
        ],
    ),
    OnboardingSection(
        id="economic",
        title_ar="الاقتصاد",
        phase=2,
        questions=[
            OnboardingQuestion(
                id="sale_price", label_ar="سعر بيع الوحدة", type="number", unit="ريال"
            ),
            OnboardingQuestion(id="sale_market", label_ar="مكان البيع", type="text"),
        ],
    ),
    OnboardingSection(
        id="freeform",
        title_ar="ملاحظات حرّة",
        phase=2,
        questions=[
            OnboardingQuestion(id="notes", label_ar="أيّ ملاحظات عن الموسم", type="text"),
            OnboardingQuestion(id="photos", label_ar="صور للحقل", type="photo"),
            OnboardingQuestion(
                id="audio",
                label_ar="تسجيل صوتي (للأمّيّة)",
                type="audio",
                hint_ar="سجّل ملاحظاتك صوتيّاً بدل الكتابة",
            ),
        ],
    ),
]


def get_questionnaire(phase: int | None = None) -> dict:
    """يُرجع تعريف الاستبيان. phase=1 للإلزامي فقط، None للكلّ."""
    secs = ONBOARDING_SECTIONS
    if phase is not None:
        secs = [s for s in secs if s.phase == phase]
    return {
        "version": "1.0",
        "rtl": True,
        "lang": "ar",
        "offline_capable": True,
        "sections": [s.model_dump() for s in secs],
        "required_count": sum(1 for s in ONBOARDING_SECTIONS for q in s.questions if q.required),
    }


def validate_response(answers: dict) -> dict:
    """يتحقّق من اكتمال الحقول الإلزاميّة. يُرجع {valid, missing}."""
    required_ids = [q.id for s in ONBOARDING_SECTIONS for q in s.questions if q.required]
    missing = [
        qid for qid in required_ids if qid not in answers or answers.get(qid) in (None, "", [])
    ]
    return {
        "valid": len(missing) == 0,
        "missing": missing,
        "answered": len([k for k in answers if answers.get(k) not in (None, "", [])]),
    }

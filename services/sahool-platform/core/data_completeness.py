"""
core.data_completeness
======================
نظام اكتمال البيانات والرسائل التحفيزية.

الفلسفة (قرار المستخدم): بدل "BLOCKED — ممنوع" القاطع،
نُظهر للمزارع قيمة إكمال بياناته ونحفّزه:
  "توصيات تقريبية الآن — أكمل بياناتك لتوصيات دقيقة قيّمة"
ثم نرسل إشعاراً لاحقاً حين تصبح النتائج الدقيقة جاهزة.

الحدّ الثابت (سلامة): التحفيز للتوصيات العامة فقط.
توصيات المبيدات (L3/PHI) تبقى محجوبة لا "تقريبية" — سلامة المستهلك.

تعدّد المستخدمين: كل دالة تأخذ field_id؛ العزل يُدار في طبقة
التخزين (lite_store) بعمود tenant/farmer_id. جاهز لـ RLS عند PostgreSQL.
"""
from __future__ import annotations

from dataclasses import dataclass, field as dc_field

# وزن كل حقل في درجة الاكتمال + ما يفتحه
# (الحقل، الوزن، التوصية التي يفتحها)
FIELD_WEIGHTS = [
    # أساسية (موجودة عادةً)
    ("boundary", 15, "خريطة الحقل والمساحة"),
    ("crop", 15, "تقويم المحصول ومراحل النمو"),
    ("planting_date", 10, "حساب GDD والاحتياج المائي"),
    ("irrigation_type", 10, "جدولة الري"),
    # حاكمة (تفتح الدقّة)
    ("salinity_s3", 15, "إدارة الملوحة وتوصيات دقيقة"),
    ("ph_s4", 15, "ملاءمة المحصول وتصحيح الحموضة"),
    ("water_i3", 15, "جودة مياه الري والتوصية الدقيقة"),
    # إثرائية
    ("organic_matter", 5, "تقدير الخصوبة"),
]

# الحقول الحاكمة التي تفتح حالة READY
_GOVERNING = {"salinity_s3", "ph_s4", "water_i3"}


@dataclass
class CompletenessResult:
    score: int                          # 0–100
    provided: list[str] = dc_field(default_factory=list)
    missing: list[str] = dc_field(default_factory=list)
    next_value: str = ""                # أهم حقل ناقص + ما يفتحه
    headline_ar: str = ""
    is_precise: bool = False            # كل الحاكمات متوفّرة؟


def compute_completeness(provided_fields: set[str]) -> CompletenessResult:
    """يحسب درجة الاكتمال + الرسالة التحفيزية."""
    score = 0
    provided, missing = [], []
    for name, weight, unlocks in FIELD_WEIGHTS:
        if name in provided_fields:
            score += weight
            provided.append(name)
        else:
            missing.append((name, weight, unlocks))

    governing_done = _GOVERNING.issubset(provided_fields)

    # أهم حقل ناقص (أعلى وزن) — لتحفيز المزارع
    next_value = ""
    if missing:
        missing.sort(key=lambda x: -x[1])
        top = missing[0]
        next_value = f"أضف «{_label(top[0])}» → يفتح: {top[2]}"

    # الرسالة التحفيزية (لا قاطعة)
    if governing_done:
        headline = "🟢 بياناتك كاملة — توصياتك دقيقة وقيّمة"
    elif score >= 60:
        headline = "🟡 توصيات تقريبية جيدة — أكمل التحاليل الحاكمة لدقّة كاملة"
    elif score >= 30:
        headline = "🟠 توصيات عامة الآن — كلما أكملت بياناتك، زادت قيمة توصياتك"
    else:
        headline = "⚪ ابدأ بإدخال بياناتك — كل حقل يفتح توصيات أكثر قيمة"

    return CompletenessResult(
        score=score, provided=provided,
        missing=[m[0] for m in missing], next_value=next_value,
        headline_ar=headline, is_precise=governing_done,
    )


def _label(field_name: str) -> str:
    labels = {
        "boundary": "حدود الحقل", "crop": "المحصول", "planting_date": "تاريخ الزراعة",
        "irrigation_type": "نظام الري", "salinity_s3": "ملوحة التربة S3",
        "ph_s4": "حموضة pH S4", "water_i3": "ملوحة المياه I3", "organic_matter": "المادة العضوية",
    }
    return labels.get(field_name, field_name)


# ── نظام الإشعارات اللاحقة ──

class NotificationTrigger(str):
    """أنواع الإشعارات التحفيزية اللاحقة."""
    DATA_COMPLETE = "data_complete"      # أكمل البيانات → نتائج دقيقة جاهزة
    LAB_RESULTS = "lab_results"          # وصلت نتائج المعمل
    PRECISE_READY = "precise_ready"      # التوصيات الدقيقة مُفعّلة الآن
    REMINDER = "reminder"                # تذكير لطيف بإكمال البيانات


def build_notification(trigger: str, field_name: str,
                       completeness: CompletenessResult | None = None) -> dict:
    """يبني إشعاراً تحفيزياً (للإرسال عبر التطبيق/WhatsApp لاحقاً)."""
    messages = {
        NotificationTrigger.PRECISE_READY: {
            "title_ar": "🟢 توصياتك الدقيقة جاهزة!",
            "body_ar": f"اكتملت بيانات «{field_name}» — توصياتك الآن دقيقة وقيّمة. اطّلع عليها.",
        },
        NotificationTrigger.LAB_RESULTS: {
            "title_ar": "🧫 وصلت نتائج تحليل التربة",
            "body_ar": f"نتائج «{field_name}» جاهزة — أُدخلت تلقائياً وفُعّلت التوصيات الدقيقة.",
        },
        NotificationTrigger.REMINDER: {
            "title_ar": "💡 أكمل بيانات حقلك",
            "body_ar": (completeness.next_value if completeness and completeness.next_value
                        else f"أكمل بيانات «{field_name}» للحصول على توصيات أدقّ."),
        },
        NotificationTrigger.DATA_COMPLETE: {
            "title_ar": "✅ بياناتك مكتملة",
            "body_ar": f"شكراً! بيانات «{field_name}» كاملة — توصياتك ستكون بأعلى دقّة.",
        },
    }
    msg = messages.get(trigger, messages[NotificationTrigger.REMINDER])
    return {"trigger": trigger, "field": field_name, **msg}

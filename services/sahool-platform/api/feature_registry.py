"""feature_registry.py — سجلّ موثّق لأعلام الميزات (FEATURE_*) التي تحرس راوترات API.

كلّ علم هنا يحرس راوتراً واحداً تحت ``api/routers/``: مُطفأ افتراضاً ⇒ النقطة تُرجِع
404 حتى يُضبَط العلم إلى قيمة truthy (1/true/yes/on). الغرض من السجلّ منع «الأعلام
الصامتة»: أيّ علم جديد يحرس راوتراً دون مدخل هنا يُفشِل اختبار
``tests_v9/test_feature_flags_smoke.py`` — فلا يبقى مسار 404 غير موثّق.

التحديث: عند إضافة علم ``FEATURE_*`` جديد لحراسة راوتر (نمط
``os.getenv("FEATURE_X", "").strip().lower() in _TRUTHY``)، أضِف مدخله هنا
(الاسم → وصف موجز). الاختبار يستخرج المجموعة الفعليّة من ``api/routers/`` ويطابقها
مع مفاتيح هذا السجلّ (تساوٍ دقيق في الاتّجاهين).
"""

from __future__ import annotations

# قيم env التي تُعدّ «مُفعِّلة» (يطابق منطق الراوترات تماماً).
TRUTHY = {"1", "true", "yes", "on"}

# اسم العلم → وصف موجز للميزة التي يحرسها. الافتراض دائماً OFF (404).
FEATURE_FLAGS: dict[str, str] = {
    "FEATURE_PORTFOLIO_COMMAND": "مركز قيادة المحفظة (نظرة عامّة عبر الحقول).",
    "FEATURE_DEVICE_TWIN": "التوأم الرقميّ للجهاز (حالة/تحكّم الأجهزة).",
    "FEATURE_DELTA_SYNC": "المزامنة التفاضليّة (Delta-Sync) للعملاء غير المتّصلين.",
    "FEATURE_NATURAL_LANGUAGE_GIS": "استعلامات GIS باللغة الطبيعيّة.",
    "FEATURE_DECISION_STUDIO": "استوديو القرار (شرح/تفكيك القرارات).",
    "FEATURE_OPERATIONS_WALL": "جدار مركز العمليّات (تدفّق العمليّات الحيّ).",
    "FEATURE_REPLAY_MAP": "إعادة تشغيل الموسم على الخريطة (agronomic replay).",
    "FEATURE_EVIDENCE_MAP": "خريطة الدليل (طبقات الأدلّة المكانيّة).",
    "FEATURE_LEARNING_DASHBOARD": "لوحة حلقة التعلّم (ملخّص التعلّم/النتائج).",
    "FEATURE_DECISION_CONFIDENCE": "ثقة القرار الموحَّدة (مؤشّرات الثقة).",
    "FEATURE_UNIFIED_LINEAGE": "النَّسَب الموحّد للتنفيذ (execution lineage).",
    "FEATURE_GIS_KERNEL": "نواة GIS (عمليّات مكانيّة منخفضة المستوى).",
    "FEATURE_IRRIGATION_NETWORK": "توأم شبكة الريّ (irrigation network twin).",
    "FEATURE_EXECUTION_FEEDBACK": "رصد حلقة التنفيذ (execution feedback).",
    "FEATURE_FARM_OPERATIONS_LEDGER": "دفتر العمليات الزراعية الرقابي (أعمال/مياه/طاقة/مدخلات).",
}


def is_enabled(name: str, env_value: str | None) -> bool:
    """هل العلم ``name`` مُفعَّل بقيمة env المعطاة؟ مُطفأ افتراضاً (None/فارغ ⇒ False).

    يطابق منطق الحراسة في الراوترات: ``getenv(...).strip().lower() in TRUTHY``.
    دالّة نقيّة بلا أيّ وصول لقاعدة بيانات أو متغيّرات بيئة — تُمرَّر القيمة صراحةً.
    ``name`` غير مستعمَل في القرار (مُمرَّر للوضوح/التماثل مع نمط الراوترات).
    """
    del name  # غير مؤثّر في القرار — موجود للتماثل مع توقيع الحراسة في الراوترات.
    return (env_value or "").strip().lower() in TRUTHY

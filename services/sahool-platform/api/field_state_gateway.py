"""
api/field_state_gateway.py — بوّابة الحالة القانونيّة الموحّدة للحقل (Phase 1)

الهدف (من سؤال «مصدر الحقيقة الواحد / Canonical Field State»):
  المنصّة تملك مُركِّب حالة ممتازاً (field_operational_state.resolve_field_state)
  لكنّه كان «آلة حاسبة» نقيّة: المتّصِل يمرّر كلّ المدخلات (عمر NDVI/الثقة/…)
  بنفسه ⇒ ليس مصدر حقيقة واحداً (كلّ مستهلك يجمّع «الحقيقة» على طريقته).

ما تفعله هذه الطبقة (وما لا تفعله — صدق):
  ✓ تجمع مدخلات القرار من **مصادرها القانونيّة في قاعدة المنصّة** بدل المتّصِل:
      - نضارة NDVI  ← imagery_automation_fields.last_image_date (تتبّع صور Sentinel)
      - نضارة التربة ← أحدث soil_lab_tests.sampled_on (معتمَد/منشور)
      - نضارة الطقس ← weather_automation_cache.fetched_at (عبر موقع الحقل)
  ✓ تشتقّ مستوى الثقة من نضارة NDVI عبر confidence_engine.TemporalConfidence
    (لا أرقام مُلفَّقة — أحدث صورة = ثقة أعلى، غياب الصورة = None).
  ✓ تبقي التركيب نفسه في resolve_field_state (لا تكرّره) — طبقة جمعٍ فقط.
  ✗ لا تخزّن الحالة (إسقاط مُخزَّن = Phase 2 لاحقاً) — تحسبها عند الطلب من المصدر.
  ✗ لا تختلق مدخلات غائبة: غياب المصدر ⇒ عمر None ⇒ resolve_field_state يعدّها
    بيانات ناقصة بصدق (INSUFFICIENT) لا «حديثة».

الدوال هنا نقيّة (بلا قاعدة بيانات) لتُختبَر مباشرةً؛ استعلامات SQL تبقى في
نقطة النهاية (main.py) ضمن tenant_connection (RLS) وتمرّر نتائجها هنا.
"""

from __future__ import annotations

from datetime import date


def _days_since(ref: date | None, today: date) -> float | None:
    """عمر بالأيّام منذ تاريخ مرجعيّ (لا سالب). None إن غاب المرجع."""
    if ref is None:
        return None
    return max(0.0, float((today - ref).days))


def derive_confidence_level(ndvi_age_days: float | None) -> str | None:
    """يشتقّ مستوى الثقة من نضارة NDVI الزمنيّة (TemporalConfidence + level_from_score).

    صدق المصدر: لا صورة NDVI (عمر None) ⇒ ثقة None — يدع resolve_field_state يعلن
    «بيانات ناقصة» بدل اختلاق ثقة. القيمة نصّيّة (high/medium/low/very_low).
    """
    if ndvi_age_days is None:
        return None
    # استيراد محلّيّ لتفادي أيّ دورة استيراد عند تحميل الوحدة.
    from .confidence_engine import TemporalConfidence, level_from_score

    score = TemporalConfidence(days_since_observation=int(round(ndvi_age_days))).score
    return level_from_score(score).value


def build_state_inputs(
    *,
    last_image_date: date | None,
    latest_soil_sampled_on: date | None,
    weather_age_hours: float | None,
    today: date,
) -> dict:
    """يحوّل صفوف المصادر القانونيّة إلى مدخلات resolve_field_state.

    يُرجِع dict بمفاتيح فرعيّة من توقيع resolve_field_state (الباقي يبقى None):
    confidence_level + ندى الأعمار الثلاثة. يُمرَّر كـ**kwargs لـresolve_field_state.
    """
    ndvi_age = _days_since(last_image_date, today)
    soil_age = _days_since(latest_soil_sampled_on, today)
    # تطبيع عمر الطقس مثل أعمار التواريخ: قيمة سالبة (انحراف ساعة DB/app أو طابع
    # زمنيّ مستقبليّ) لا تُعدّ «طازجة» زوراً — تُقصّ إلى 0 لإدخال قانونيّ غير سالب.
    wx_age = max(0.0, float(weather_age_hours)) if weather_age_hours is not None else None
    return {
        "confidence_level": derive_confidence_level(ndvi_age),
        "ndvi_age_days": ndvi_age,
        "soil_age_days": soil_age,
        "weather_age_hours": wx_age,
    }

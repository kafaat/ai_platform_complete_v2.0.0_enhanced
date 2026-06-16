"""core/data_quality.py — سجلّ سياسات جودة البيانات + مُقيّمها (منطق صرف، pure).

خارطة الطريق: #12 — قواعد جودة البيانات (Data Quality Rules).

المبدأ:
  • هذا هو **السجلّ الوحيد** لسياسات تحقّق جودة البيانات في المنصّة — مصدر واحد
    للحقيقة. بدل نمط «if ndvi < 0» المُبعثَر في مسارات الاستيعاب/الحساب، تُعلَن
    سياسات التحقّق كـ«بيانات» (QualityRule) ويُطبّقها مُقيّم عامّ (evaluate_record).
  • هكذا تُضاف/تُعدّل القواعد دون لمس الكود — توسّع ميتاداتا-مُوجَّه (metadata-driven).
  • المنطق **نقيّ** (لا شبكة، لا قاعدة) — يُختبَر offline بالكامل، ولا يرمي
    استثناءً على سجلّ سيّئ مهما كان (صدق: التحقّق لا يُسقِط المسار).

⚠ الحدود أدناه **حدود صحّة فيزيائيّة** (physical validity ranges) — وقائع
لا جدال فيها (مثلاً NDVI رياضيّاً ضمن [-1, 1]). ليست عتبات **معايرة زراعيّة**
(agronomic calibration) — تلك تحتاج معايرة ميدانيّة ولا نخترعها هنا.

ملاحظة (متابعة لاحقاً): ربط هذا السجلّ فعليّاً بنقاط الاستيعاب/الحساب — أي
استدعاء evaluate_record بدل الـ«if» السطريّة — هو **عمل لاحق**؛ هذه الدفعة
تُسلّم السجلّ + المُقيّم فقط.
"""

from __future__ import annotations

from dataclasses import dataclass

# مجموعة الفحوص المدعومة (ثابتة وصغيرة).
_CHECKS = frozenset({"range", "min", "max", "not_null"})
# درجات الخطورة المتاحة.
_SEVERITIES = frozenset({"info", "warning", "critical"})


@dataclass(frozen=True)
class QualityRule:
    """قاعدة جودة بيانات واحدة — تُعلَن كبيانات لا ككود.

    الحقول:
      • id        — معرّف فريد للقاعدة (للتتبّع والميتاداتا).
      • field     — اسم المقياس في السجلّ (مثل "ndvi").
      • check     — نوع الفحص: range | min | max | not_null.
      • low/high  — حدود الفحص (حسب نوعه)؛ None حيث لا تنطبق.
      • severity  — درجة الخطورة: info | warning | critical.
      • message_ar — رسالة عربيّة تُعرَض عند المخالفة.
    """

    id: str
    field: str
    check: str
    low: float | None = None
    high: float | None = None
    severity: str = "warning"
    message_ar: str = ""


# ─── السجلّ المبدئيّ — حدود صحّة فيزيائيّة فقط (لا معايرة زراعيّة) ──────
# NDVI/NDRE/SAVI: نِسَب طيفيّة مُعرَّفة رياضيّاً ضمن [-1, 1] — أيّ قيمة خارجها
# خطأ قياس/حساب لا واقع فيزيائيّ. (مؤشّرات الانعكاس المعيّرة محصورة بحكم تعريفها.)
# رطوبة التربة/الهواء %: نِسَب مئويّة ⇒ ضمن [0, 100] بالضرورة.
# الحرارة °م: حدود فيزيائيّة لسطح الأرض — أدنى رقم قياسيّ عالميّ ≈ -89.2°م
#   (محطّة فوستوك، أنتاركتيكا) وأعلى ≈ 56.7°م (وادي الموت)؛ نتبنّى [-90, 60]
#   كنطاق صحّة سخيّ. قيمة خارجه ⇒ خطأ مستشعر مؤكَّد.
_RULES: list[QualityRule] = [
    QualityRule(
        id="ndvi_physical_range",
        field="ndvi",
        check="range",
        low=-1.0,
        high=1.0,
        severity="critical",
        message_ar="قيمة NDVI خارج المدى الفيزيائيّ [-1, 1] — خطأ قياس/حساب.",
    ),
    QualityRule(
        id="ndre_physical_range",
        field="ndre",
        check="range",
        low=-1.0,
        high=1.0,
        severity="critical",
        message_ar="قيمة NDRE خارج المدى الفيزيائيّ [-1, 1] — خطأ قياس/حساب.",
    ),
    QualityRule(
        id="savi_physical_range",
        field="savi",
        check="range",
        low=-1.0,
        high=1.0,
        severity="critical",
        message_ar="قيمة SAVI خارج المدى الفيزيائيّ [-1, 1] — خطأ قياس/حساب.",
    ),
    QualityRule(
        id="soil_moisture_pct_range",
        field="soil_moisture_pct",
        check="range",
        low=0.0,
        high=100.0,
        severity="warning",
        message_ar="رطوبة التربة (%) خارج المدى [0, 100] — نسبة مئويّة غير صالحة.",
    ),
    QualityRule(
        id="humidity_pct_range",
        field="humidity_pct",
        check="range",
        low=0.0,
        high=100.0,
        severity="warning",
        message_ar="الرطوبة النسبيّة (%) خارج المدى [0, 100] — نسبة مئويّة غير صالحة.",
    ),
    QualityRule(
        id="temperature_c_physical_range",
        field="temperature_c",
        check="range",
        low=-90.0,
        high=60.0,
        severity="warning",
        message_ar="الحرارة (°م) خارج المدى الفيزيائيّ [-90, 60] — خطأ مستشعر مرجَّح.",
    ),
]


def _is_number(value: object) -> bool:
    """هل القيمة عدد صالح للفحوص الرقميّة؟ (نستبعد bool لأنّه فرع من int)."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _violation(rule: QualityRule, value: object) -> dict:
    """يبني قاموس مخالفة موحّد من قاعدة وقيمة."""
    return {
        "rule_id": rule.id,
        "field": rule.field,
        "value": value,
        "severity": rule.severity,
        "message_ar": rule.message_ar,
    }


def _check_fails(rule: QualityRule, value: float) -> bool:
    """يُطبّق فحص القاعدة على قيمة رقميّة ويُعيد True عند المخالفة."""
    if rule.check == "range":
        return (rule.low is not None and value < rule.low) or (
            rule.high is not None and value > rule.high
        )
    if rule.check == "min":
        return rule.low is not None and value < rule.low
    if rule.check == "max":
        return rule.high is not None and value > rule.high
    # not_null تُعالَج قبل فحص القيمة الرقميّة (انظر evaluate_record).
    return False


def evaluate_record(record: dict, rules: list[QualityRule] | None = None) -> list[dict]:
    """يُقيّم سجلّاً واحداً مقابل القواعد ويُعيد قائمة المخالفات.

    السلوك:
      • القاعدة التي **يغيب** حقلها عن السجلّ تُتجاوَز بصمت — لا تلفيق لقراءة
        غير متوفّرة (صدق/graceful).
      • "not_null": تُخالَف إن كان الحقل حاضراً وقيمته None.
      • الفحوص الرقميّة (range/min/max): إن كانت القيمة **غير رقميّة** (نصّ، None…)
        نُسجّلها مخالفةً بدرجة خطورة القاعدة — قيمة غير قابلة للتحقّق خطأ بحدّ ذاته.
      • نقيّ تماماً: لا يرمي استثناءً مهما كان السجلّ سيّئاً.

    كلّ مخالفة قاموس: {"rule_id","field","value","severity","message_ar"}.
    """
    active = _RULES if rules is None else rules
    violations: list[dict] = []
    for rule in active:
        if rule.field not in record:
            continue  # حقل غائب ⇒ لا قراءة نُلفّقها.
        value = record[rule.field]

        if rule.check == "not_null":
            if value is None:
                violations.append(_violation(rule, value))
            continue

        # فحص رقميّ: قيمة غير رقميّة = مخالفة (لا يمكن التحقّق منها).
        if not _is_number(value):
            violations.append(_violation(rule, value))
            continue

        if _check_fails(rule, float(value)):
            violations.append(_violation(rule, value))

    return violations


def list_rules() -> list[dict]:
    """استبطان الميتاداتا — يُعيد كلّ قاعدة كقاموس (للعرض/التوثيق)."""
    return [
        {
            "id": r.id,
            "field": r.field,
            "check": r.check,
            "low": r.low,
            "high": r.high,
            "severity": r.severity,
            "message_ar": r.message_ar,
        }
        for r in _RULES
    ]


def rules_for(field: str) -> list[QualityRule]:
    """يُعيد قواعد حقل بعينه (مثلاً كلّ قواعد "ndvi")."""
    return [r for r in _RULES if r.field == field]

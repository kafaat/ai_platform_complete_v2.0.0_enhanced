"""core/salinity_policy.py — سياسة قرار تفعيل الملوحة تلقائيّاً (دالّة نقيّة).

تُكمل حلّ **H5** (`sahool-brain/gaps/registry.md`): الملوحة (`apply_salinity` في
`compute_irrigation`/`water_balance`) **مُطفأة افتراضيّاً**، لكنّها تُفعَّل **تلقائيّاً من جودة
البيانات** لا يدويّاً. القرار يُشتقّ من توفّر تحليل مخبريّ موثوق وحديث — لا من تبديل بشريّ.

المنطق (قرار المستخدم — مُنفَّذ حرفيّاً):
  - **تُفعَّل (enabled=True)** عند: وجود تحليل مخبريّ حديث للتربة (ECe) أو الماء (ECw) **و**
    عمره < ٣٦٥ يوماً **و** الثقة ≥ ٠.٨.
  - **إشارات قويّة تُفعِّل** (مع شرط الحداثة/الثقة): ``ECe > 2.0 dS/m`` · ``ECw > 1.5 dS/m`` ·
    محصول حسّاس جدّاً (حمضيّات/عنب/فستق) مع وجود أيّ قياس EC.
  - **تُعطَّل (enabled=False)** عند: لا تحليل · بيانات قديمة (العمر ≥ ٣٦٥) · ثقة < ٠.٨ ·
    قيم تقديريّة من خرائط عالميّة (لا تُمرَّر كتحليل موثوق).
  - **تنبيه (warn=True بلا تفعيل)** عند: منطقة معروفة بالملوحة (الجوف/تهامة…) + تحليل قديم/
    منخفض الثقة ⇒ يُنصح المستخدم بإعادة التحليل المخبريّ.

صدق منهجيّ صارم (نمط ``api/water_twin_seed.py`` و``decision_record``):
  - **لا تفعيل على افتراض.** البيانات الناقصة ⇒ off + سبب «لا بيانات».
  - **لا تفعيل على بيانات غير موثوقة.** القديمة/منخفضة الثقة ⇒ off (+ warn إن منطقة مالحة).
  - **مصدر كلّ قرار مُعلَن** في ``reason_ar`` و``signals`` (تفصيل: «ECe=3.1>2.0»،
    «تحليل عمره 540يوم≥365»…) — لا تخمين، لا صندوق أسود.

نقيّ بالكامل: بلا I/O / قاعدة / شبكة ⇒ يُختبَر بـ``unit``. المستدعي (راوتر/خدمة) يجلب القيم
المخبريّة ويستدعي ``salinity_decision`` فقط.

⚠️ ملاحظة العتبات: الثوابت أدناه **تقديريّة قابلة للمعايرة** محلّيّاً (ليست قياساً مُعايَراً)؛
مُعلَنة هنا صراحةً لا مدفونة في المنطق.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# ── العتبات (⚠️ تقديريّة قابلة للمعايرة المحلّيّة — مُعلَنة لا مدفونة) ──────────────
# ECe القويّة: فوقها يُعَدّ ملح التربة مؤثّراً فيستحقّ تفعيل مسار الملوحة (FAO-56 Ch.8،
# عتبة إرشاديّة عامّة؛ المحاصيل تختلف). dS/m.
ECE_STRONG = 2.0
# ECw القويّة: ملوحة ماء الريّ المؤثّرة (إرشاديّة عامّة). dS/m.
ECW_STRONG = 1.5
# أقصى عمر للتحليل ليُعَدّ «حديثاً» (يوم). ≥ هذا العمر ⇒ غير موثوق زمنيّاً.
MAX_AGE_DAYS = 365
# أدنى ثقة (٠..١) في التحليل ليُعتمَد. < هذا ⇒ غير موثوق.
MIN_CONFIDENCE = 0.8


@dataclass
class SalinityDecision:
    """قرار تفعيل الملوحة — شفّاف بالكامل (كلّ تفعيل/تعطيل بسبب + إشارات مُفصَّلة).

    الحقول:
      enabled    هل يُفعَّل مسار الملوحة (``apply_salinity=True``) في حساب الريّ؟
      reason_ar  السبب الموجز بالعربيّة (مصدر القرار).
      warn       تنبيه للمستخدم (منطقة مالحة ببيانات غير موثوقة ⇒ يُنصح بإعادة التحليل) —
                 مستقلّ عن ``enabled``.
      signals    تفصيل الإشارات الداعمة للقرار («ECe=3.1>2.0»، «تحليل عمره 540يوم≥365»…).
    """

    enabled: bool
    reason_ar: str
    warn: bool = False
    signals: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """تمثيل قابل للتسلسل (JSON/تدقيق) — شفّاف."""
        return {
            "enabled": self.enabled,
            "reason_ar": self.reason_ar,
            "warn": self.warn,
            "signals": list(self.signals),
        }


def salinity_decision(
    *,
    soil_ece: float | None,
    water_ecw: float | None,
    analysis_age_days: int | None,
    confidence: float | None,
    crop_sensitive: bool = False,
    saline_region: bool = False,
) -> SalinityDecision:
    """يقرّر تفعيل الملوحة تلقائيّاً من **جودة البيانات** (نقيّ — لا I/O).

    المُدخلات:
      soil_ece          ECe التربة (dS/m) من تحليل مخبريّ، أو None إن لا قياس.
      water_ecw         ECw ماء الريّ (dS/m) من تحليل مخبريّ، أو None إن لا قياس.
      analysis_age_days عمر أحدث تحليل بالأيّام (None إن لا تحليل).
      confidence        الثقة في التحليل (٠..١؛ None إن لا تحليل).
      crop_sensitive    محصول حسّاس جدّاً للملوحة (حمضيّات/عنب/فستق…).
      saline_region     منطقة معروفة بالملوحة (الجوف/تهامة…) — للتنبيه فقط، لا للتفعيل.

    القاعدة (تُطبَّق بالترتيب، الحدود مُعرَّفة صراحةً):
      1. لا قياس EC إطلاقاً ⇒ off + «لا بيانات» (warn=False — لا داعي لتنبيه بلا أيّ إشارة).
      2. وجود قياس لكن بلا بيانات حداثة/ثقة موثوقة، أو قديم (العمر ≥ MAX_AGE_DAYS)، أو
         ثقة < MIN_CONFIDENCE ⇒ off + (warn=True إن ``saline_region``).
      3. تحليل موثوق (عمر < MAX_AGE_DAYS و ثقة ≥ MIN_CONFIDENCE):
           - ECe > ECE_STRONG أو ECw > ECW_STRONG  ⇒ on (إشارة قويّة).
           - محصول حسّاس + وجود أيّ قياس EC        ⇒ on.
           - وإلّا (قياس موثوق لكن دون العتبات وغير حسّاس) ⇒ on (تحليل موثوق يُفعِّل
             المسار حتى تُحسَب Ks الفعليّة — حتى عند EC منخفض، فالقياس الموثوق يحسم).

    الحدود (مُعرَّفة واختُبرت):
      - ECe = ECE_STRONG **بالضبط** ⇒ ليست «قويّة» (الشرط ``>`` لا ``>=``)، لكنّها تبقى
        تفعيلاً عبر مسار «تحليل موثوق».
      - العمر = MAX_AGE_DAYS **بالضبط** ⇒ **قديم** (الشرط ``< MAX_AGE_DAYS`` للحداثة، فـ
        ``age >= MAX_AGE_DAYS`` ⇒ off).
      - الثقة = MIN_CONFIDENCE **بالضبط** ⇒ **مقبولة** (الشرط ``>= MIN_CONFIDENCE``).
    """
    signals: list[str] = []

    has_ece = soil_ece is not None
    has_ecw = water_ecw is not None
    has_any_ec = has_ece or has_ecw

    # (1) لا قياس EC إطلاقاً ⇒ لا بيانات (لا تفعيل، لا تنبيه — لا إشارة أصلاً).
    if not has_any_ec:
        return SalinityDecision(
            enabled=False,
            reason_ar="لا تحليل ملوحة متوفّر — لا تفعيل (الافتراض: مُطفأة).",
            warn=False,
            signals=["لا قياس ECe/ECw"],
        )

    # نُسجّل القياسات المتوفّرة (شفافيّة) قبل تقييم الموثوقيّة.
    if has_ece:
        signals.append(f"ECe={_fmt(soil_ece)} dS/m")
    if has_ecw:
        signals.append(f"ECw={_fmt(water_ecw)} dS/m")

    # تقييم الموثوقيّة الزمنيّة والثقة (صدق صارم: الناقص = غير موثوق).
    fresh = analysis_age_days is not None and analysis_age_days < MAX_AGE_DAYS
    confident = confidence is not None and confidence >= MIN_CONFIDENCE

    # (2) قياس موجود لكن غير موثوق (ناقص الحداثة/الثقة، أو قديم، أو ثقة منخفضة).
    if not (fresh and confident):
        reasons: list[str] = []
        if analysis_age_days is None:
            reasons.append("عمر التحليل غير معروف")
            signals.append("عمر التحليل: غير معروف")
        elif analysis_age_days >= MAX_AGE_DAYS:
            reasons.append("تحليل قديم")
            signals.append(f"تحليل عمره {analysis_age_days}يوم≥{MAX_AGE_DAYS}")
        else:
            signals.append(f"تحليل عمره {analysis_age_days}يوم<{MAX_AGE_DAYS}")

        if confidence is None:
            reasons.append("الثقة غير معروفة")
            signals.append("الثقة: غير معروفة")
        elif confidence < MIN_CONFIDENCE:
            reasons.append("ثقة منخفضة")
            signals.append(f"ثقة={_fmt(confidence)}<{MIN_CONFIDENCE}")
        else:
            signals.append(f"ثقة={_fmt(confidence)}≥{MIN_CONFIDENCE}")

        warn = saline_region
        if warn:
            signals.append("منطقة معروفة بالملوحة")
        detail = "؛ ".join(reasons) if reasons else "بيانات غير موثوقة"
        reason = f"بيانات ملوحة غير موثوقة ({detail}) — لا تفعيل."
        if warn:
            reason += " ⚠️ منطقة مالحة: يُنصح بإعادة التحليل المخبريّ."
        return SalinityDecision(enabled=False, reason_ar=reason, warn=warn, signals=signals)

    # وصلنا هنا ⇒ التحليل موثوق (حديث + ثقة كافية). نُعلن ذلك.
    signals.append(f"تحليل عمره {analysis_age_days}يوم<{MAX_AGE_DAYS}")
    signals.append(f"ثقة={_fmt(confidence)}≥{MIN_CONFIDENCE}")

    strong: list[str] = []
    if has_ece and soil_ece > ECE_STRONG:
        strong.append(f"ECe={_fmt(soil_ece)}>{ECE_STRONG}")
    if has_ecw and water_ecw > ECW_STRONG:
        strong.append(f"ECw={_fmt(water_ecw)}>{ECW_STRONG}")

    # (3أ) إشارة قويّة فوق العتبة.
    if strong:
        signals.extend(strong)
        return SalinityDecision(
            enabled=True,
            reason_ar="تحليل موثوق + إشارة ملوحة قويّة (" + "، ".join(strong) + ") — تفعيل.",
            warn=False,
            signals=signals,
        )

    # (3ب) محصول حسّاس جدّاً + وجود أيّ قياس EC موثوق.
    if crop_sensitive:
        signals.append("محصول حسّاس جدّاً للملوحة")
        return SalinityDecision(
            enabled=True,
            reason_ar="تحليل موثوق + محصول حسّاس جدّاً مع قياس EC — تفعيل احترازيّ.",
            warn=False,
            signals=signals,
        )

    # (3ج) قياس موثوق دون العتبات وغير حسّاس ⇒ تفعيل (القياس الموثوق يحسم؛ Ks الفعليّة
    # ستُحسَب — وقد تكون ≈١ عند EC منخفض، فلا ضرر، والشفافيّة مَصونة).
    return SalinityDecision(
        enabled=True,
        reason_ar="تحليل ملوحة موثوق متوفّر (دون العتبات القويّة) — تفعيل لحساب Ks الفعليّة.",
        warn=False,
        signals=signals,
    )


def _fmt(x: float | None) -> str:
    """تنسيق رقم مقروء في الإشارات (يحذف الصفر العشريّ الزائد)."""
    if x is None:
        return "—"
    f = float(x)
    return str(int(f)) if f == int(f) else f"{f:g}"

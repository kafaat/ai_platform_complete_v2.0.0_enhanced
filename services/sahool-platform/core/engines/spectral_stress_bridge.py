"""core/engines/spectral_stress_bridge.py — جسر مؤشّرات الرطوبة الطيفيّة للقرار.

الفجوة المُكتشَفة (مراجعة ربط المؤشّرات، تحقُّق فعلي بالكود): سهول يحسب ~10
مؤشّرات طيفيّة، عدّة منها **محسوبة بلا ربط بالقرار**. الأهمّ: NDMI (مؤشّر رطوبة
الغطاء، الأنسب علميّاً للإجهاد المائي) محسوب لكن قرار الإجهاد يعتمد عدّ أحداث
الريّ لا الطيف. أمّا MSI فليس محسوباً حاليّاً في هذه الشجرة — الجسر يدعمه لِما
يُحسَب لاحقاً، ويتدهور بصدق إلى unknown حتى ذلك (لا اختراع).

هذا الجسر يربط مؤشّرات الرطوبة الطيفيّة بكشف الإجهاد المائي/الغذائي:
  • NDMI (NIR-SWIR1)/(NIR+SWIR1): محتوى ماء الغطاء — مرتفع=رطب، منخفض=إجهاد
  • MSI (SWIR1/NIR): الإجهاد المائي — مرتفع=إجهاد (عكس NDMI)
  • NDRE: نيتروجين/كلوروفيل (red-edge) — إجهاد غذائي
  • FAPAR: الإشعاع الممتصّ — كفاءة الإنتاج

⚠ المبدأ (اتّساقاً مع field_intelligence_coordinator + صدق المصدر):
  • العتبات من الأدبيّات الطيفيّة الموثّقة (لا اختراع)
  • إشارة استرشاديّة تُدمَج مع القرار الفيزيائي (لا تستبدله)
  • كلّ إشارة لها مصدر وثقة (provenance) — تتّسق مع نمط المايسترو
  • حتمي: عتبات صريحة، لا نموذج

⚠ ليست بديلاً عن القياس الأرضي. مؤشّر الرطوبة الطيفي وكيل (proxy) لحالة
الماء — يُرجَّح بالقياس الميداني (التربة/الريّ) عند توفّره.

المصادر: NDMI/MSI ranges (Gao 1996؛ Hunt & Rock 1989 لـMSI)؛ NDRE للنيتروجين
(Barnes 2000). العتبات تقريبيّة تُضبط ميدانيّاً لكلّ محصول/منطقة.
"""

from __future__ import annotations

from enum import Enum


class StressSignal(str, Enum):
    NONE = "none"
    MILD = "mild"
    MODERATE = "moderate"
    SEVERE = "severe"
    UNKNOWN = "unknown"  # المؤشّر غير متاح (صدق)


# عتبات NDMI (محتوى ماء الغطاء) — من الأدبيّات الطيفيّة.
# NDMI مرتفع = رطب جيّد؛ منخفض/سالب = إجهاد مائي.
NDMI_THRESHOLDS = {
    "healthy": 0.4,  # ≥0.4: رطوبة عالية، لا إجهاد
    "mild": 0.2,  # 0.2–0.4: رطوبة معتدلة
    "moderate": 0.0,  # 0.0–0.2: إجهاد مائي مبدئي
    # <0.0: إجهاد شديد
}

# عتبات MSI (الإجهاد المائي، عكس NDMI) — Hunt & Rock 1989.
# MSI منخفض = صحّي؛ مرتفع = إجهاد. (SWIR1/NIR)
MSI_THRESHOLDS = {
    "healthy": 1.0,  # <1.0: صحّي
    "mild": 1.6,  # 1.0–1.6: إجهاد خفيف
    "moderate": 2.0,  # 1.6–2.0: إجهاد متوسّط
    # >2.0: إجهاد شديد
}


def assess_water_stress_ndmi(ndmi: float | None) -> dict:
    """يحوّل NDMI إلى إشارة إجهاد مائي (حتمي، من الأدبيّات)."""
    if ndmi is None:
        return {
            "signal": StressSignal.UNKNOWN.value,
            "index": "ndmi",
            "detail_ar": "NDMI غير متاح (لا صورة/سحب) — لا إشارة (صدق)",
        }
    if ndmi >= NDMI_THRESHOLDS["healthy"]:
        sig = StressSignal.NONE
    elif ndmi >= NDMI_THRESHOLDS["mild"]:
        sig = StressSignal.MILD
    elif ndmi >= NDMI_THRESHOLDS["moderate"]:
        sig = StressSignal.MODERATE
    else:
        sig = StressSignal.SEVERE
    return {
        "signal": sig.value,
        "index": "ndmi",
        "value": round(ndmi, 3),
        "detail_ar": f"NDMI={ndmi:.2f} → إجهاد مائي {sig.value} (محتوى ماء الغطاء)",
    }


def assess_water_stress_msi(msi: float | None) -> dict:
    """يحوّل MSI إلى إشارة إجهاد مائي (عكس NDMI، Hunt & Rock 1989)."""
    if msi is None:
        return {
            "signal": StressSignal.UNKNOWN.value,
            "index": "msi",
            "detail_ar": "MSI غير متاح — لا إشارة (صدق)",
        }
    if msi < MSI_THRESHOLDS["healthy"]:
        sig = StressSignal.NONE
    elif msi < MSI_THRESHOLDS["mild"]:
        sig = StressSignal.MILD
    elif msi < MSI_THRESHOLDS["moderate"]:
        sig = StressSignal.MODERATE
    else:
        sig = StressSignal.SEVERE
    return {
        "signal": sig.value,
        "index": "msi",
        "value": round(msi, 3),
        "detail_ar": f"MSI={msi:.2f} → إجهاد مائي {sig.value} (مؤشّر الإجهاد)",
    }


def _severity_rank(sig: str) -> int:
    return {"none": 0, "mild": 1, "moderate": 2, "severe": 3, "unknown": -1}.get(sig, -1)


def fuse_water_stress(ndmi: float | None = None, msi: float | None = None) -> dict:
    """يدمج إشارات الرطوبة الطيفيّة (NDMI + MSI) في حكم واحد متّسق.

    لو اتّفقا → ثقة أعلى. لو اختلفا → يُعلَن (قد يكون أحدهما متأثّراً بضوضاء).
    صدق: لو كلاهما غير متاح → unknown (لا اختراع إجهاد).
    """
    a = assess_water_stress_ndmi(ndmi)
    b = assess_water_stress_msi(msi)
    avail = [x for x in (a, b) if x["signal"] != "unknown"]

    if not avail:
        return {
            "fused_signal": StressSignal.UNKNOWN.value,
            "confidence": "none",
            "sources": [a, b],
            "note_ar": "لا مؤشّر رطوبة متاح — لا حكم على الإجهاد المائي (صدق).",
        }

    ranks = [_severity_rank(x["signal"]) for x in avail]
    # نأخذ الأشدّ (احتراز) لكن نُعلن التوافق
    max_rank = max(ranks)
    fused = ["none", "mild", "moderate", "severe"][max_rank]
    agree = len(set(ranks)) == 1 and len(avail) == 2

    if len(avail) == 2:
        conf = "high" if agree else "moderate"
        note = (
            "المؤشّران متّفقان — ثقة عالية."
            if agree
            else "المؤشّران مختلفان قليلاً — أُخذ الأشدّ احترازاً؛ راجع الميدان."
        )
    else:
        conf = "moderate"
        note = f"مؤشّر واحد متاح ({avail[0]['index']}) — ثقة متوسّطة."

    return {
        "fused_signal": fused,
        "confidence": conf,
        "agreement": agree,
        "sources": [a, b],
        "note_ar": note,
        "decision_hint_ar": (
            "إشارة طيفيّة استرشاديّة تُدمَج مع ميزان الماء/التربة. الإجهاد "
            "المتوسّط/الشديد ⇒ راجع جدول الريّ. تبقى الكلمة الأخيرة للقياس الأرضي."
        ),
    }


def index_coverage_report() -> dict:
    """تقرير شفّاف: أيّ مؤشّرات مربوطة بالقرار وأيّها معروض فقط (حوكمة).

    يسدّ فجوة الشفافيّة: يوضّح حالة ربط كلّ مؤشّر (صدق عن النضج).
    """
    return {
        "decision_linked": {
            "ndvi": "صحّة عامّة + اتّجاه (إنذار مبكر) + تقدير الإنتاج",
            "ndre": "إجهاد غذائي (نيتروجين/كلوروفيل)",
            "ndsi": "الملوحة (مربوط بقرار الملوحة عبر المعايرة)",
            "ndwi": "الماء السطحي/رطوبة الغطاء",
            "bsi": "التربة العارية (سياق الغطاء)",
            "ndmi": "الإجهاد المائي (مربوط الآن عبر هذا الجسر) ✓",
            "msi": "الإجهاد المائي (الجسر يدعمه؛ غير محسوب بعد في الشجرة — unknown حتى يُحسَب)",
        },
        "display_or_context_only": {
            "evi": "صحّة محسّنة (مقاومة الغلاف الجوّي) — عرض",
            "savi/msavi": "صحّة مع تصحيح التربة — عرض لكثافة منخفضة",
            "fapar": "الإشعاع الممتصّ — مرشّح لربط الإنتاجيّة مستقبلاً",
            "gli/tgi/vari": "مؤشّرات RGB (طائرات بلا NIR) — عرض",
            "bi/bi2/dbsi/satvi/ndti": "مؤشّرات تربة إضافيّة — سياق/عرض",
            "gndvi": "صحّة (أخضر) — عرض",
        },
        "honesty_note_ar": (
            "شفافيّة الربط: ليست كلّ المؤشّرات المحسوبة مربوطة بالقرار — بعضها "
            "للعرض/السياق. هذا مقصود (تجنّب ضوضاء)، لا نقص. ndmi/msi رُبطا الآن "
            "بقرار الإجهاد المائي (كانا محسوبَين بلا ربط)."
        ),
    }

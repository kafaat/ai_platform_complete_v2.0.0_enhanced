"""
api/index_registry.py — سجلّ المؤشّرات الطيفيّة النباتيّة (Index Registry)

المصدر **الوحيد** لبيانات وصف المؤشّرات الطيفيّة (NDVI/SAVI/GNDVI...). اليوم
تُكتب صيغ المؤشّرات كأكواد مضمّنة (انظر vegetation-analysis-service/main.py،
الدالّة _compute_indices) فكلّ مؤشّر جديد يعني تعديل كود في خدمات الحساب
وقائمة الواجهة معاً. هذا السجلّ يحوّل الوصف إلى **بيانات** (metadata) لا كود:

  • كلّ مؤشّر يُعلَن مرّة واحدة هنا (المعرّف، الأسماء، الصيغة، النطاقات الطيفيّة،
    خريطة الألوان، العتبات، الوحدة، الوصف)
  • خدمات الحساب وطبقة الواجهة (قائمة المؤشّرات) تقرأ من هنا ⇒ إضافة مؤشّر
    جديد = إدخال سطر بيانات واحد فيظهر تلقائيّاً (أساس "أضف مؤشّراً → يظهر").

نطاق هذا الإصدار (PR):
  • يُسلّم **السجلّ + البيانات الوصفيّة** فقط.
  • ربط الحساب الفعلي للراستر (تقييم `formula` على النطاقات الطيفيّة) **متابعة
    لاحقة** — اليوم الحساب لا يزال في _compute_indices؛ هنا نوحّد الوصف فقط.

أمانة البيانات:
  • صيغ ونطاقات ndvi/savi/gndvi مطابقة حرفيّاً لما يُحسب في
    vegetation-analysis-service/main.py (نطاقات Sentinel‑2: B08 الأشعّة القريبة،
    B04 الأحمر، B03 الأخضر، B05 الحافّة الحمراء).
  • المؤشّرات الإضافيّة القياسيّة (ndre/evi/msavi) بصيغها المرجعيّة المعروفة فقط.
  • العتبات **استرشاديّة** بانتظار المعايرة الميدانيّة، أو {} حين لا يتوفّر مصدر
    موثوق — لا عتبات مُختلَقة.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class VegetationIndex:
    """وصف مؤشّر طيفي نباتي واحد (بيانات وصفيّة، لا حساب)."""

    id: str  # المعرّف الفريد المختصر (مثل "ndvi")
    name_ar: str  # الاسم العربي
    name_en: str  # الاسم الإنجليزي
    formula: str  # صيغة قابلة للقراءة بدلالة النطاقات (مثل "(B08 - B04) / (B08 + B04)")
    bands: tuple[str, ...]  # النطاقات الطيفيّة المستخدمة (مثل ("B08", "B04"))
    colormap: str  # معرّف سلّم الألوان المسمّى (مثل "rdylgn")
    units: str  # الوحدة (مثل "dimensionless")
    description_ar: str  # وصف عربي + ملاحظة المصدر/المعايرة
    # العتبات استرشاديّة بانتظار المعايرة الميدانيّة؛ {} حين لا مصدر موثوق.
    thresholds: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name_ar": self.name_ar,
            "name_en": self.name_en,
            "formula": self.formula,
            "bands": self.bands,
            "colormap": self.colormap,
            "units": self.units,
            "description_ar": self.description_ar,
            "thresholds": dict(self.thresholds),
        }


# ملاحظة معايرة مشتركة: العتبات أدناه استرشاديّة بانتظار المعايرة الميدانيّة.
_CALIB_AR = "العتبات استرشاديّة بانتظار المعايرة الميدانيّة، لا قيم نهائيّة."

# السجلّ: مفتاحه المعرّف. الصيغ/النطاقات لـ ndvi/savi/gndvi مطابقة لـ
# vegetation-analysis-service/main.py::_compute_indices؛ البقيّة بصيغ مرجعيّة قياسيّة.
_REGISTRY: dict[str, VegetationIndex] = {
    "ndvi": VegetationIndex(
        id="ndvi",
        name_ar="مؤشّر الغطاء النباتي المعياري",
        name_en="Normalized Difference Vegetation Index",
        # مطابق لـ vegetation-analysis main.py: (B08 - B04) / (B08 + B04 + eps)
        formula="(B08 - B04) / (B08 + B04)",
        bands=("B08", "B04"),
        colormap="rdylgn",
        units="dimensionless",
        description_ar=(
            "حيويّة الغطاء النباتي عبر تباين الأحمر/تحت الأحمر القريب. "
            "مطابق لما يُحسب في vegetation-analysis. " + _CALIB_AR
        ),
        thresholds={"low": 0.2, "healthy": 0.5},
    ),
    "savi": VegetationIndex(
        id="savi",
        name_ar="مؤشّر الغطاء النباتي المصحّح للتربة",
        name_en="Soil-Adjusted Vegetation Index",
        # مطابق لـ vegetation-analysis main.py: (B08 - B04) / (B08 + B04 + 0.5) * 1.5
        # (L = 0.5؛ عامل (1 + L) = 1.5)
        formula="((B08 - B04) / (B08 + B04 + 0.5)) * 1.5",
        bands=("B08", "B04"),
        colormap="rdylgn",
        units="dimensionless",
        description_ar=(
            "كـ NDVI لكن يخفّف أثر انعكاس التربة العارية (L = 0.5) في الغطاء المتفرّق. "
            "مطابق لما يُحسب في vegetation-analysis. " + _CALIB_AR
        ),
        thresholds={},
    ),
    "gndvi": VegetationIndex(
        id="gndvi",
        name_ar="مؤشّر الغطاء النباتي الأخضر المعياري",
        name_en="Green Normalized Difference Vegetation Index",
        # مطابق لـ vegetation-analysis main.py: (B08 - B03) / (B08 + B03 + eps)
        formula="(B08 - B03) / (B08 + B03)",
        bands=("B08", "B03"),
        colormap="rdylgn",
        units="dimensionless",
        description_ar=(
            "يستبدل الأخضر بالأحمر؛ أكثر حسّاسيّة للكلوروفيل وتركيز النيتروجين. "
            "مطابق لما يُحسب في vegetation-analysis. " + _CALIB_AR
        ),
        thresholds={},
    ),
    "evi": VegetationIndex(
        id="evi",
        name_ar="المؤشّر النباتي المحسّن",
        name_en="Enhanced Vegetation Index",
        # مطابق لـ vegetation-analysis main.py:
        # 2.5 * (B08 - B04) / (B08 + 6*B04 - 7.5*B02 + 1)
        formula="2.5 * (B08 - B04) / (B08 + 6 * B04 - 7.5 * B02 + 1)",
        bands=("B08", "B04", "B02"),
        colormap="rdylgn",
        units="dimensionless",
        description_ar=(
            "يصحّح أثر الغلاف الجوي والخلفيّة الترابيّة؛ أقلّ تشبّعاً في الكتلة "
            "الحيويّة العالية. مطابق لما يُحسب في vegetation-analysis. " + _CALIB_AR
        ),
        thresholds={},
    ),
    "ndre": VegetationIndex(
        id="ndre",
        name_ar="مؤشّر الحافّة الحمراء المعياري",
        name_en="Normalized Difference Red Edge",
        # صيغة مرجعيّة قياسيّة (B05 الحافّة الحمراء متاحة في النطاقات):
        formula="(B08 - B05) / (B08 + B05)",
        bands=("B08", "B05"),
        colormap="rdylgn",
        units="dimensionless",
        description_ar=(
            "يستخدم الحافّة الحمراء (B05)؛ أنفذ في الغطاء الكثيف وأحسّ لإجهاد "
            "النيتروجين من NDVI. صيغة مرجعيّة قياسيّة. " + _CALIB_AR
        ),
        thresholds={},
    ),
    "msavi": VegetationIndex(
        id="msavi",
        name_ar="مؤشّر الغطاء النباتي المصحّح للتربة المعدّل",
        name_en="Modified Soil-Adjusted Vegetation Index",
        # صيغة MSAVI2 المرجعيّة القياسيّة:
        formula="(2 * B08 + 1 - sqrt((2 * B08 + 1)^2 - 8 * (B08 - B04))) / 2",
        bands=("B08", "B04"),
        colormap="rdylgn",
        units="dimensionless",
        description_ar=(
            "يضبط عامل تصحيح التربة ذاتيّاً (MSAVI2) بلا ثابت L مفروض. "
            "صيغة مرجعيّة قياسيّة. " + _CALIB_AR
        ),
        thresholds={},
    ),
}


def list_indices() -> list[dict]:
    """كلّ المؤشّرات كقواميس بيانات وصفيّة، مرتّبة بالمعرّف (للواجهة/الخدمات)."""
    return [_REGISTRY[index_id].to_dict() for index_id in sorted(_REGISTRY)]


def get_index(index_id: str) -> dict | None:
    """بيانات مؤشّر بمعرّفه، أو None إن لم يُعرَف."""
    entry = _REGISTRY.get(index_id)
    return entry.to_dict() if entry is not None else None


def known_ids() -> list[str]:
    """معرّفات المؤشّرات المعروفة، مرتّبة."""
    return sorted(_REGISTRY)

"""core/engines/crop_classification_readiness.py — جاهزيّة تصنيف المحاصيل بالأقمار.

السؤال (المستخدم): هل يتعرّف سهول على المحاصيل بالأقمار لتوقّع فجوة السوق؟
الجواب الصادق: ليس الآن — يستخرج مؤشّرات (NDVI/LAI) لا نوع المحصول. المحصول
من إدخال المزارع. تصنيف المحاصيل **ممكن** (دراسات: RF/U-Net دقّة 91-95% على
Sentinel-2) لكن يتطلّب **بيانات تدريب أرضيّة** (ground truth) غير كافية بعد.

هذا المكوّن (البوّابة الصادقة، لا تصنيف وهمي):
  • يقيس كم عيّنة تدريب حقيقيّة تراكمت (حقول المنصّة: crop معروف + GPS + سلسلة)
  • يقرّر متى تصبح كافية للتصنيف (عتبات من الأدبيّات)
  • يربط الحلقة: حقول المنصّة → ground truth → تصنيف → فجوة سوق إقليميّة أدقّ
  • قبل الجاهزيّة: يُعلن بصدق أنّ التصنيف غير متاح (لا يخترع)

⚠ المبدأ (اتّساقاً مع learning_activation + confidence_engine + market_analyzer):
  • مدفوع بالبيانات: العتبة شرط موضوعي (عيّنات/محصول + سلسلة زمنيّة + GPS)
  • صدق: قبل الكفاية، التصنيف "غير متاح" لا "تقديري ضعيف"
  • حتمي: عدّ + عتبات صريحة، لا نموذج يُدرَّب على فراغ
  • لكلّ منطقة مناخيّة (التواقيع الطيفيّة تختلف بالإقليم)

⚠ عتبات الجاهزيّة من الأدبيّات (تقريبيّة، تُضبط ميدانيّاً):
  IARI الهند ~100 حقل؛ Shiyang الصين 268 حقل/16k بكسل؛ بيئة جافّة ~1870 عيّنة.
  نعتمد حدّاً أدنى عمليّاً: ≥30 حقل/محصول + ≥6 مشاهد زمنيّة + GPS دقيق.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ClassificationReadiness(str, Enum):
    NOT_READY = "not_ready"  # عيّنات غير كافية — التصنيف غير متاح
    ACCUMULATING = "accumulating"  # تتراكم — يقترب من الكفاية
    READY = "ready"  # كافية — التصنيف ممكن بثقة معقولة


# عتبات من الأدبيّات (الحدّ الأدنى العملي لبيئة إقليميّة واحدة)
MIN_FIELDS_PER_CROP = 30  # حقول معروفة المحصول لكلّ صنف (ground truth)
MIN_TEMPORAL_SCENES = 6  # مشاهد زمنيّة (multi-temporal حاسم للتصنيف)
MIN_CROPS_FOR_USEFUL_MAP = 3  # أقلّ عدد محاصيل ليكون التصنيف مفيداً
ACCUMULATING_FLOOR = 10  # دون هذا/محصول = not_ready


@dataclass
class CropSampleInventory:
    """جرد عيّنات التدريب المتاحة لمنطقة (من حقول المنصّة)."""

    zone_key: str
    fields_with_crop_and_gps: dict[str, int]  # {crop_id: عدد الحقول بـcrop+GPS}
    avg_temporal_scenes: float  # متوسّط المشاهد الزمنيّة/حقل
    gps_quality_ok: bool  # هل الإحداثيّات دقيقة كفاية؟


def assess_classification_readiness(inv: CropSampleInventory) -> dict:
    """يقرّر جاهزيّة تصنيف المحاصيل بالأقمار لمنطقة (حتمي، صادق).

    قبل الكفاية: يُعلن أنّ التصنيف غير متاح + كم ينقص (لا تصنيف وهمي).
    """
    crops_ready = {
        crop: n for crop, n in inv.fields_with_crop_and_gps.items() if n >= MIN_FIELDS_PER_CROP
    }
    crops_accumulating = {
        crop: n
        for crop, n in inv.fields_with_crop_and_gps.items()
        if ACCUMULATING_FLOOR <= n < MIN_FIELDS_PER_CROP
    }
    total_crops = len(inv.fields_with_crop_and_gps)

    blockers = []
    if len(crops_ready) < MIN_CROPS_FOR_USEFUL_MAP:
        blockers.append(
            f"محاصيل جاهزة {len(crops_ready)} < {MIN_CROPS_FOR_USEFUL_MAP} "
            f"(كلّ محصول يحتاج ≥{MIN_FIELDS_PER_CROP} حقل بـGPS)"
        )
    if inv.avg_temporal_scenes < MIN_TEMPORAL_SCENES:
        blockers.append(
            f"مشاهد زمنيّة {inv.avg_temporal_scenes:.1f} < {MIN_TEMPORAL_SCENES} "
            "(التصنيف يحتاج سلسلة زمنيّة لالتقاط التطوّر الفينولوجي)"
        )
    if not inv.gps_quality_ok:
        blockers.append("دقّة GPS غير كافية لمطابقة البكسلات بالحقول")

    if not blockers:
        state = ClassificationReadiness.READY
    elif crops_accumulating or crops_ready:
        state = ClassificationReadiness.ACCUMULATING
    else:
        state = ClassificationReadiness.NOT_READY

    state_msg = {
        ClassificationReadiness.NOT_READY: (
            "غير متاح — عيّنات تدريب أرضيّة غير كافية. التصنيف بالأقمار يحتاج "
            "حقولاً معروفة المحصول كـground truth (لا نخترع تصنيفاً)."
        ),
        ClassificationReadiness.ACCUMULATING: (
            "تتراكم — عيّنات حقول المنصّة تنمو. كلّما سُجّلت حقول أكثر بمحاصيلها "
            "ومواقعها، اقترب التصنيف من الجاهزيّة."
        ),
        ClassificationReadiness.READY: (
            "جاهز — عيّنات كافية لتدريب مصنّف (RF/U-Net) على هذه المنطقة. "
            "يمكن تصنيف المحاصيل بالأقمار ثمّ تغذية فجوة السوق الإقليميّة."
        ),
    }[state]

    return {
        "zone_key": inv.zone_key,
        "state": state.value,
        "state_ar": state_msg,
        "crops_ready": list(crops_ready.keys()),
        "crops_accumulating": list(crops_accumulating.keys()),
        "total_crops_tracked": total_crops,
        "avg_temporal_scenes": round(inv.avg_temporal_scenes, 1),
        "blockers": blockers,
        "can_classify": state == ClassificationReadiness.READY,
        "honesty_note_ar": (
            "تصنيف المحاصيل بالأقمار ممكن علميّاً (دقّة 91-95% بـRF/U-Net على "
            "Sentinel-2) لكنّه يتطلّب بيانات تدريب أرضيّة. سهول يجمعها تدريجيّاً "
            "من حقول المنصّة (محصول معروف + GPS). قبل الكفاية: لا تصنيف (لا اختراع)."
        ),
        "link_to_market_gap_ar": (
            "عند الجاهزيّة: التصنيف يوسّع crop_market_gap من 'حقول المنصّة' إلى "
            "'كلّ المنطقة' (يشمل غير المشتركين) → فجوة سوق أدقّ وأشمل."
        ),
    }


def readiness_roadmap(inventories: list[CropSampleInventory]) -> dict:
    """خارطة جاهزيّة التصنيف عبر المناطق — أين نقترب، أين نحتاج عيّنات."""
    assessed = [assess_classification_readiness(inv) for inv in inventories]
    ready_zones = [a for a in assessed if a["can_classify"]]
    return {
        "total_zones": len(inventories),
        "ready_zones": len(ready_zones),
        "per_zone": assessed,
        "strategic_note_ar": (
            "الطريق لتوقّع فجوة السوق بالأقمار: (١) سجّل حقولاً بمحاصيلها+GPS، "
            "(٢) راكم سلاسل زمنيّة، (٣) عند الكفاية درّب مصنّفاً للمنطقة، "
            "(٤) صنّف كلّ المنطقة، (٥) اكشف التشبّع/الفجوة على مستوى الإقليم. "
            "كلّ خطوة مدفوعة بالبيانات — لا قفز فوق ما لا نملكه."
        ),
    }

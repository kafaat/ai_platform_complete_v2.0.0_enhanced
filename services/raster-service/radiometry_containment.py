"""radiometry_containment.py — احتواءُ مسار Element84→VRT حتّى يُبنى عقدُ التطبيع.

``stac_vrt.build_band_vrt`` يكدّس COGs نطاقات Element84 في VRT ثمّ يُحسَب المؤشّر منه.
ثبت بالقياس (مراجعة مستقلّة على ``d6488d89`` + إعادة إنتاج على شجرة المستودع) أنّ هذا
المسار لا يُنتِج قيماً صالحة، لثلاثة أسباب مستقلّة لا يُصلحها أحدُها وحده:

* **المقياس** — الـVRT يحمل ``scale=1.0``/``offset=0`` (رأسُ COG الحقيقيّ نفسُه لا يحمل
  المقياس؛ هو في ``raster:bands`` الذي لا يُقرأ)، فتُحسَب المؤشّرات ذات الثوابت الجمعيّة
  على DN خام: EVI 0.952 بدل 0.328 على شاهدٍ معلوم، وSATVI -899.5 بدل 0.0975. وقناعُ
  التشبّع (>1.20) يرفض DN الخام كلَّه فيصير المشهدُ الصافي 422.
* **المحاذاة** — أبعادُ النطاق الأوّل وتحويلُه تُفرَض على كلّ المصادر (``SrcRect`` و
  ``DstRect`` واحدان)، فنطاقاتُ 20م (``scl``/``swir1``/``swir2``/``rededge``) تُرسَم على
  ربع الشبكة والباقي أصفار.
* **NoData** — لا ``NoDataValue`` في الـVRT، فالبكسلُ المفقود (0) يُعدّ صالحاً ويُخفِّض
  المتوسّط (أربعة «صالحة» بمتوسّط 0.125 بدل بكسلٍ واحد بـ0.5).

الاحتواء رفضٌ صريح **قبل** بناء الـVRT وقبل أيّ معالجة أو كتابة COG أو حفظ أصل، بحمولةٍ
منظَّمة ``radiometry_unresolved``. وهو **دائمٌ لنسخة المعالجة هذه**: لا يُعاد تلقائيّاً،
ولا يُسجَّل المنتجُ ``ready``، ولا يُقرأ مشهداً فارغاً أو منخفضَ الجودة. رفعُه يأتي مع
عقد التطبيع والمحاذاة وNoData — لا بتمرير المقياس وحده.

الاحتواء **لا يُغلق** العيوب ولا يُصحّح المنتجات القديمة؛ سجلُّ الفجوات يبقى مفتوحاً.
"""

from __future__ import annotations

from typing import NoReturn

RADIOMETRY_UNRESOLVED = "radiometry_unresolved"

# بادئةُ سبب العنصر في ``backfill_run_items.error`` — يقرؤها مسارُ إعادة الصفّ كي لا يُعيد
# عنصراً محجوباً إلى ``queued`` في التشغيلة التالية (الفشلُ دائمٌ لهذه النسخة).
ITEM_ERROR = f"{RADIOMETRY_UNRESOLVED}:element84_vrt"

# نطاقاتُ Sentinel-2 بدقّة 20م كما تسمّيها ``stac_search.band_urls_from_assets``.
_TWENTY_METRE_BANDS = ("rededge", "swir1", "swir2", "scl")

GAP_IDS = (
    "ELEMENT84-VRT-REFLECTANCE-SCALE-NOT-APPLIED-01",
    "ELEMENT84-VRT-BAND-GRID-MISALIGNED-01",
    "ELEMENT84-VRT-NODATA-NOT-PROPAGATED-01",
)


class RadiometryUnresolved(Exception):
    """رفضٌ منظَّم: المسار لا يملك تحويلاً إشعاعيّاً محسوماً. ``detail`` حمولةٌ قابلة للقراءة آليّاً."""

    def __init__(self, detail: dict) -> None:
        self.detail = detail
        super().__init__(detail.get("code", RADIOMETRY_UNRESOLVED))


def element84_vrt_detail(band_keys, *, entry_point: str) -> dict:
    """حمولةُ الرفض لمجموعة نطاقات. ``band_keys`` أسماءٌ لا روابط — لا يُعاد href إلى العميل.

    سببا المقياس وNoData قائمان لكلّ طلب؛ وسببُ المحاذاة يُذكَر حين يضمّ الطلبُ نطاقاً بدقّة
    20م فقط، مع أسماء تلك النطاقات — فالسببُ وقائعُ الطلب لا قائمةٌ ثابتة.
    """
    keys = sorted({str(k) for k in (band_keys or ()) if k})
    reasons: list[dict] = [
        {
            "code": "reflectance_scale_unresolved",
            "detail": "VRT يحمل scale=1/offset=0 ولا يُقرأ raster:bands؛ مؤشّرات EVI/MSAVI/SAVI/"
            "TGI/BI/BI2/SATVI تُحسَب على DN خام، وقناع التشبّع يرفضها",
        },
        {
            "code": "nodata_not_propagated",
            "detail": "VRT بلا NoDataValue؛ البكسل المفقود (0) يُعدّ صالحاً",
        },
    ]
    misaligned = [b for b in _TWENTY_METRE_BANDS if b in keys]
    if misaligned:
        reasons.insert(
            1,
            {
                "code": "band_grid_misaligned",
                "detail": "أبعاد النطاق الأوّل تُفرَض على كلّ المصادر؛ نطاقات 20م لا تُعاد عيّنتها",
                "bands": misaligned,
            },
        )
    return {
        "code": RADIOMETRY_UNRESOLVED,
        "provider": "element84",
        "path": "stac_vrt",
        "entry_point": entry_point,
        "bands": keys,
        "reasons": reasons,
        "retryable": False,
        "gap_ids": list(GAP_IDS),
        "note_ar": (
            "مسار Element84→VRT محجوب حتّى يُبنى عقد التطبيع والمحاذاة وNoData؛ "
            "لا معالجة ولا حفظ لهذا الطلب، والفشل دائم لنسخة المعالجة الحاليّة."
        ),
    }


def reject_element84_vrt(band_keys, *, entry_point: str) -> NoReturn:
    """يرفض الطلب قبل بناء الـVRT. يُستدعى في كلّ نقطة دخول كانت تبني VRT من نطاقات Element84."""
    raise RadiometryUnresolved(element84_vrt_detail(band_keys, entry_point=entry_point))


def single_scene_detail(result: dict) -> dict:
    """حمولة 422 لـ``/imagery/process-date`` حين يكون العنصر فشلاً دائماً لهذه النسخة.

    مراجعة Copilot على #1135: ذلك المسار كان يمسح الخطأ ويُعيد العنصر إلى ``queued``،
    فيُكسَر وعد «الفشل دائمٌ لنسخة المعالجة». الآن يُرفَض بلا تشغيلة جديدة.
    """
    return {
        "code": RADIOMETRY_UNRESOLVED,
        "entry_point": "process_date",
        "retryable": False,
        "item_id": result.get("item_id"),
        "run_id": result.get("run_id"),
        "previous_error": result.get("error"),
        "note_ar": (
            "المشهد فشل فشلاً دائماً لنسخة المعالجة الحاليّة (مسار Element84→VRT محجوب حتّى "
            "عقد التطبيع) — لا إعادة محاولة بالنقر."
        ),
    }

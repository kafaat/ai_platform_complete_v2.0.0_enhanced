"""imagery_product_identity.py — كائن القيمة القانونيّ الوحيد لهويّة منتج الصور (V8-05 PR1-b).

مصدرٌ واحد لبناء الهويّة عبر كلّ المسارات (idempotency لعناصر backfill الجماعيّ ومسار
single_scene · فحص الأصل الجاهز · هويّة منتج الراستر ومنع التكرار). أيّ تمثيل نصّيّ مختلف
تحتاجه عقود التخزين يُشتقّ من هذا الكائن نفسه لا بإعادة تركيب الحقول يدويّاً في أكثر من موضع.

الحقول السبعة القانونيّة:
    tenant_id · field_id · geometry_revision · provider · scene_id · product · processing_version

صدق صارم:
  • ``processing_version`` يأتي من مسار المعالجة القانونيّ (``canonical_processing_version``)،
    لا من قيمة يرسلها العميل بحرّيّة.
  • ``provider`` و``product`` يُطبَّعان قبل توليد المفتاح (اسم قانونيّ واحد).
  • **لا** استعمال ``hash()`` المدمج (غير مستقرّ بين العمليّات) — تسلسل حتميّ + SHA-256 عند الحاجة.
  • الهويّة v2 مُصدَّرة صراحةً (بادئة ``v2``) — الكتابات الجديدة تستعملها وحدها؛ القراءة
    dual-read (v2 ثمّ المفتاح القديم عند إمكان إثبات التطابق دون غموض).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

IDENTITY_VERSION = "v2"

# أسماء مزوّدين قانونيّة (تطبيع مرادفات شائعة ⇒ اسم واحد).
_PROVIDER_ALIASES = {
    "sentinel-2": "cdse",
    "sentinel2": "cdse",
    "sentinelhub": "cdse",
    "sentinel-hub": "cdse",
    "copernicus": "cdse",
    "cdse": "cdse",
    "element84": "element84",
    "earth-search": "element84",
    "landsat": "landsat-element84",
    "landsat-element84": "landsat-element84",
    "landsat-thermal": "landsat-element84",
}


def normalize_provider(provider: str | None) -> str:
    """اسم مزوّد قانونيّ (حروف صغيرة، بلا فراغات، مرادفات مُوحَّدة). فراغ ⇒ ``unknown``."""
    p = str(provider or "").strip().lower()
    if not p:
        return "unknown"
    return _PROVIDER_ALIASES.get(p, p)


def normalize_product(product: str | None) -> str:
    """اسم منتَج/مؤشّر قانونيّ (حروف صغيرة، بلا فراغات)."""
    return str(product or "").strip().lower()


def canonical_processing_version(explicit: str | None = None) -> str:
    """إصدار المعالجة القانونيّ — من مسار المعالجة لا من العميل.

    الافتراض إصدار خوارزميّة band-math القانونيّ (``raster_quality.ALGORITHM_VERSION``).
    ``explicit`` يُمرَّر فقط من مسار خادميّ يعرف إصداره؛ لا من مدخل عميل.
    """
    if explicit:
        return str(explicit)
    try:
        import raster_quality

        return str(raster_quality.ALGORITHM_VERSION)
    except Exception:  # noqa: BLE001 — غياب الوحدة (اختبار) ⇒ إصدار أساس ثابت
        return "sahool.band_math/1"


@dataclass(frozen=True)
class ImageryProductIdentity:
    """هويّة منتج صور غير قابلة للتغيير — الحقول السبعة القانونيّة (مُطبَّعة)."""

    tenant_id: str
    field_id: str
    geometry_revision: int | None
    provider: str
    scene_id: str
    product: str
    processing_version: str

    @classmethod
    def create(
        cls,
        *,
        tenant_id,
        field_id,
        geometry_revision,
        provider,
        scene_id,
        product,
        processing_version,
    ) -> ImageryProductIdentity:
        """يبني الهويّة مع التطبيع (المسار الوحيد المسموح لبناء الهويّة)."""
        return cls(
            tenant_id=str(tenant_id or ""),
            field_id=str(field_id or ""),
            geometry_revision=(int(geometry_revision) if geometry_revision is not None else None),
            provider=normalize_provider(provider),
            scene_id=str(scene_id or ""),
            product=normalize_product(product),
            processing_version=str(processing_version or ""),
        )

    def _ordered_fields(self) -> dict:
        # ترتيب حتميّ صريح — لا يعتمد على ترتيب إدراج الحقول.
        return {
            "v": IDENTITY_VERSION,
            "tenant_id": self.tenant_id,
            "field_id": self.field_id,
            "geometry_revision": self.geometry_revision
            if self.geometry_revision is not None
            else 0,
            "provider": self.provider,
            "scene_id": self.scene_id,
            "product": self.product,
            "processing_version": self.processing_version,
        }

    def to_canonical_key(self) -> str:
        """مفتاح idempotency القانونيّ (نصّ حتميّ ببادئة v2) — لعناصر backfill (جماعيّ+single_scene)."""
        f = self._ordered_fields()
        return ":".join(
            [
                str(f["v"]),
                f["tenant_id"],
                f["field_id"],
                str(f["geometry_revision"]),
                f["provider"],
                f["scene_id"],
                f["product"],
                f["processing_version"],
            ]
        )

    def content_hash(self) -> str:
        """بصمة SHA-256 حتميّة (تسلسل مُرتَّب المفاتيح) — لعقود التخزين التي تحتاج تمثيلاً مُجزَّأً."""
        raw = json.dumps(self._ordered_fields(), sort_keys=True, separators=(",", ":"))
        return "ipk2_" + hashlib.sha256(raw.encode()).hexdigest()

    def legacy_backfill_key(self) -> str:
        """المفتاح القديم (قبل v2): ``tenant:field:geom:provider:scene:product`` بلا processing_version.

        للـdual-read فقط (اكتشاف عنصر قديم عند إمكان إثبات التطابق) — لا يُكتَب أبداً.
        """
        geom = self.geometry_revision if self.geometry_revision is not None else 0
        return f"{self.tenant_id}:{self.field_id}:{geom}:{self.provider}:{self.scene_id}:{self.product}"

    def legacy_matches_baseline(self) -> bool:
        """هل يجوز إعادة استعمال عنصر قديم (بلا processing_version)؟ فقط إذا كان الإصدار الحاليّ
        هو إصدار الأساس القانونيّ الذي أُنشئت تحته السجلّات القديمة — وإلّا فالتطابق غامض (لا نعيد الاستعمال)."""
        return self.processing_version == canonical_processing_version()

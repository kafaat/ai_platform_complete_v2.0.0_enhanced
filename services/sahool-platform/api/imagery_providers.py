"""api/imagery_providers.py — سجلّ بيانات‑وصفيّة لمزوّدي الصور (Imagery Providers).

لماذا هذا السجلّ؟
  اليوم مصدر الصور **مُثبَّت برمجيّاً** على Sentinel‑2: مسار السحب الفعليّ
  (api/imagery_automation.py → raster-service /v1/imagery/search → مجموعة STAC
  "sentinel-2-l2a" على Element84 Earth Search) لا يعرف سوى Sentinel‑2.
  إضافة مزوّد جديد (Planet / Landsat / طائرة مسيّرة) تتطلّب اليوم تعديل كود.

  هذا الملفّ يجعلها **تغييراً في البيانات لا في الكود**: مصدر وحيد للحقيقة
  لبيانات مزوّدي الصور الوصفيّة (النطاقات، الدقّة، دورة الإعادة، النوع، الحالة).
  طبقة السحب يُفترض أن **تختار** مزوّداً من هذا السجلّ مستقبلاً (متابعة).

مبدأ الصدق:
  - Sentinel‑2 فقط هو الموصول فعليّاً اليوم ⇒ status="active".
  - Planet / Landsat‑8 / الطائرة المسيّرة نقاط توسّع **مخطّطة** (status="planned")
    ببيانات معروفة صحيحة، لكنّها **غير موصولة** — لا تلفيق لربط لا وجود له.

هذا الملفّ نقيّ: لا قاعدة بيانات، لا شبكة، لا حالة عامّة قابلة للتغيير.
"""

from __future__ import annotations

from dataclasses import dataclass

# المجموعات المسموحة (للتحقّق والتوثيق)
_ALLOWED_KINDS = ("satellite", "drone", "aerial")
_ALLOWED_STATUSES = ("active", "planned", "unavailable")


@dataclass(frozen=True)
class ImageryProvider:
    """بيانات وصفيّة لمزوّد صور واحد (غير قابل للتعديل).

    الحقول:
      id          معرّف مستقرّ (مثل "sentinel2") يُستخدم مفتاحاً.
      name_ar     الاسم بالعربيّة.
      name_en     الاسم بالإنجليزيّة.
      bands       النطاقات الطيفيّة المتاحة (tuple ثابت).
      resolution_m  الدقّة المكانيّة بالأمتار (None إن متغيّرة/غير معرّفة).
      revisit_days  دورة إعادة الزيارة بالأيّام (None إن متغيّرة/عند الطلب).
      kind        نوع المنصّة: "satellite" | "drone" | "aerial".
      status      الحالة: "active" (موصول) | "planned" (مخطّط) | "unavailable".
      notes_ar    ملاحظات عربيّة (سياق الصدق: ما هو موصول وما هو مخطّط).
    """

    id: str
    name_ar: str
    name_en: str
    bands: tuple[str, ...]
    resolution_m: float | None
    revisit_days: int | None
    kind: str
    status: str
    notes_ar: str


# ─────────────────────────────────────────────────────────────────────────────
# السجلّ — مصدر وحيد للحقيقة. مرتّب: النشِط أوّلاً ثمّ المخطّط.
# ─────────────────────────────────────────────────────────────────────────────
_REGISTRY: tuple[ImageryProvider, ...] = (
    # المزوّد الوحيد الموصول فعليّاً اليوم.
    # الأرقام مؤصَّلة في حقائق Sentinel‑2 L2A:
    #   B02/B03/B04 (أزرق/أخضر/أحمر) و B08 (NIR) بدقّة 10م،
    #   B05 (حافّة حمراء/red-edge) بدقّة 20م. نُدرج 10م كدقّة أساس (النطاقات
    #   المستخدمة في NDVI). دورة الإعادة ~5 أيّام (قمران Sentinel‑2A/2B).
    ImageryProvider(
        id="sentinel2",
        name_ar="سنتينل-2",
        name_en="Sentinel-2",
        bands=("B02", "B03", "B04", "B08", "B05"),
        resolution_m=10.0,
        revisit_days=5,
        kind="satellite",
        status="active",
        notes_ar=(
            "المزوّد الوحيد الموصول فعليّاً: raster-service يبحث مجموعة STAC "
            "'sentinel-2-l2a' على Element84 Earth Search. B02-04/B08 دقّتها 10م، "
            "B05 دقّتها 20م، ودورة الإعادة ~5 أيّام (Sentinel-2A/2B)."
        ),
    ),
    # ── نقاط توسّع مخطّطة (غير موصولة) ببيانات معروفة صحيحة ──
    ImageryProvider(
        id="landsat8",
        name_ar="لاندسات-8",
        name_en="Landsat 8",
        # OLI: ساحلي/أزرق/أخضر/أحمر/NIR/SWIR1/SWIR2
        bands=("B1", "B2", "B3", "B4", "B5", "B6", "B7"),
        resolution_m=30.0,
        revisit_days=16,
        kind="satellite",
        status="planned",
        notes_ar=(
            "مخطّط (غير موصول). Landsat-8 OLI بدقّة 30م ودورة إعادة 16 يوماً. "
            "مجموعة 'landsat-c2-l2' متاحة على Element84 لكنّ مسار السحب لا يستخدمها بعد."
        ),
    ),
    ImageryProvider(
        id="planet",
        name_ar="بلانيت (PlanetScope)",
        name_en="PlanetScope",
        bands=("blue", "green", "red", "nir"),
        resolution_m=3.0,
        revisit_days=1,
        kind="satellite",
        status="planned",
        notes_ar=(
            "مخطّط (غير موصول). PlanetScope بدقّة ~3م وتغطية شبه يوميّة، "
            "لكنّه تجاريّ يتطلّب مفتاحاً وتكاملاً منفصلاً (غير منجَز)."
        ),
    ),
    ImageryProvider(
        id="drone",
        name_ar="طائرة مسيّرة",
        name_en="Drone / UAV",
        # نطاقات وأرقام متغيّرة حسب الحمولة والمهمّة ⇒ None قصداً.
        bands=("red", "green", "blue"),
        resolution_m=None,
        revisit_days=None,
        kind="drone",
        status="planned",
        notes_ar=(
            "مخطّط (غير موصول). الدقّة ودورة الزيارة متغيّرتان حسب الحمولة وارتفاع "
            "الطيران والمهمّة (عند الطلب، لا دورة ثابتة)."
        ),
    ),
)


def list_providers() -> tuple[ImageryProvider, ...]:
    """يُرجِع كلّ المزوّدين المسجَّلين (نشِط + مخطّط) بترتيب السجلّ."""
    return _REGISTRY


def get_provider(provider_id: str) -> ImageryProvider | None:
    """يُرجِع مزوّداً بمعرّفه، أو None إن لم يوجد (لا استثناء)."""
    for provider in _REGISTRY:
        if provider.id == provider_id:
            return provider
    return None


def active_providers() -> tuple[ImageryProvider, ...]:
    """يُرجِع المزوّدين الموصولين فعليّاً (status="active") — اليوم: Sentinel‑2 فقط."""
    return tuple(p for p in _REGISTRY if p.status == "active")


def for_kind(kind: str) -> tuple[ImageryProvider, ...]:
    """يُرجِع المزوّدين من نوع منصّة معيّن ("satellite" | "drone" | "aerial")."""
    return tuple(p for p in _REGISTRY if p.kind == kind)

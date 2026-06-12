"""core/engines/field_workspace.py — تجميع «مساحة عمل الحقل» (طبقات + خطّ زمنيّ).

مستلهَم من نمط John Deere (Monitor + Analyze) و Climate FieldView (الخريطة محور
+ طبقات قابلة للتبديل + خطّ زمنيّ للعمليّات) — لكن **بنمط سهول الصادق**:

⚠ المبدأ:
  • طبقة **عرض/تجميع** صرفة (display_only) — لا تفرض قراراً ولا تخترع بيانات
  • **توفّر صادق**: كلّ طبقة تُعلن إن كانت متاحة الآن (من أعمدة الحقل) أو عند
    الطلب (صور الأقمار) أو غير متوفّرة — لا تلوين مفبرك لطبقة بلا بيانات
  • الخطّ الزمنيّ من **الأحداث المسجّلة فقط** (لا تاريخ مخترَع)
  • حتميّ بالكامل: تجميع وتطبيع، لا نموذج

⚠ النواة هنا نقيّة (تأخذ بيانات مُجمَّعة وتشكّلها) — الجلب من القاعدة في الـendpoint.
"""

from __future__ import annotations

# ── كتالوج الطبقات المتاحة في سهول (معرفة طبقات العرض) ───────────────────
# كلّ طبقة: المفتاح، تسميتها، فئتها، والعمود/الشرط الذي يُتيحها.
LAYER_CATALOG: list[dict] = [
    {"key": "ndvi", "label_ar": "صحّة الغطاء (NDVI)", "category": "vegetation", "source": "imagery"},
    {
        "key": "ndmi",
        "label_ar": "رطوبة الغطاء (NDMI)",
        "category": "vegetation",
        "source": "imagery",
    },
    {"key": "elevation", "label_ar": "الارتفاع", "category": "terrain", "field_col": "elevation_m"},
    {"key": "slope", "label_ar": "المنحدر", "category": "terrain", "field_col": "slope_pct"},
    {"key": "aspect", "label_ar": "الاتّجاه", "category": "terrain", "field_col": "aspect"},
    {"key": "soil_type", "label_ar": "نوع التربة", "category": "soil", "field_col": "soil_type"},
    {"key": "salinity", "label_ar": "الملوحة (EC)", "category": "soil", "field_col": "water_ec"},
    {
        "key": "irrigation",
        "label_ar": "نظام الريّ",
        "category": "water",
        "field_col": "irrigation_type",
    },
]

# تطبيع أنواع الأحداث إلى تسمية عمليّة عربيّة + فئة (لبطاقات الخطّ الزمنيّ).
# المفتاح = بادئة event_type المخزَّن (event_bus EventType.value).
_EVENT_PREFIX_AR: list[tuple[str, str, str]] = [
    ("field.created", "إنشاء الحقل", "land"),
    ("field.updated", "تحديث بيانات الحقل", "land"),
    ("field.geometry", "تعديل حدود الحقل", "land"),
    ("season.created", "بدء موسم", "season"),
    ("planting", "زراعة", "planting"),
    ("irrigation", "ريّ", "irrigation"),
    ("fertilizer", "تسميد", "fertilization"),
    ("pesticide", "رشّ مبيد", "spraying"),
    ("harvest", "حصاد", "harvest"),
    ("lifecycle", "انتقال مرحلة", "lifecycle"),
    ("activity", "نشاط ميدانيّ", "other"),
]


def _op_label(event_type: str) -> tuple[str, str]:
    """يحوّل event_type المخزَّن إلى (تسمية عربيّة، فئة) — حتميّ."""
    et = (event_type or "").lower()
    for prefix, label_ar, category in _EVENT_PREFIX_AR:
        if et.startswith(prefix):
            return label_ar, category
    return event_type or "حدث", "other"


def layer_availability(field: dict) -> list[dict]:
    """يحدّد توفّر كلّ طبقة من أعمدة الحقل — صادق (متاح/عند الطلب/غير متوفّر)."""
    layers = []
    for spec in LAYER_CATALOG:
        if spec.get("source") == "imagery":
            # طبقات الأقمار: تُجلب عند الطلب إن توفّرت صورة صافية — لا تُخزَّن.
            status, available = "on_demand", False
            note = "يُجلب من الأقمار عند الطلب (إن توفّرت صورة صافية) — لا تلوين مفبرك."
        else:
            val = field.get(spec["field_col"])
            available = val is not None and val != ""
            status = "available" if available else "missing"
            if available:
                note = "متاحة من بيانات الحقل."
            elif spec["category"] == "terrain":
                # DEM يملأ التضاريس فقط (ارتفاع/منحدر/اتّجاه).
                note = "غير متوفّرة — أدخِلها (PATCH /api/v1/fields/{field_id}) أو املأها من DEM."
            else:
                note = "غير متوفّرة — أدخِل القيمة (PATCH /api/v1/fields/{field_id})."
        layers.append(
            {
                "key": spec["key"],
                "label_ar": spec["label_ar"],
                "category": spec["category"],
                "available": available,
                "status": status,
                "display_only": True,
                "note_ar": note,
            }
        )
    return layers


def normalize_timeline(events: list[dict]) -> list[dict]:
    """يطبّع أحداثاً مسجّلة إلى بطاقات خطّ زمنيّ (مرتّبة الأحدث أوّلاً).

    events: عناصر فيها event_type و occurred_at (+ issue_tags اختياريّاً).
    من الأحداث المسجّلة فقط — لا تاريخ مخترَع.
    """
    cards = []
    for e in events:
        op_ar, category = _op_label(e.get("event_type", ""))
        tags = e.get("issue_tags")
        if not isinstance(tags, list):  # None/نوع غير صالح → [] (عقد المستهلك: قائمة دائماً)
            tags = []
        cards.append(
            {
                "occurred_at": e.get("occurred_at", ""),
                "event_type": e.get("event_type", ""),
                "op_ar": op_ar,
                "category": category,
                "issue_tags": tags,
            }
        )
    # الأحدث أوّلاً (نمط الخطّ الزمنيّ)؛ ثابت ومستقرّ.
    cards.sort(key=lambda c: c["occurred_at"], reverse=True)
    return cards


def assemble_workspace(field: dict, terrain: dict | None, events: list[dict]) -> dict:
    """يجمّع مساحة عمل الحقل: ملخّص + طبقات قابلة للتبديل + خطّ زمنيّ (عرض صرف)."""
    layers = layer_availability(field)
    timeline = normalize_timeline(events)
    available_layers = [lyr["key"] for lyr in layers if lyr["available"]]
    return {
        "field_id": field.get("field_id"),
        "display_only": True,  # تجميع عرض — لا قرار
        "field": {
            "name_ar": field.get("name"),
            "crop": field.get("crop"),
            "area_ha": field.get("area_ha"),
            "soil_type": field.get("soil_type"),
        },
        "layers": layers,
        "available_layer_count": len(available_layers),
        "terrain": terrain,  # تفسير التضاريس (enrich_terrain) إن توفّر
        "timeline": timeline,
        "timeline_total": len(timeline),
        "honesty_note_ar": (
            "مساحة عرض تجميعيّة (مستلهَمة من نمط FieldView/John Deere): الخريطة محور، "
            "طبقات قابلة للتبديل، وخطّ زمنيّ للعمليّات. كلّ طبقة تُعلن توفّرها بصدق "
            "(متاحة/عند الطلب/غير متوفّرة) — لا تلوين مفبرك. الخطّ الزمنيّ من أحداث "
            "مسجّلة فقط. طبقة عرض لا تفرض قراراً."
        ),
    }

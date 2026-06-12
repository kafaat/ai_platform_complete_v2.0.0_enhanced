"""اختبارات البوّابة الصادقة لتصنيف المحاصيل بالأقمار (offline صرف — بلا قاعدة/شبكة).

تتحقّق من العقد:
  • عيّنات غير كافية ⇒ NOT_READY، لا تصنيف، مُفصِح عمّا ينقص (لا اختراع تصنيف)
  • كفاية كاملة (≥3 محاصيل × ≥30 حقل + ≥6 مشاهد + GPS) ⇒ READY، يمكن التصنيف
  • محاصيل جاهزة لكن مشاهد زمنيّة ناقصة ⇒ ACCUMULATING لا READY (البوّابة لا تقفز)
  • أرضيّة التراكم (10≤n<30) ⇒ ACCUMULATING
  • readiness_roadmap يعدّ المناطق الجاهزة بدقّة

المبدأ المُتحقَّق منه: قبل الكفاية، التصنيف "غير متاح" حتميّاً — لا تقدير ضعيف.
"""

from core.engines.crop_classification_readiness import (
    ACCUMULATING_FLOOR,
    MIN_CROPS_FOR_USEFUL_MAP,
    MIN_FIELDS_PER_CROP,
    MIN_TEMPORAL_SCENES,
    ClassificationReadiness,
    CropSampleInventory,
    assess_classification_readiness,
    readiness_roadmap,
)

# ─── حالات مساعدة ────────────────────────────────────────────────────────


def _ready_inventory(zone_key: str = "zone_ready") -> CropSampleInventory:
    """جرد كافٍ تماماً: ≥3 محاصيل كلّ منها ≥30 حقل + مشاهد كافية + GPS سليم."""
    return CropSampleInventory(
        zone_key=zone_key,
        fields_with_crop_and_gps={
            "wheat": MIN_FIELDS_PER_CROP,
            "barley": MIN_FIELDS_PER_CROP + 5,
            "sorghum": MIN_FIELDS_PER_CROP + 10,
        },
        avg_temporal_scenes=float(MIN_TEMPORAL_SCENES),
        gps_quality_ok=True,
    )


# ─── عيّنات غير كافية ⇒ NOT_READY ────────────────────────────────────────


def test_empty_inventory_is_not_ready():
    # لا عيّنات ⇒ التصنيف غير متاح بصدق، لا اختراع
    inv = CropSampleInventory(
        zone_key="empty",
        fields_with_crop_and_gps={},
        avg_temporal_scenes=0.0,
        gps_quality_ok=False,
    )
    out = assess_classification_readiness(inv)
    assert out["state"] == ClassificationReadiness.NOT_READY.value
    assert out["can_classify"] is False
    assert out["blockers"], "يجب أن يُفصِح عمّا ينقص"
    assert out["crops_ready"] == []
    assert out["crops_accumulating"] == []
    assert out["total_crops_tracked"] == 0


def test_honesty_and_market_gap_notes_present():
    # ملاحظتا الصدق والربط بفجوة السوق موجودتان دائماً
    out = assess_classification_readiness(_ready_inventory())
    assert out["honesty_note_ar"]
    assert out["link_to_market_gap_ar"]


# ─── كفاية كاملة ⇒ READY ─────────────────────────────────────────────────


def test_sufficient_inventory_becomes_ready():
    # ≥3 محاصيل × ≥30 حقل + ≥6 مشاهد + GPS ⇒ جاهز، يمكن التصنيف
    out = assess_classification_readiness(_ready_inventory())
    assert out["state"] == ClassificationReadiness.READY.value
    assert out["can_classify"] is True
    assert out["blockers"] == []
    assert len(out["crops_ready"]) == 3
    assert set(out["crops_ready"]) == {"wheat", "barley", "sorghum"}


# ─── البوّابة لا تقفز: مشاهد ناقصة ⇒ ACCUMULATING لا READY ────────────────


def test_ready_crops_but_low_temporal_is_accumulating_not_ready():
    # محاصيل جاهزة (≥3 × ≥30) لكن المشاهد الزمنيّة دون العتبة ⇒ ACCUMULATING
    inv = _ready_inventory("zone_low_temporal")
    inv.avg_temporal_scenes = float(MIN_TEMPORAL_SCENES - 1)
    out = assess_classification_readiness(inv)
    assert out["state"] == ClassificationReadiness.ACCUMULATING.value
    assert out["can_classify"] is False
    assert out["blockers"], "حاجز المشاهد الزمنيّة يجب أن يُذكر"
    # المحاصيل جاهزة فعلاً لكنّ الحالة ليست READY بسبب الحاجز
    assert len(out["crops_ready"]) == 3


def test_ready_crops_but_bad_gps_is_accumulating_not_ready():
    # محاصيل جاهزة + مشاهد كافية لكن GPS غير دقيق ⇒ ACCUMULATING لا READY
    inv = _ready_inventory("zone_bad_gps")
    inv.gps_quality_ok = False
    out = assess_classification_readiness(inv)
    assert out["state"] == ClassificationReadiness.ACCUMULATING.value
    assert out["can_classify"] is False
    assert any("GPS" in b for b in out["blockers"])
    assert len(out["crops_ready"]) == 3


def test_too_few_distinct_ready_crops_is_accumulating():
    # محصولان جاهزان فقط (<3) رغم اكتمال المشاهد وGPS ⇒ ليست READY
    inv = CropSampleInventory(
        zone_key="zone_two_crops",
        fields_with_crop_and_gps={
            "wheat": MIN_FIELDS_PER_CROP,
            "barley": MIN_FIELDS_PER_CROP,
        },
        avg_temporal_scenes=float(MIN_TEMPORAL_SCENES),
        gps_quality_ok=True,
    )
    out = assess_classification_readiness(inv)
    assert out["state"] == ClassificationReadiness.ACCUMULATING.value
    assert out["can_classify"] is False
    assert any("محاصيل جاهزة" in b for b in out["blockers"])


# ─── أرضيّة التراكم: 10 ≤ n < 30 ⇒ ACCUMULATING ──────────────────────────


def test_accumulating_floor_partitioning():
    # عدد بين الأرضيّة والعتبة ⇒ يُحتسب accumulating لا ready
    inv = CropSampleInventory(
        zone_key="zone_accumulating",
        fields_with_crop_and_gps={
            "wheat": ACCUMULATING_FLOOR,  # 10 ⇒ accumulating (حدّ أدنى شامل)
            "barley": MIN_FIELDS_PER_CROP - 1,  # 29 ⇒ accumulating
            "millet": ACCUMULATING_FLOOR - 1,  # 9 ⇒ دون الأرضيّة، لا هذا ولا ذاك
        },
        avg_temporal_scenes=float(MIN_TEMPORAL_SCENES),
        gps_quality_ok=True,
    )
    out = assess_classification_readiness(inv)
    assert out["state"] == ClassificationReadiness.ACCUMULATING.value
    assert out["can_classify"] is False
    assert out["crops_ready"] == []
    assert set(out["crops_accumulating"]) == {"wheat", "barley"}
    assert out["total_crops_tracked"] == 3


def test_below_floor_only_is_not_ready():
    # كلّ المحاصيل دون أرضيّة التراكم ⇒ NOT_READY (لا تراكم ولا جاهزيّة)
    inv = CropSampleInventory(
        zone_key="zone_below_floor",
        fields_with_crop_and_gps={
            "wheat": ACCUMULATING_FLOOR - 1,
            "barley": 1,
        },
        avg_temporal_scenes=1.0,
        gps_quality_ok=False,
    )
    out = assess_classification_readiness(inv)
    assert out["state"] == ClassificationReadiness.NOT_READY.value
    assert out["crops_ready"] == []
    assert out["crops_accumulating"] == []


# ─── readiness_roadmap ───────────────────────────────────────────────────


def test_roadmap_counts_ready_zones():
    # منطقتان جاهزتان + واحدة فارغة ⇒ ready_zones == 2
    inventories = [
        _ready_inventory("zone_a"),
        _ready_inventory("zone_b"),
        CropSampleInventory(
            zone_key="zone_empty",
            fields_with_crop_and_gps={},
            avg_temporal_scenes=0.0,
            gps_quality_ok=False,
        ),
    ]
    out = readiness_roadmap(inventories)
    assert out["total_zones"] == 3
    assert out["ready_zones"] == 2
    assert len(out["per_zone"]) == 3
    assert out["strategic_note_ar"]
    # المناطق الجاهزة فقط هي التي can_classify
    ready_keys = {z["zone_key"] for z in out["per_zone"] if z["can_classify"]}
    assert ready_keys == {"zone_a", "zone_b"}


def test_roadmap_empty_input():
    # لا مناطق ⇒ أصفار متّسقة
    out = readiness_roadmap([])
    assert out["total_zones"] == 0
    assert out["ready_zones"] == 0
    assert out["per_zone"] == []


def test_thresholds_have_expected_values():
    # العتبات معلنة صراحةً ومتّسقة مع التصميم
    assert MIN_FIELDS_PER_CROP == 30
    assert MIN_TEMPORAL_SCENES == 6
    assert MIN_CROPS_FOR_USEFUL_MAP == 3
    assert ACCUMULATING_FLOOR == 10

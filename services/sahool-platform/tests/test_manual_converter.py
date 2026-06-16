"""اختبارات محوّل وحدات التطبيق اليدوي (offline) — تحويل وحدات صرف.

يتحقّق من `api/manual_converter.py`: kg_per_terrace، وفروع الطرق الثلاث
(نثر على مصطبة / رشّ ظهري / لكلّ شجرة) مع وبدون أغطية وتركيز، ورفع ValueError
عند نقص المعدّات. كلّ القيم مشتقّة هندسيّاً من الكود (1 هكتار = 10000 م²).
بلا قاعدة بيانات ولا شبكة ولا قراءة ملفّات.
"""

import pytest
from api.manual_converter import (
    ApplicationMethod,
    EquipmentSpec,
    ManualDose,
    convert_zone,
    kg_per_terrace,
)

pytestmark = pytest.mark.unit


# ─── kg_per_terrace ────────────────────────────────────────────────────────


def test_kg_per_terrace_basic_conversion():
    # 50 kg/ha × 100 m² / 10000 = 0.5 kg
    assert kg_per_terrace(50, 100) == 0.5


def test_kg_per_terrace_full_hectare_terrace_equals_rate():
    assert kg_per_terrace(120, 10_000) == 120.0


# ─── BROADCAST_TERRACE ─────────────────────────────────────────────────────


def test_broadcast_terrace_with_caps():
    equip = EquipmentSpec(terrace_area_m2=100, cap_weight_kg=0.05)
    d = convert_zone("z1", 50, 2.0, ApplicationMethod.BROADCAST_TERRACE, equip)
    assert d.kg_total == 100.0  # 50 kg/ha × 2 ha
    assert d.kg_per_terrace == 0.5  # 50 × 100 / 10000
    assert d.terraces_count == 200.0  # 2 ha = 20000 m² / 100
    assert d.caps_per_terrace == 10.0  # 0.5 / 0.05
    assert d.instruction_ar.startswith("انثر")
    assert "غطاء" in d.instruction_ar


def test_broadcast_terrace_without_caps_falls_back_to_kg():
    equip = EquipmentSpec(terrace_area_m2=100)
    d = convert_zone("z1", 50, 2.0, ApplicationMethod.BROADCAST_TERRACE, equip)
    assert d.kg_per_terrace == 0.5
    assert d.caps_per_terrace is None
    assert "كغ على كلّ مصطبة" in d.instruction_ar


def test_broadcast_terrace_zero_cap_weight_falls_back_to_kg():
    equip = EquipmentSpec(terrace_area_m2=100, cap_weight_kg=0.0)
    d = convert_zone("z1", 50, 2.0, ApplicationMethod.BROADCAST_TERRACE, equip)
    assert d.caps_per_terrace is None
    assert "كغ على كلّ مصطبة" in d.instruction_ar


def test_broadcast_terrace_requires_terrace_area():
    with pytest.raises(ValueError, match="terrace_area_m2"):
        convert_zone("z1", 50, 2.0, ApplicationMethod.BROADCAST_TERRACE, EquipmentSpec())


def test_broadcast_terrace_zero_area_raises():
    with pytest.raises(ValueError):
        convert_zone(
            "z1", 50, 2.0, ApplicationMethod.BROADCAST_TERRACE, EquipmentSpec(terrace_area_m2=0)
        )


# ─── BACKPACK_SPRAY ────────────────────────────────────────────────────────


def test_backpack_spray_with_caps():
    equip = EquipmentSpec(tank_capacity_l=20, concentration_kg_l=0.5, cap_weight_kg=0.1)
    d = convert_zone("z2", 10, 1.0, ApplicationMethod.BACKPACK_SPRAY, equip)
    # kg_total = 10; solution = 10/0.5 = 20 L; tanks = 20/20 = 1
    assert d.tanks_needed == 1.0
    # kg_per_tank = 20 × 0.5 = 10 kg; caps = 10 / 0.1 = 100
    assert d.caps_per_terrace == 100.0
    assert "غطاء في كلّ خزّان" in d.instruction_ar


def test_backpack_spray_without_caps_falls_back_to_kg():
    equip = EquipmentSpec(tank_capacity_l=20, concentration_kg_l=0.5)
    d = convert_zone("z2", 10, 1.0, ApplicationMethod.BACKPACK_SPRAY, equip)
    assert d.tanks_needed == 1.0
    assert d.caps_per_terrace is None
    assert "كغ في كلّ خزّان" in d.instruction_ar


def test_backpack_spray_requires_tank_capacity():
    with pytest.raises(ValueError, match="tank_capacity_l"):
        convert_zone(
            "z2",
            10,
            1.0,
            ApplicationMethod.BACKPACK_SPRAY,
            EquipmentSpec(concentration_kg_l=0.5),
        )


def test_backpack_spray_requires_concentration():
    with pytest.raises(ValueError, match="concentration_kg_l"):
        convert_zone(
            "z2",
            10,
            1.0,
            ApplicationMethod.BACKPACK_SPRAY,
            EquipmentSpec(tank_capacity_l=20),
        )


# ─── PER_TREE ──────────────────────────────────────────────────────────────


def test_per_tree_with_cans():
    equip = EquipmentSpec(tree_spacing_m2=25, can_capacity_l=10, concentration_kg_l=0.2)
    d = convert_zone("z3", 100, 1.0, ApplicationMethod.PER_TREE, equip)
    # trees = 10000 / 25 = 400; kg_per_tree = 100 × 25 / 10000 = 0.25
    assert d.trees_count == 400.0
    # cans = 0.25 / (10 × 0.2) = 0.125
    assert d.watering_cans_per_tree == 0.125
    assert "سقاية لكلّ شجرة" in d.instruction_ar


def test_per_tree_without_cans_falls_back_to_kg():
    equip = EquipmentSpec(tree_spacing_m2=25)
    d = convert_zone("z3", 100, 1.0, ApplicationMethod.PER_TREE, equip)
    assert d.trees_count == 400.0
    assert d.watering_cans_per_tree is None
    assert "كغ لكلّ شجرة" in d.instruction_ar


def test_per_tree_partial_can_data_falls_back_to_kg():
    # can_capacity موجودة لكن التركيز غائب → سقوط للكغ
    equip = EquipmentSpec(tree_spacing_m2=25, can_capacity_l=10)
    d = convert_zone("z3", 100, 1.0, ApplicationMethod.PER_TREE, equip)
    assert d.watering_cans_per_tree is None
    assert "كغ لكلّ شجرة" in d.instruction_ar


def test_per_tree_requires_tree_spacing():
    with pytest.raises(ValueError, match="tree_spacing_m2"):
        convert_zone("z3", 100, 1.0, ApplicationMethod.PER_TREE, EquipmentSpec())


# ─── to_dict ───────────────────────────────────────────────────────────────


def test_to_dict_per_tree_shape_and_rounding():
    equip = EquipmentSpec(tree_spacing_m2=25, can_capacity_l=10, concentration_kg_l=0.2)
    d = convert_zone("z3", 100, 1.0, ApplicationMethod.PER_TREE, equip).to_dict()
    assert d["zone_id"] == "z3"
    assert d["method"] == "per_tree"
    assert d["kg_total"] == 100.0
    assert d["watering_cans_per_tree"] == 0.12  # round(0.125, 2)
    assert d["trees_count"] == 400.0
    # الحقول غير المعنيّة بالطريقة تبقى None
    assert d["kg_per_terrace"] is None
    assert d["tanks_needed"] is None


def test_to_dict_handles_all_none_optionals():
    dose = ManualDose(
        zone_id="z0",
        rate_kg_ha=10,
        method=ApplicationMethod.BROADCAST_TERRACE,
        kg_total=10,
    )
    d = dose.to_dict()
    for key in (
        "kg_per_terrace",
        "terraces_count",
        "caps_per_terrace",
        "tanks_needed",
        "watering_cans_per_tree",
        "trees_count",
    ):
        assert d[key] is None
    assert d["instruction_ar"] == ""

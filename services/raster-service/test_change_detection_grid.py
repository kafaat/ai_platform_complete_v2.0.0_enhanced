"""
test_change_detection_grid.py — تحقّق offline لكشف التغيّر المكاني (per-pixel 2D).

نقيّ تماماً: لا شبكة، لا rasterio. numpy فقط. يغطّي:
  • الفرق بكسل-بكسل + التصنيف (تحسّن/مستقرّ/تدهور/تدهور حادّ).
  • اتّجاه المؤشّر (ندوة: النقص تدهور؛ ملوحة: الزيادة تدهور).
  • صدق الفجوات (None/NaN لا تُحسب ولا تُفبرَك).
  • المفاتيح المختصرة على المستوى الأعلى (delta_grid/mean_delta/improved_pct/
    degraded_pct/zones) التي يستهلكها العميل/الموبايل.
"""

import change_detection as cd


def test_top_level_contract_keys_present():
    """العقد المطلوب: delta_grid + mean_delta + improved_pct + degraded_pct + zones."""
    before = [[0.6, 0.6], [0.6, 0.6]]
    after = [[0.6, 0.6], [0.6, 0.6]]
    res = cd.detect_change(before, after, index="ndvi")
    for key in ("delta_grid", "mean_delta", "improved_pct", "degraded_pct", "zones"):
        assert key in res, f"مفتاح مفقود: {key}"
    assert isinstance(res["delta_grid"], list)
    assert isinstance(res["zones"], list)


def test_stable_when_no_change():
    """لا فرق ⇒ كلّ البكسلات مستقرّة، لا تحسّن/تدهور، mean_delta=0."""
    g = [[0.5, 0.4], [0.3, 0.55]]
    res = cd.detect_change(g, g, index="ndvi")
    assert res["mean_delta"] == 0.0
    assert res["improved_pct"] == 0.0
    assert res["degraded_pct"] == 0.0
    assert res["stable_pct"] == 100.0
    assert res["zones"] == []


def test_ndvi_drop_is_degradation():
    """انخفاض NDVI كبير (>severe) ⇒ تدهور حادّ، delta سالب."""
    before = [[0.8, 0.8], [0.8, 0.8]]
    after = [[0.4, 0.4], [0.4, 0.4]]  # هبوط 0.4 ≥ severe(0.2)
    res = cd.detect_change(before, after, index="ndvi", slight_threshold=0.1, severe_threshold=0.2)
    assert res["mean_delta"] == -0.4
    assert res["degraded_pct"] == 100.0
    assert res["improved_pct"] == 0.0
    assert res["areas"]["severe_degraded_pct"] == 100.0
    # delta_grid يحمل الفرق الفعلي (after-before)
    assert res["delta_grid"][0][0] == -0.4


def test_ndvi_rise_is_improvement():
    """ارتفاع NDVI ⇒ تحسّن، delta موجب."""
    before = [[0.3, 0.3], [0.3, 0.3]]
    after = [[0.6, 0.6], [0.6, 0.6]]
    res = cd.detect_change(before, after, index="ndvi")
    assert res["mean_delta"] == 0.3
    assert res["improved_pct"] == 100.0
    assert res["degraded_pct"] == 0.0


def test_salinity_direction_inverted():
    """للملوحة: الزيادة(+) تدهور (زحف ملوحة)، لا تحسّن."""
    before = [[0.1, 0.1]]
    after = [[0.5, 0.5]]  # ارتفاع ملوحة = تدهور
    res = cd.detect_change(before, after, index="salinity")
    assert res["direction"] == "higher_is_worse"
    assert res["degraded_pct"] == 100.0
    assert res["improved_pct"] == 0.0


def test_gaps_not_counted_and_no_fabrication():
    """None/NaN في أيّ تاريخ ⇒ بكسل غير صالح (لا يُحسب، delta=None، لا تغيّر مُفبرَك)."""
    before = [[0.5, None], [0.5, 0.5]]
    after = [[0.5, 0.9], [None, 0.5]]
    res = cd.detect_change(before, after, index="ndvi")
    # بكسلان فقط صالحان (الزاويتان حيث كلاهما متوفّر)
    assert res["valid_pixels"] == 2
    assert res["total_pixels"] == 4
    assert res["delta_grid"][0][1] is None  # before=None
    assert res["delta_grid"][1][0] is None  # after=None


def test_zones_aggregate_degraded_cells():
    """المناطق تجمّع خلايا التدهور بإحداثيّاتها (للموبايل: أين تدهور الحقل)."""
    before = [[0.8, 0.8], [0.8, 0.8]]
    after = [[0.8, 0.8], [0.3, 0.3]]  # الصفّ السفلي تدهور
    res = cd.detect_change(before, after, index="ndvi")
    deg_zones = [z for z in res["zones"] if z["class"] in ("degradation", "severe_degradation")]
    assert deg_zones, "يجب وجود منطقة تدهور"
    cells = [tuple(c) for z in deg_zones for c in z["cells"]]
    assert (1, 0) in cells and (1, 1) in cells


def test_mismatched_shapes_raise():
    try:
        cd.detect_change([[0.5, 0.5]], [[0.5], [0.5]], index="ndvi")
    except ValueError:
        return
    raise AssertionError("يجب رفع ValueError عند اختلاف الأبعاد")


def test_all_gaps_zero_coverage():
    """تغطية صفر (كلّ البكسلات فجوات) ⇒ لا تغيّر، coverage=0، تحذير سحاب."""
    before = [[None, None], [None, None]]
    after = [[0.5, 0.5], [0.5, 0.5]]
    res = cd.detect_change(before, after, index="ndvi")
    assert res["valid_pixels"] == 0
    assert res["coverage_pct"] == 0.0
    assert res["cloud_warning"] is True
    assert res["mean_delta"] == 0.0

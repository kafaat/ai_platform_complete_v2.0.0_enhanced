"""Unit tests: spatial (2D per-pixel) change detection — raster-service.

يحرس الفجوة المُسدَّة: التحليل الزمني 1D (متوسّط) يُخفي التدهور الموضعي. هذه
الاختبارات تُثبت أنّ كشف التغيير المكاني يُبرزه، يحترم اتّجاه المؤشّر، ويصدُق مع
فجوات السحاب — وأنّ الـplaceholder («قيد التطوير») أُزيل وحلّ محلّه ربط حقيقي.
"""

from __future__ import annotations

import importlib.util
import os

import pytest

ROOT = os.path.join(os.path.dirname(__file__), "..")


def _load_cd():
    spec = importlib.util.spec_from_file_location(
        "change_detection", os.path.join(ROOT, "services/raster-service/change_detection.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _const(n: int, v):
    return [[v for _ in range(n)] for _ in range(n)]


@pytest.mark.unit
def test_hidden_localized_degradation_surfaced():
    """متوسّط الفرق يبدو مستقرّاً، لكنّ رقعة تدهورت بشدّة — الجوهر."""
    cd = _load_cd()
    n = 16
    before = _const(n, 0.6)
    after = [row[:] for row in before]
    for r in range(4):
        for c in range(4):  # 16/256 = 6.25% تنهار
            after[r][c] = 0.15
    res = cd.detect_change(before, after, index="ndvi")
    assert abs(res["stats"]["mean_delta"]) < 0.1  # المتوسّط «يبدو سليماً»
    assert res["areas"]["severe_degraded_pct"] >= 6.0  # لكنّ الرقعة مُبرَزة
    assert any(z["class"] == "severe_degradation" for z in res["zones"])


@pytest.mark.unit
def test_salinity_direction_inverted():
    """الملوحة: الارتفاع = تدهور (لا تحسّن)."""
    cd = _load_cd()
    n = 16
    before = _const(n, 0.1)
    after = [row[:] for row in before]
    for r in range(n):
        for c in range(6):
            after[r][c] = 0.45  # الملوحة ترتفع في شريط
    res = cd.detect_change(before, after, index="salinity")
    assert res["direction"] == "higher_is_worse"
    assert res["areas"]["degraded_pct"] > 0
    assert res["areas"]["improved_pct"] == 0.0


@pytest.mark.unit
def test_cloud_gap_honesty():
    """بكسلات None لا تُحسب ولا يُفبرَك تغيير عبرها؛ تحذير عند تغطية منخفضة."""
    cd = _load_cd()
    n = 16
    before = _const(n, 0.5)
    after = _const(n, 0.45)
    for r in range(8, n):  # نصف «بعد» غيوم
        for c in range(n):
            after[r][c] = None
    res = cd.detect_change(before, after, index="ndvi")
    assert res["valid_pixels"] == n * 8
    assert res["total_pixels"] == n * n
    assert res["cloud_warning"] is True
    assert "التغطية" in res["interpretation_ar"]


@pytest.mark.unit
def test_deterministic_and_improvement_and_shape_guard():
    cd = _load_cd()
    n = 12
    before = _const(n, 0.3)
    after = _const(n, 0.55)  # تحسّن منتظم
    r1 = cd.detect_change(before, after, index="ndvi")
    r2 = cd.detect_change(before, after, index="ndvi")
    assert r1 == r2  # حتميّ
    assert r1["areas"]["improved_pct"] > 90.0
    with pytest.raises(ValueError):
        cd.detect_change([[0.1, 0.2]], [[0.1]], index="ndvi")  # أبعاد مختلفة


@pytest.mark.unit
def test_placeholder_removed_and_endpoint_wired():
    """الـplaceholder أُزيل من نسختَي المهارة، والنقطة موجودة في raster-service."""
    placeholder = "قيد التطوير"
    for rel in (
        "services/supervisor-agent/skills/remote_sensing_skill.py",
        "services/supervisor-agent/remote_sensing_skill.py",
    ):
        txt = open(os.path.join(ROOT, rel), encoding="utf-8").read()
        assert placeholder not in txt, f"placeholder ما زال في {rel}"
        assert "/change/detect" in txt, f"الربط بالنقطة مفقود في {rel}"
    main = open(os.path.join(ROOT, "services/raster-service/main.py"), encoding="utf-8").read()
    assert '@app.post("/change/detect")' in main, "نقطة /change/detect مفقودة"
    # حدّ الحجم (413) ضدّ DoS قبل تحويل numpy
    assert "MAX_CHANGE_GRID_CELLS" in main and "status_code=413" in main, "حدّ حجم الشبكة مفقود"

"""تحقّق V60.2 — اختيار عدد مناطق الإدارة الأمثل (fuzzy c-means + FPI/NCE) + تنعيم مكانيّ.

منهجيّة Management Zone Analyst: FPI/NCE على fuzzy c-means عبر مدى k تقترح العدد الأمثل.
- بيانات ٣ مجموعات مفصولة ⇒ ``recommended_k == 3`` (أدنى FPI).
- fuzzy c-means حتميّ: مراكز تصاعديّة + صفوف عضويّة تجمع لـ1.
- بيانات متجانسة ⇒ ``None`` (لا اختراع عدد).
- مرشّح الأغلبيّة يُصلح خليّة «ملح-وفلفل» ولا يمسّ حقلاً نظيفاً (idempotent).
- المسار التلقائيّ في ``zones_from_ndvi_grid(grid, bbox, None)`` يعيد مناطق + التوصية.

منطق صرف — وظيفة Unit Tests.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.ai_agronomist import management_zone_count as M  # noqa: E402
from services.ai_agronomist import productivity_zones_clustering as C  # noqa: E402

_BBOX = [44.0, 16.0, 44.4, 16.4]
# ٣ مجموعات NDVI مفصولة بوضوح (٩ قيم مميَّزة).
_THREE_GROUPS = [0.08, 0.10, 0.12, 0.48, 0.50, 0.52, 0.88, 0.90, 0.92] * 3


def test_fuzzy_cmeans_deterministic_sorted_and_normalized():
    a = M.fuzzy_cmeans_1d(_THREE_GROUPS, 3)
    b = M.fuzzy_cmeans_1d(list(reversed(_THREE_GROUPS)), 3)  # shuffled input
    assert a is not None and b is not None
    ca, ma = a
    cb, _ = b
    assert ca == pytest.approx(cb)  # order-independent (deterministic seeding)
    assert ca[0] < ca[1] < ca[2]  # ascending centroids
    for row in ma:  # membership rows sum to 1
        assert sum(row) == pytest.approx(1.0, abs=1e-6)


def test_fuzzy_cmeans_none_on_homogeneous():
    assert M.fuzzy_cmeans_1d([0.5] * 10, 3) is None
    assert M.fuzzy_cmeans_1d([0.5, 0.5], 2) is None  # <k distinct


def test_recommend_zone_count_picks_true_structure():
    rec = M.recommend_zone_count(_THREE_GROUPS)
    assert rec is not None
    assert rec["recommended_k"] == 3
    assert rec["fpi_optimal_k"] == 3
    ks = [row["k"] for row in rec["metrics"]]
    assert ks == [2, 3, 4, 5, 6]
    # FPI أدنى عند 3 من عند 2 (بيانات ٣ مجموعات مفصولة).
    fpi_by_k = {row["k"]: row["fpi"] for row in rec["metrics"]}
    assert fpi_by_k[3] < fpi_by_k[2]
    assert "حكم أغرونوميّ" in rec["note"]  # صدق: اقتراح لا قرار


def test_recommend_zone_count_none_on_degenerate():
    assert M.recommend_zone_count([0.5] * 20) is None
    assert M.recommend_zone_count([]) is None


def test_smooth_label_grid_fixes_salt_and_pepper():
    # خليّة وسطيّة شاذّة (1) وسط بحر من (0) ⇒ الأغلبيّة تُصلحها إلى 0.
    grid = [[0, 0, 0], [0, 1, 0], [0, 0, 0]]
    out = C.smooth_label_grid(grid)
    assert out[1][1] == 0
    # حقل نظيف (نصفان متّصلان) لا يتغيّر (idempotent).
    clean = [[0, 0], [0, 0], [1, 1], [1, 1]]
    assert C.smooth_label_grid(clean) == clean


def test_smooth_label_grid_ignores_invalid_cells():
    grid = [[0, None, 0], [0, 1, None], [0, 0, 0]]
    out = C.smooth_label_grid(grid)
    assert out[0][1] is None and out[1][2] is None  # None لا يصوّت ولا يُلمَس
    assert out[1][1] == 0


def test_zones_from_ndvi_grid_auto_k_returns_recommendation():
    # شبكة ٣ نطاقات أفقيّة (منخفض/متوسّط/عالٍ) ⇒ المسار التلقائيّ يختار k ويعيد التوصية.
    grid = [[0.10, 0.10, 0.10]] * 2 + [[0.50, 0.50, 0.50]] * 2 + [[0.90, 0.90, 0.90]] * 2
    out = C.zones_from_ndvi_grid(grid, _BBOX, None, smooth=True)
    assert out is not None
    assert out["spatially_smoothed"] is True
    rec = out["zone_count_recommendation"]
    assert rec is not None and rec["recommended_k"] == out["k_effective"]
    classes = sorted({z["productivity_class"] for z in out["zones"]})
    assert classes == ["high", "low", "medium"]


def test_explicit_k_path_unchanged_and_no_recommendation():
    grid = [[0.15, 0.15, 0.15, 0.15]] * 2 + [[0.80, 0.80, 0.80, 0.80]] * 2
    out = C.zones_from_ndvi_grid(grid, _BBOX, 2)
    assert out is not None
    assert "zone_count_recommendation" not in out  # لا توصية عند k صريح
    assert out["spatially_smoothed"] is False

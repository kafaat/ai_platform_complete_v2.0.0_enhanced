"""تحقّق V60.1 — عنقدة مناطق الإنتاجيّة من شبكة NDVI (k-means حتميّ، مُفعّل + سقوط آمن).

- ``kmeans_1d`` حتميّ (بلا عشوائيّة): مراكز تصاعديّة تفصل مجموعات NDVI.
- ``zones_from_ndvi_grid``: خلايا NDVI منخفضة/مرتفعة ⇒ مناطق low/high بمضلّعات EPSG:4326.
- **مُفعّل عند وجود ``ndvi_grid`` فقط**؛ غيابه/تدهوره ⇒ ``None`` ⇒ السقوط للشرائح (v60 دون تغيير).
- ``cluster_separability`` عالٍ لبيانات مفصولة.
- كلّ نتيجة اقتراح فقط.

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

from services.ai_agronomist import productivity_zones as PZ  # noqa: E402
from services.ai_agronomist import productivity_zones_clustering as C  # noqa: E402

_BBOX = [44.0, 16.0, 44.4, 16.4]


def test_kmeans_1d_is_deterministic_and_ordered():
    a = C.kmeans_1d([0.1, 0.12, 0.11, 0.8, 0.82, 0.79], 2)
    b = C.kmeans_1d([0.82, 0.11, 0.8, 0.1, 0.79, 0.12], 2)  # shuffled
    assert a == b  # order-independent, no randomness
    assert a[0] < a[1] and a[0] < 0.3 and a[1] > 0.6


def test_cluster_separability_high_for_separated_data():
    vals = [0.1, 0.11, 0.12, 0.8, 0.81, 0.82]
    cents = C.kmeans_1d(vals, 2)
    assert C.cluster_separability(vals, cents) > 0.8


def test_zones_from_ndvi_grid_low_vs_high_halves():
    # النصف العلويّ منخفض NDVI، السفليّ مرتفع ⇒ منطقتان.
    grid = [[0.15, 0.15, 0.15, 0.15]] * 2 + [[0.80, 0.80, 0.80, 0.80]] * 2
    out = C.zones_from_ndvi_grid(grid, _BBOX, 2)
    assert out is not None
    classes = sorted({z["productivity_class"] for z in out["zones"]})
    assert classes == ["high", "low"]
    for z in out["zones"]:
        for lon, lat in z["geometry"]["coordinates"][0]:
            assert 44.0 <= lon <= 44.4 and 16.0 <= lat <= 16.4


def test_degenerate_grid_returns_none():
    assert C.zones_from_ndvi_grid([[0.5, 0.5], [0.5, 0.5]], _BBOX, 3) is None  # single value
    assert C.zones_from_ndvi_grid([], _BBOX, 3) is None


# ── integration through the tool contract ───────────────────────────────────
def test_propose_uses_clustering_when_grid_present():
    grid = [[0.15, 0.15]] * 2 + [[0.82, 0.82]] * 2
    out = PZ.propose_productivity_zones(
        {"bbox": _BBOX, "zone_count": 2, "ndvi_grid": grid},
        field_id="f",
    )
    assert out["method"] == "ndvi_kmeans_clustering"
    assert out["cluster_separability"] > 0.8
    assert out["requires_user_confirmation"] is True
    assert {z["productivity_class"] for z in out["productivity_zones"]} == {"low", "high"}
    assert all("ndvi_grid_kmeans" in z["drivers"] for z in out["productivity_zones"])


def test_propose_falls_back_to_strips_without_grid():
    out = PZ.propose_productivity_zones({"bbox": _BBOX, "zone_count": 3}, field_id="f")
    assert out["method"] in {
        "multi_index_quantile_zoning_fallback",
        "geometry_seeded_zoning_fallback",
    }
    assert [z["productivity_class"] for z in out["productivity_zones"]] == ["high", "medium", "low"]

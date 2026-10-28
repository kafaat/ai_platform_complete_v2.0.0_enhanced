"""غيوم مجهولة ≠ صفر غيوم — RS-01 + EXTRA-1 (تدقيق الاستشعار عن بُعد 2026-10-27).

**RS-01:** ``stac_search_cdse``/``stac_search_element84`` كانا يطبّعان غياب
``eo:cloud_cover`` إلى ``cloud_cover_pct=0.0`` بجانب ``cloud_cover_known=False``، و
``scene_policy`` يتجاهل العلم، فيصير المشهد المجهول «صافياً ١٠٠٪ / جودة high» في انتقاء
الـbackfill والشريط الزمنيّ. قبول المجهول قرار مالك موثَّق؛ **اختلاق صفرٍ له ليس كذلك.**

**EXTRA-1:** ``cdse_client._apply_cloud_filter`` يحوّل بـ``float()`` ثمّ يفحص الحدّ الأعلى
وحده، فـ``"NaN"`` و``"-Infinity"`` و``-1`` تعبر المرشّح الصارم بلا تشخيص.

العقد: ``eo:cloud_cover`` نسبة مئويّة [0, 100] (STAC eo extension) — لا كسر [0, 1] ولا
تحويل وحدات ضمنيّ. ما ليس عدداً منتهياً داخل المدى = مجهول: ``None`` مع ``known=False``،
ولا يُرتَّب أبداً جودةً عالية.
"""

from __future__ import annotations

import asyncio
import math

import cdse_client
import pytest
import raster_scene_model
import scene_policy
import stac_search

pytestmark = pytest.mark.unit

_DT = "2026-10-01T08:00:00Z"


# ───────────── RS-01: البحث لا يختلق صفراً ─────────────


class _FakeCdse:
    def __init__(self, features):
        self._features = features

    def search_scenes(self, **_kw):
        return self._features


def _cdse_items(monkeypatch, props: dict) -> list[dict]:
    feat = {"id": "S2_X", "properties": {"datetime": _DT, **props}}
    monkeypatch.setattr(cdse_client, "get_client", lambda: _FakeCdse([feat]))
    out = asyncio.run(stac_search.stac_search_cdse([0, 0, 1, 1], _DT, _DT, 40.0, 10))
    return out["items"]


def test_cdse_search_keeps_missing_cloud_null_not_zero(monkeypatch):
    (item,) = _cdse_items(monkeypatch, {})
    assert item["cloud_cover_known"] is False
    assert item["cloud_cover_pct"] is None, "غياب eo:cloud_cover صار صفراً مختلَقاً"


@pytest.mark.parametrize("raw", ["NaN", float("nan"), float("-inf"), -1.0, 101.0, "bad", True])
def test_cdse_search_marks_invalid_cloud_unknown(monkeypatch, raw):
    (item,) = _cdse_items(monkeypatch, {"eo:cloud_cover": raw})
    assert item["cloud_cover_known"] is False
    assert item["cloud_cover_pct"] is None


def test_cdse_search_keeps_valid_cloud_as_percent(monkeypatch):
    (item,) = _cdse_items(monkeypatch, {"eo:cloud_cover": 12.5})
    assert item["cloud_cover_known"] is True
    assert item["cloud_cover_pct"] == 12.5


def test_element84_search_keeps_missing_cloud_null_not_zero(monkeypatch):
    async def _fake_query(_payload):
        return {"features": [{"id": "E84_X", "properties": {"datetime": _DT}, "assets": {}}]}

    monkeypatch.setattr(stac_search, "stac_query", _fake_query)
    out = asyncio.run(stac_search.stac_search_element84([0, 0, 1, 1], _DT, _DT, 40.0, 10))
    (item,) = out["items"]
    assert item["cloud_cover_known"] is False
    assert item["cloud_cover_pct"] is None


# ───────────── RS-01: السياسة تحترم known=False ─────────────


def _legacy_unknown(item_id: str = "missing-cloud", dt: str = _DT) -> dict:
    """الشكل الذي كان البحث يُخرجه (وقد يبقى في سجلّات مُدامة): 0.0 مع known=False."""
    return {
        "item_id": item_id,
        "datetime": dt,
        "cloud_cover_pct": 0.0,
        "cloud_cover_known": False,
        "provider": "cdse",
    }


def test_unknown_cloud_is_never_labelled_high_or_clear():
    scene = _legacy_unknown()
    assert scene_policy.scene_cloud_pct(scene) is None
    assert scene_policy.scene_clear_pct(scene) is None
    assert scene_policy.scene_quality_label(scene) == "unknown"


def test_backfill_selection_does_not_manufacture_clear_coverage():
    (out,) = scene_policy.select_backfill_scenes_by_policy([_legacy_unknown()], indices=["ndvi"])
    assert out["quality_label"] == "unknown"
    assert out["clear_pct"] is None
    assert out["sahool_quality"]["cloud_pct"] is None
    assert out["sahool_quality"]["cloud_known"] is False
    assert out["sahool_quality"]["cloud_source"] == "unknown"


def test_unknown_cloud_ranks_below_a_known_acceptable_scene():
    known = {"item_id": "known-20", "datetime": _DT, "cloud_cover_pct": 20.0}
    ranked = scene_policy.rank_scenes([_legacy_unknown(), known], max_cloud_pct=40.0)
    assert [r["item_id"] for r in ranked] == ["known-20", "missing-cloud"]


def test_selection_receipt_declares_unknown_for_legacy_zero():
    selected = scene_policy.select_scene(
        [_legacy_unknown()], policy=scene_policy.SceneSelectionPolicy.LATEST_ACCEPTABLE
    )
    assert selected is not None
    assert selected.cloud_pct is None
    assert selected.cloud_source == "unknown"


def test_aoi_measurement_still_wins_over_unknown_scene_metadata():
    """``known`` يصف بيانات المشهد الوصفيّة؛ قياس AOI قياسٌ مستقلّ يبقى صالحاً."""
    scene = {**_legacy_unknown(), "aoi_cloud_pct": 10.0}
    assert scene_policy.scene_cloud_pct(scene) == 10.0
    assert scene_policy.scene_quality_label(scene) == "high"


@pytest.mark.parametrize("raw", [float("nan"), float("inf"), float("-inf"), -1.0, 100.5, "NaN"])
def test_policy_rejects_non_finite_and_out_of_range_cloud(raw):
    scene = {"item_id": "x", "datetime": _DT, "cloud_cover_pct": raw}
    assert scene_policy.scene_cloud_pct(scene) is None
    assert scene_policy.scene_quality_label(scene) == "unknown"
    q = scene_policy.scene_quality_score(scene)
    assert q["cloud_pct"] is None and q["cloud_known"] is False
    assert math.isfinite(q["score"])


@pytest.mark.parametrize("raw", [float("nan"), float("-inf"), -5.0, 150.0, "bad"])
def test_selectors_reject_present_but_malformed_cloud(raw):
    """التالف ≠ الغائب — مرآة سياسة ``cdse_client`` الصارمة: الغائب يُقبَل مجهولاً،
    والتالف يُرفَض. فلا يصير ``-5`` صفراً «صافياً» ولا ``150`` مجهولاً مؤهَّلاً."""
    bad = {"item_id": "bad", "datetime": _DT, "cloud_cover_pct": raw}
    assert scene_policy.scene_quality_score(bad)["cloud_source"] == "invalid"
    assert scene_policy.select_backfill_scenes_by_policy([bad], indices=["ndvi"]) == []
    assert (
        scene_policy.select_scene([bad], policy=scene_policy.SceneSelectionPolicy.LATEST_ACCEPTABLE)
        is None
    )


@pytest.mark.parametrize("raw", [0, 0.0, 37.25, 100, "42"])
def test_policy_accepts_valid_percent(raw):
    scene = {"item_id": "x", "datetime": _DT, "cloud_cover_pct": raw}
    assert scene_policy.scene_cloud_pct(scene) == float(raw)
    assert scene_policy.scene_quality_score(scene)["cloud_known"] is True


# ───────────── RS-01: التسلسل الموحَّد لا يختلق صفراً ─────────────


def test_normalized_scene_keeps_unknown_cloud_null():
    (scene,) = raster_scene_model.normalize_search_result(
        {
            "source": "cdse-catalog",
            "items": [{"item_id": "S2_X", "datetime": _DT, "cloud_cover_pct": None}],
        }
    )
    d = scene.to_dict()
    assert d["cloud_cover"] is None
    assert d["cloud_cover_known"] is False


def test_best_scene_endpoint_prefers_known_clear_over_unknown(monkeypatch):
    from routers import imagery_search

    async def _fake_search(*_a, **_kw):
        return {
            "items": [
                {"item_id": "unknown", "datetime": _DT, "cloud_cover_pct": None},
                {"item_id": "known-10", "datetime": _DT, "cloud_cover_pct": 10.0},
            ]
        }

    monkeypatch.setattr(imagery_search, "stac_search", _fake_search)
    out = asyncio.run(
        imagery_search.imagery_best_scene(
            west=0, south=0, east=1, north=1, lookback_days=30, max_cloud_pct=40
        )
    )
    assert out["best"]["item_id"] == "known-10"


# ───────────── EXTRA-1: مرشّح CDSE يرفض غير المنتهي وخارج المدى ─────────────


def _scene(raw) -> dict:
    return {"id": "s1", "properties": {"eo:cloud_cover": raw}}


@pytest.mark.parametrize("raw", ["NaN", "-Infinity", float("nan"), float("-inf"), -1, -0.5])
def test_strict_cloud_filter_rejects_malformed_finite_domain(monkeypatch, raw):
    monkeypatch.delenv("CDSE_CLOUD_POLICY", raising=False)
    accepted, diags = cdse_client._apply_cloud_filter([_scene(raw)], 30.0)
    assert accepted == [], f"{raw!r} عبر المرشّح الصارم"
    assert [d["reason"] for d in diags] == ["invalid_cloud_cover"]
    assert diags[0]["accepted"] is False


def test_allow_unknown_accepts_malformed_with_diagnostic(monkeypatch):
    monkeypatch.setenv("CDSE_CLOUD_POLICY", "allow_unknown")
    accepted, diags = cdse_client._apply_cloud_filter([_scene("NaN")], 30.0)
    assert len(accepted) == 1
    assert diags[0]["reason"] == "invalid_cloud_cover" and diags[0]["accepted"] is True


def test_above_hundred_is_invalid_not_merely_over_threshold(monkeypatch):
    """101٪ ليس «غائماً جدّاً» بل قيمة مستحيلة — تشخيص صريح لا رفض صامت."""
    monkeypatch.delenv("CDSE_CLOUD_POLICY", raising=False)
    accepted, diags = cdse_client._apply_cloud_filter([_scene(101)], 100.0)
    assert accepted == []
    assert [d["reason"] for d in diags] == ["invalid_cloud_cover"]


@pytest.mark.parametrize("raw", [0, 0.0, 30, "29.9"])
def test_strict_cloud_filter_still_accepts_valid_in_range(monkeypatch, raw):
    monkeypatch.delenv("CDSE_CLOUD_POLICY", raising=False)
    accepted, diags = cdse_client._apply_cloud_filter([_scene(raw)], 30.0)
    assert len(accepted) == 1 and diags == []

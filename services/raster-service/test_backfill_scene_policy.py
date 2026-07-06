"""اختبارات وحدة لسياسة اختيار مشاهد الـbackfill (``_select_backfill_scenes_by_policy``).

تقفل الحالات الحدّيّة التي كانت مغطّاة عبر dry-run فقط: (١) كلّ المشاهد غائمة ⇒ لا اختيار
للخطّ الأساسيّ (صدق جودة: لا نلوّث الخطّ الزمنيّ بصور رديئة)، (٢) التباعد الزمنيّ ≥3 أيّام
يُفضَّل، (٣) وسم الجودة (high ≥70% صافٍ · medium ≥50% · rejected <50%). نقيّة بلا شبكة.
"""

from __future__ import annotations

import pytest
import scene_policy

pytestmark = pytest.mark.unit


def _scene(day: int, cloud: float, suffix: str = "A") -> dict:
    return {
        "item_id": f"S2_{day:02d}_{suffix}",
        "datetime": f"2026-01-{day:02d}T08:00:00Z",
        "cloud_cover_pct": cloud,
        "bands_urls": {
            "blue": "https://example.com/blue.tif",
            "green": "https://example.com/green.tif",
            "red": "https://example.com/red.tif",
            "nir": "https://example.com/nir.tif",
            "scl": "https://example.com/scl.tif",
        },
    }


def test_all_cloudy_core_timeline_selects_nothing():
    """كلّ المشاهد صافيها <50% (غيوم >50%) ⇒ الخطّ الأساسيّ لا يختار شيئاً (fail-closed جودةً)."""
    scenes = [_scene(d, 70.0) for d in (5, 10, 15, 20)]
    out = scene_policy.select_backfill_scenes_by_policy(scenes, indices=["ndvi"], limit=8)
    assert out == []


def test_clear_scenes_selected_with_correct_quality_labels():
    scenes = [_scene(2, 10.0, "hi"), _scene(8, 40.0, "med"), _scene(14, 70.0, "bad")]
    out = scene_policy.select_backfill_scenes_by_policy(scenes, indices=["ndvi"], limit=8)
    ids = {s["item_id"] for s in out}
    # 90% صافٍ و60% صافٍ مقبولان؛ 30% صافٍ مرفوض (تحت عتبة 50%).
    assert "S2_02_hi" in ids and "S2_08_med" in ids
    assert "S2_14_bad" not in ids
    labels = {s["item_id"]: s["quality_label"] for s in out}
    assert labels["S2_02_hi"] == "high"  # ≥70% صافٍ
    assert labels["S2_08_med"] == "medium"  # 50–70% صافٍ
    # clear_pct مُرفَق ومتّسق (100 − غيوم).
    clear = {s["item_id"]: s["clear_pct"] for s in out}
    assert clear["S2_02_hi"] == pytest.approx(90.0)


def test_min_spacing_prefers_spread_not_adjacent_days():
    """مشاهد صافية متقاربة (يوم بينها) لا تُختار كلّها؛ يُفضَّل الأبعد ≥3 أيّام."""
    scenes = [_scene(2, 10.0, "a"), _scene(3, 12.0, "b"), _scene(9, 15.0, "c")]
    out = scene_policy.select_backfill_scenes_by_policy(
        scenes, indices=["ndvi"], limit=2, min_spacing_days=3.0
    )
    days = sorted(s["item_id"].split("_")[1] for s in out)
    assert len(out) == 2
    assert "09" in days  # المشهد المتباعد مُدرَج
    assert days != ["02", "03"]  # لا يومان متلاصقان فقط


def test_advanced_only_request_respects_caller_max_cloud():
    """طلب مؤشّر متقدّم فقط (لا أساسيّ) يحترم max_cloud_pct للمستدعي لا عتبة الخطّ الأساسيّ."""
    scenes = [_scene(4, 55.0, "x"), _scene(12, 20.0, "y")]
    # max_cloud=60 ⇒ كلاهما مقبول (المؤشّر المتقدّم لا يفرض عتبة 50% الأساسيّة).
    out = scene_policy.select_backfill_scenes_by_policy(
        scenes, indices=["reci"], max_cloud_pct=60.0, limit=8
    )
    assert {s["item_id"] for s in out} == {"S2_04_x", "S2_12_y"}

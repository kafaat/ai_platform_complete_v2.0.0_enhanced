"""اختبار إغلاق C5: بوّابة عتبات NDVI خلف feature flag (default off) — مستوى الإسقاط.

يقفل `_apply_ndvi_threshold_gating` (التي يستدعيها recompute_field_state على كتلة
remote_sensing): OFF (افتراضيّ) ⇒ إعلان صريح `insufficient_field_calibration` (NDVI معلوماتيّ
لا يحكم الصلاحيّة)؛ ON بلا بطاقة معايَرة ⇒ يبقى insufficient (صدق: لا عتبات مُلفَّقة). لا قاعدة
بيانات. يُثبت أيضاً أنّ `_ndvi_thresholds_for` يُرجِع None لمحصول حقيقيّ (لا معايرة بعد).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_PLATFORM = Path(__file__).resolve().parent.parent / "services" / "sahool-platform"
if str(_PLATFORM) not in sys.path:
    sys.path.insert(0, str(_PLATFORM))

try:
    from api.field_state_projection import (
        _apply_ndvi_threshold_gating,
        _ndvi_thresholds_for,
    )
    from core.season_phenology import resolve_crop_id
except Exception:  # noqa: BLE001 — تبعيّات المنصّة غير متوفّرة (بيئة Unit Tests الأدنى)
    pytest.skip("platform/api deps unavailable", allow_module_level=True)

_FLAG = "APPLY_NDVI_THRESHOLDS"


def _state_with_ndvi() -> dict:
    return {"remote_sensing": {"available": True, "ndvi_mean": 0.62, "source": "sentinel-2"}}


def test_flag_off_declares_insufficient_calibration(monkeypatch):
    """OFF (افتراضيّ) ⇒ إعلان صريح insufficient_field_calibration، NDVI معلوماتيّ."""
    monkeypatch.delenv(_FLAG, raising=False)
    st = _state_with_ndvi()
    _apply_ndvi_threshold_gating(st, resolve_crop_id("قمح"), 60)
    rs = st["remote_sensing"]
    assert rs["ndvi_thresholds_enabled"] is False
    assert rs["thresholds_applied"] is False
    assert rs["threshold_source"] is None
    assert rs["calibration_status"] == "insufficient_field_calibration"
    # السلوك المعلوماتيّ محفوظ (لا تغيّر القيمة/التوفّر)
    assert rs["available"] is True and rs["ndvi_mean"] == 0.62


def test_flag_on_no_calibration_still_insufficient(monkeypatch):
    """ON لكن لا بطاقة تحمل عتبات معايَرة ⇒ يبقى insufficient (صدق: لا اختلاق)."""
    monkeypatch.setenv(_FLAG, "1")
    st = _state_with_ndvi()
    _apply_ndvi_threshold_gating(st, resolve_crop_id("قمح"), 60)
    rs = st["remote_sensing"]
    assert rs["ndvi_thresholds_enabled"] is True  # العلم مفعَّل
    assert rs["thresholds_applied"] is False  # لكن لا عتبات معايَرة ⇒ لا تطبيق
    assert rs["threshold_source"] is None
    assert rs["calibration_status"] == "insufficient_field_calibration"


def test_thresholds_for_real_crop_is_none():
    """لا بطاقة محصول تحمل ndvi_thresholds معايَرة ⇒ None (لا عتبات مُلفَّقة)."""
    assert _ndvi_thresholds_for(resolve_crop_id("قمح"), 60) is None
    assert _ndvi_thresholds_for(None, 60) is None
    assert _ndvi_thresholds_for("nonexistent_crop_xyz", 60) is None


def test_no_remote_sensing_block_is_safe(monkeypatch):
    """غياب كتلة remote_sensing (أو ليست dict) ⇒ لا كسر (fail-safe)."""
    monkeypatch.setenv(_FLAG, "1")
    st = {}  # لا remote_sensing
    _apply_ndvi_threshold_gating(st, resolve_crop_id("قمح"), 60)  # لا يرمي
    assert "remote_sensing" not in st


def test_flag_on_no_crop_insufficient(monkeypatch):
    """ON بلا محصول (crop_id None) ⇒ insufficient (لا أساس للمعايرة)."""
    monkeypatch.setenv(_FLAG, "1")
    st = _state_with_ndvi()
    _apply_ndvi_threshold_gating(st, None, None)
    rs = st["remote_sensing"]
    assert rs["thresholds_applied"] is False
    assert rs["calibration_status"] == "insufficient_field_calibration"

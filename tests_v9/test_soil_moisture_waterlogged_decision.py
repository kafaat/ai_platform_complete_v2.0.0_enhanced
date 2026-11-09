"""Saturation in the sensor advisor: VWC near θs is "waterlogged", never "safe".

``api/soil_moisture_advisor`` declared θs per texture and used it nowhere, so a reading at
saturation fell through to the RWC ≥ 80 % branch and was reported "safe — no irrigation
needed". Waterlogging is a root-zone hazard of its own (oxygen starvation, root rot), not a
synonym for "plenty of water". The decision now has a fourth state, ``waterlogged``, above
θFC + k·(θs − θFC) with k = 0.5; between θFC and that threshold the decision stays "safe".
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_PLATFORM = Path(__file__).resolve().parent.parent / "services" / "sahool-platform"
if str(_PLATFORM) not in sys.path:
    sys.path.insert(0, str(_PLATFORM))

from api.soil_moisture_advisor import (  # noqa: E402
    _SOIL_DISPLAY,
    _soil_params,
    compute_rwc,
    irrigation_guidance,
    waterlogged_threshold,
)


@pytest.mark.parametrize("soil_type", sorted(_SOIL_DISPLAY))
def test_vwc_at_saturation_is_waterlogged(soil_type):
    theta_s = _SOIL_DISPLAY[soil_type]["theta_s"]
    out = compute_rwc(theta_s, soil_type)
    assert out["decision"] == "waterlogged"
    assert out["irrigation_allowed"] is False
    assert "غدق" in out["decision_ar"]
    assert "لا تروِ" in out["decision_ar"]
    assert out["theta_s"] == pytest.approx(theta_s)


@pytest.mark.parametrize("soil_type", sorted(_SOIL_DISPLAY))
def test_threshold_is_midway_between_fc_and_saturation(soil_type):
    p = _soil_params(soil_type)
    expected = p["theta_fc"] + 0.5 * (p["theta_s"] - p["theta_fc"])
    assert waterlogged_threshold(p["theta_fc"], p["theta_s"]) == pytest.approx(expected)
    assert compute_rwc(expected, soil_type)["decision"] == "waterlogged"
    just_below = expected - 0.005
    assert just_below >= p["theta_fc"]
    below = compute_rwc(just_below, soil_type)
    assert below["decision"] == "safe"
    assert below["irrigation_allowed"] is False


def test_field_capacity_band_stays_safe_and_dry_still_irrigates():
    p = _soil_params("loam")
    assert compute_rwc(p["theta_fc"], "loam")["decision"] == "safe"
    dry = compute_rwc(p["theta_wp"], "loam")
    assert dry["decision"] == "irrigate"
    assert dry["irrigation_allowed"] is True


def test_waterlogged_guidance_never_suggests_water_or_priority():
    theta_s = _SOIL_DISPLAY["loam"]["theta_s"]
    g = irrigation_guidance(theta_s, "loam", crop="ذرة", growth_stage="الإزهار")
    assert g["decision"] == "waterlogged"
    assert "irrigation_amount" not in g
    # A sensitive stage must not turn a waterlogged field into "give irrigation priority".
    assert g["stage_sensitivity_note_ar"] is None


def test_calibrated_fc_above_texture_saturation_has_no_waterlogged_reference():
    # θFC calibrated above the texture's θs ⇒ no valid saturation reference ⇒ no invented
    # waterlogging verdict; the reading stays in the no-irrigation "safe" band.
    out = compute_rwc(0.52, "loam", theta_fc=0.50, theta_wp=0.20)
    assert out["waterlogged_threshold_vwc"] is None
    assert out["decision"] == "safe"
    assert waterlogged_threshold(0.50, 0.47) is None

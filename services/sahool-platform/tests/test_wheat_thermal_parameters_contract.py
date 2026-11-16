"""crop-4 contract: one wheat maturity GDD and one base temperature across the platform.

Wheat carried three maturity values: 1600 in ``api.gdd_tracker``, 1800 in
``api.season_simulation`` and 2000 in the crop card read by ``core.gdd_phenology``. A field
could be "mature" in the GDD tracker, mid grain-fill in the season state and short of maturity
in the simulation, all from the same thermal sum. The crop card is now the single source;
this test fails if any of the three drifts from it again.
"""

from __future__ import annotations

import pytest
from api.gdd_tracker import GDD_CROP_PARAMS, stage_result_from_cumulative
from api.season_simulation import (
    PARAMETER_VERSION,
    PARAMETER_VERSION_HISTORY,
    _params_for,
    crop_gdd_policy,
)
from core.crop_cards.loader import load_crop_card
from core.gdd_phenology import gdd_base_c, gdd_stage_thresholds, gdd_to_maturity, phenology_progress

pytestmark = pytest.mark.unit


def test_wheat_maturity_gdd_agrees_across_tracker_simulation_and_phenology():
    card = load_crop_card("wheat")["thermal"]["gdd_to_maturity"]
    tracker = dict(GDD_CROP_PARAMS["wheat"]["stages"])["maturity"]
    simulation = _params_for("wheat").gdd_to_maturity
    phenology = phenology_progress("wheat", 0, 0.0)["gdd_to_maturity"]
    last_band_end = gdd_stage_thresholds("wheat")[-1]["gdd_end"]
    values = {
        "card": card,
        "gdd_tracker": tracker,
        "season_simulation": simulation,
        "gdd_phenology": phenology,
        "gdd_phenology.last_band_end": last_band_end,
        "gdd_to_maturity()": gdd_to_maturity("wheat"),
    }
    assert len({float(v) for v in values.values()}) == 1, (
        f"wheat maturity GDD must be one value from the crop card, got {values}"
    )


def test_wheat_base_temperature_agrees():
    values = {
        "card": gdd_base_c("wheat"),
        "gdd_tracker": GDD_CROP_PARAMS["wheat"]["t_base"],
        "season_simulation": crop_gdd_policy("wheat")[0],
    }
    assert len({float(v) for v in values.values()}) == 1, (
        f"wheat GDD base must be one value from the crop card, got {values}"
    )


def test_the_same_sum_is_mature_everywhere_or_nowhere():
    maturity = gdd_to_maturity("wheat")
    below = maturity - 1.0
    assert stage_result_from_cumulative("wheat", maturity, 120).current_stage == "maturity", (
        "the tracker calls the card maturity sum mature"
    )
    assert phenology_progress("wheat", 120, maturity)["maturity_reached_gdd"] is True, (
        "the phenology resolver calls the same sum mature"
    )
    assert stage_result_from_cumulative("wheat", below, 120).current_stage != "maturity", (
        "one GDD short is not mature in the tracker"
    )
    assert phenology_progress("wheat", 120, below)["maturity_reached_gdd"] is False, (
        "one GDD short is not mature in the phenology resolver"
    )


def test_simulation_parameter_version_describes_the_live_wheat_parameters():
    """crop-4 review: stored runs name the parameters that produced them.

    ``season_simulation_runs`` is append-only and carries ``parameter_version``. Moving wheat
    maturity from 1800 to the card's 2000 under the same version would make two different
    parameter sets indistinguishable in stored rows.
    """
    live = _params_for("wheat")
    recorded = PARAMETER_VERSION_HISTORY.get(PARAMETER_VERSION, {}).get("wheat")
    assert recorded == {"t_base_c": live.t_base_c, "gdd_to_maturity": live.gdd_to_maturity}, (
        f"{PARAMETER_VERSION} must record the live wheat parameters, got {recorded}"
    )
    old = PARAMETER_VERSION_HISTORY.get("sahool-season-defaults/1", {}).get("wheat")
    assert old == {"t_base_c": 0.0, "gdd_to_maturity": 1800.0}, (
        "rows already stored under /1 stay interpretable: their wheat parameters are recorded"
    )
    assert PARAMETER_VERSION != "sahool-season-defaults/1", (
        "the version must change when wheat maturity changed from 1800 to the card value"
    )

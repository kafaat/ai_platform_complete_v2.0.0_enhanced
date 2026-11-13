"""Disease diagnosis matches crop rules on the canonical crop key.

A field's crop is stored as typed or as another system wrote it ("Wheat", "قمح",
" wheat "). The rules carry lowercase English keys, so a literal comparison
silently skipped every crop-specific rule and the result said "no known match".
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../services/sahool-platform"))

pytestmark = pytest.mark.unit

RUST = ["orange_pustules", "leaf_yellowing", "powder_on_touch"]


def _codes(crop):
    from api.disease_diagnosis import diagnose

    return [c.issue_code for c in diagnose(crop, RUST).candidates]


@pytest.mark.parametrize("crop", ["wheat", "Wheat", " wheat ", "WHEAT", "قمح"])
def test_wheat_rust_matches_whatever_the_crop_spelling(crop):
    assert "wheat.rust" in _codes(crop), crop


@pytest.mark.parametrize("crop", ["شعير", "Barley"])
def test_barley_spellings_reach_the_shared_rust_rule(crop):
    assert "wheat.rust" in _codes(crop), crop


def test_an_unrelated_crop_still_does_not_get_wheat_rules():
    assert "wheat.rust" not in _codes("tomato")
    assert "wheat.rust" not in _codes("طماطم")


def test_unknown_or_empty_crop_never_widens_to_crop_specific_rules():
    assert "wheat.rust" not in _codes("xyz")
    assert "wheat.rust" not in _codes("")


def test_the_response_keeps_the_crop_as_sent():
    from api.disease_diagnosis import diagnose

    assert diagnose("قمح", RUST).to_dict()["crop"] == "قمح"

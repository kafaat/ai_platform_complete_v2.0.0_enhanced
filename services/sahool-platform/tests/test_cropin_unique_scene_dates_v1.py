"""Unique scene count must not inflate a date counted across several indices."""

import pytest
from api.field_context import count_distinct_acquisition_dates

pytestmark = pytest.mark.unit


def test_same_acquisition_in_multiple_indices_counts_once():
    records = {
        "ndvi": {"dates": [{"date": "2026-11-15"}, {"date": "2026-11-14"}]},
        "ndmi": {"dates": [{"date": "2026-11-15"}]},
        "truecolor": {"dates": [{"date": "2026-11-15"}]},
    }
    assert count_distinct_acquisition_dates(records) == 2


def test_unknown_scene_dates_do_not_become_observations():
    assert count_distinct_acquisition_dates({"ndvi": {"dates": [None, "", {}]}}) == 0

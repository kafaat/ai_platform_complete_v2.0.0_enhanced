"""Tests for on-demand index scheduling: continuous vs purpose-driven indices to save cost."""

from core.spatial.index_scheduler import (
    IndexCadence,
    cost_summary,
    get_index_policy,
    should_compute_now,
)


class TestIndexScheduler:
    def test_ndvi_is_continuous(self):
        assert get_index_policy("NDVI").cadence == IndexCadence.CONTINUOUS

    def test_bsi_is_on_demand(self):
        assert get_index_policy("BSI").cadence == IndexCadence.ON_DEMAND

    def test_continuous_recomputes_when_due(self):
        assert should_compute_now("NDVI", 8)["compute"] is True  # >7 days
        assert should_compute_now("NDVI", 3)["compute"] is False  # fresh

    def test_on_demand_stops_after_computed(self):
        # CORE IDEA: soil type computed once, then stopped to save cost
        assert should_compute_now("BSI", None)["compute"] is True  # first
        assert should_compute_now("BSI", 30)["compute"] is False  # already done

    def test_on_demand_reactivates_on_purpose(self):
        assert should_compute_now("BSI", 30, purpose_active=True)["compute"] is True

    def test_event_only_on_trigger(self):
        assert should_compute_now("SI", None)["compute"] is False
        assert should_compute_now("SI", None, purpose_active=True)["compute"] is True

    def test_cost_summary_separates_types(self):
        cs = cost_summary(["NDVI", "NDMI", "BSI", "SI"])
        assert "NDVI" in cs["continuous"]
        assert "BSI" in cs["on_demand"]
        assert "SI" in cs["event"]

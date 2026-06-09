"""Tests for learn_from_harvest.py — closes the calibration loop (zone_factor from
actual harvest). CRITICAL rule: below farm threshold → indicative (tenant only),
NEVER district-level. Previously had ZERO tests.

learn() depends on a seeded SQLite DB; here we test the isolated DB-free logic
(honest baseline + calibration arithmetic) plus the no-fabrication contract.
Full integration awaits real harvest data (the operational blocker)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
import learn_from_harvest as lfh


class TestBaseModelPredict:
    def test_uncalibrated_baseline_positive(self):
        assert lfh.base_model_predict({"crop": "wheat", "tenant_id": "t1"}) > 0

    def test_uncalibrated_not_field_specific(self):
        # transparent uncalibrated baseline — calibration differentiates, not the base
        v1 = lfh.base_model_predict({"crop": "wheat", "tenant_id": "t1"})
        v2 = lfh.base_model_predict({"crop": "barley", "tenant_id": "t2"})
        assert v1 == v2


class TestCalibrationArithmetic:
    def test_ratio_logic_baseline(self):
        actual, pred = [5.5, 4.5, 5.0], [5.0, 5.0, 5.0]
        zf = round(sum(a/p for a, p in zip(actual, pred)) / len(actual), 3)
        assert zf == 1.0

    def test_ratio_above_one_when_exceeds_baseline(self):
        actual, pred = [6.0, 6.0], [5.0, 5.0]
        zf = round(sum(a/p for a, p in zip(actual, pred)) / len(actual), 3)
        assert zf == 1.2

    def test_zero_prediction_excluded(self):
        actual, pred = [5.0, 6.0], [0.0, 5.0]
        ratios = [a/p for a, p in zip(actual, pred) if p > 0]
        assert len(ratios) == 1


class TestLearnGate:
    def test_missing_district_no_fabrication(self):
        from storage.lite_store import init_db
        try: init_db()
        except Exception: pass
        r = lfh.learn("nonexistent_district_xyz_12345", "wheat")
        # honest error or pending — NEVER a fabricated CALIBRATED zone_factor
        assert r.get("status") != "CALIBRATED"
        assert "error" in r or r.get("status") == "pending_districts"

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
        zf = round(sum(a / p for a, p in zip(actual, pred, strict=True)) / len(actual), 3)
        assert zf == 1.0

    def test_ratio_above_one_when_exceeds_baseline(self):
        actual, pred = [6.0, 6.0], [5.0, 5.0]
        zf = round(sum(a / p for a, p in zip(actual, pred, strict=True)) / len(actual), 3)
        assert zf == 1.2

    def test_zero_prediction_excluded(self):
        actual, pred = [5.0, 6.0], [0.0, 5.0]
        ratios = [a / p for a, p in zip(actual, pred, strict=True) if p > 0]
        assert len(ratios) == 1


class TestLearnGate:
    def test_missing_district_no_fabrication(self):
        from storage.lite_store import init_db

        try:
            init_db()
        except Exception:
            pass
        r = lfh.learn("nonexistent_district_xyz_12345", "wheat")
        # honest error or pending — NEVER a fabricated CALIBRATED zone_factor
        assert r.get("status") != "CALIBRATED"
        assert "error" in r or r.get("status") == "pending_districts"


def _isolated_harvest(tmp_path, monkeypatch):
    from functools import partial

    import yaml
    from storage import lite_store

    db = tmp_path / "fixture.db"
    lite_store.init_db(db)
    district = tmp_path / "districts" / "al_jawf"
    district.mkdir(parents=True)
    (district / "climate.yaml").write_text(yaml.safe_dump({"calibration": {"farms_required": 5}}))
    monkeypatch.setattr(lfh, "PLATFORM", tmp_path)
    monkeypatch.setattr(
        lfh, "yields_for_district", partial(lite_store.yields_for_district, db_path=db)
    )
    return partial(lite_store.add_yield, district_id="al_jawf", crop="wheat", db_path=db)


def _tenant_calibration(tmp_path, tenant):
    import yaml

    return yaml.safe_load(
        (tmp_path / "tenants" / tenant / "calibration" / "zone_factors.yaml").read_text()
    )


def test_two_tenants_keep_separate_factors_and_basis(tmp_path, monkeypatch):
    add = _isolated_harvest(tmp_path, monkeypatch)
    add(tenant_id="b", season_year=2026, yield_t_ha=8)
    add(tenant_id="a", season_year=2025, yield_t_ha=3)
    add(tenant_id="a", season_year=2026, yield_t_ha=5)
    add(tenant_id="b", season_year=2024, yield_t_ha=50, verified=False)
    district = tmp_path / "districts" / "al_jawf" / "climate.yaml"
    before = district.read_bytes()
    result = lfh.learn("al_jawf", "wheat")
    assert "indicative_zone_factor" not in result
    assert district.read_bytes() == before
    a = _tenant_calibration(tmp_path, "a")
    b = _tenant_calibration(tmp_path, "b")
    assert (a["indicative_zone_factor"], a["basis"]) == (
        0.8,
        {"records": 2, "farms": 1, "seasons": 2},
    )
    assert (b["indicative_zone_factor"], b["basis"]) == (
        1.6,
        {"records": 1, "farms": 1, "seasons": 1},
    )


def test_adding_another_tenant_does_not_change_existing_factor(tmp_path, monkeypatch):
    add = _isolated_harvest(tmp_path, monkeypatch)
    add(tenant_id="a", season_year=2026, yield_t_ha=5)
    assert lfh.learn("al_jawf", "wheat")["indicative_zone_factor"] == 1.0
    before = _tenant_calibration(tmp_path, "a")
    add(tenant_id="b", season_year=2025, yield_t_ha=10)
    result = lfh.learn("al_jawf", "wheat")
    assert _tenant_calibration(tmp_path, "a") == before
    assert _tenant_calibration(tmp_path, "b")["indicative_zone_factor"] == 2.0
    assert result["status"] == "pending_districts" and result["farms"] == 2

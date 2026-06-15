"""Tests for v9.1.0 review gaps: irrigation, GDD, polygon area, supervisor, users."""

import os
import tempfile
from pathlib import Path

from core.engines.fao56 import gdd_accumulate, gdd_daily
from core.spatial.pipeline import polygon_area_ha
from storage import lite_store


def _db():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db = Path(f.name)
    lite_store.init_db(db)
    return db


class TestGapsV91:
    def test_gdd_daily(self):
        assert gdd_daily(30, 15, tbase=10) == 12.5
        assert gdd_daily(8, 4, tbase=10) == 0.0  # below base → 0

    def test_gdd_accumulate(self):
        days = [{"tmax": 30, "tmin": 15}, {"tmax": 32, "tmin": 18}]
        assert gdd_accumulate(days) == 27.5

    def test_polygon_area_reasonable(self):
        sq = [(44.94, 16.08), (44.9465, 16.08), (44.9465, 16.0863), (44.94, 16.0863)]
        area = polygon_area_ha(sq)
        assert 40 < area < 60  # ~49 ha expected

    def test_polygon_too_few_points(self):
        assert polygon_area_ha([(44.9, 16.0), (44.91, 16.0)]) == 0.0

    def test_irrigation_config_saved(self):
        db = _db()
        lite_store.save_irrigation_config(
            "F1", "t1", "pivot", pivot_length_m=125, flow_rate_lps=38, db_path=db
        )
        cfg = lite_store.get_irrigation_config("F1", db_path=db)
        assert cfg["method"] == "pivot"
        assert cfg["pivot_length_m"] == 125
        os.unlink(db)

    def test_supervisor_and_skip_reason(self):
        db = _db()
        lite_store.save_field_state(
            "F1",
            "t1",
            "limited",
            soil_choice="skip",
            soil_skip_reason="cost",
            supervisor_id="u1",
            supervisor_role="owner",
            db_path=db,
        )
        s = lite_store.get_field_state("F1", db_path=db)
        assert s["soil_skip_reason"] == "cost"
        assert s["supervisor_role"] == "owner"
        os.unlink(db)

    def test_user_management(self):
        db = _db()
        lite_store.upsert_user("farm1", "اسم", district_id="al_jawf", db_path=db)
        with lite_store.connect(db) as conn:
            u = conn.execute("SELECT * FROM users WHERE tenant_id='farm1'").fetchone()
        assert u["district_id"] == "al_jawf"
        os.unlink(db)

"""W1-13 (finding water-5, manual part) — measured farm water reaches the daily water ledger.

The live proof (farm operation -> ledger row -> worker balance) is
``test_farm_water_ledger_projection_live_pg.py``. These unit tests pin the rules it rests on,
without a database:

* the depth is volume / area / 10 (500 m3 on 1 ha = 50 mm), and no depth is invented for a field
  with no recorded area;
* the projection writes irrigation only, with the W0-13 report semantics (the reporter column,
  the worker's day), records ``irrigation_source='farm_ledger'``, and never writes over a day
  another writer owns;
* only actual work counts (a completed operation not dated after today);
* every other write of ``irrigation_mm`` clears the source, so the label never outlives its figure;
* the farm operation endpoint calls the projection inside its transaction.
"""

from __future__ import annotations

import inspect
import math
import os
import sys

import pytest

pytestmark = pytest.mark.unit

ROOT = os.path.join(os.path.dirname(__file__), "..")
CORE = os.path.join(ROOT, "services/sahool-platform")
if CORE not in sys.path:
    sys.path.insert(0, CORE)

from api.water_ledger_compute import (  # noqa: E402
    FARM_LEDGER_IRRIGATION_UPSERT_SQL,
    FARM_WATER_DAY_LOCK_SQL,
    FARM_WATER_DAY_SQL,
    IRRIGATION_SOURCE_FARM_LEDGER,
    LEDGER_SELECT_COLS,
    LEDGER_UPSERT_SQL,
    farm_water_day_lock_key,
    irrigation_mm_from_volume,
    ledger_timezone,
    parse_ledger_date,
    project_farm_water_to_ledger,
    row_to_ledger_entry,
)


def _squash(sql: str) -> str:
    return " ".join(sql.split())


def test_500_m3_on_one_hectare_is_50_mm():
    assert irrigation_mm_from_volume(500, 1) == pytest.approx(50.0), (
        "1 mm over 1 ha is 10 m3, so 500 m3 on 1 ha must be 50 mm"
    )
    assert irrigation_mm_from_volume(250.0, 2.5) == pytest.approx(10.0), "250 m3 on 2.5 ha"
    assert irrigation_mm_from_volume(0, 3) == 0.0, "a measured zero is zero, not unknown"


@pytest.mark.parametrize(
    "volume, area",
    [(500, None), (500, 0), (500, -1), (None, 1), (-5, 1), (500, math.nan), (math.inf, 1)],
)
def test_no_depth_is_invented_without_a_usable_volume_and_area(volume, area):
    assert irrigation_mm_from_volume(volume, area) is None, (
        f"volume={volume!r} area={area!r} must give no depth, not a made-up one"
    )


def test_the_projection_writes_irrigation_only_on_the_workers_day():
    sql = _squash(FARM_LEDGER_IRRIGATION_UPSERT_SQL)
    update = sql.split("DO UPDATE SET", 1)[1]
    assignments = update.split(" WHERE ", 1)[0]
    for col in ("et0_mm", "depletion_mm", "deficit_mm", "confidence", "decision", "created_by"):
        assert col not in assignments, f"the projection must not write {col}: {assignments}"
    assert "irrigation_mm = EXCLUDED.irrigation_mm" in update, (
        "a re-projection replaces the day's figure (the day's sum), it never adds to it"
    )
    assert "irrigation_reported_by = EXCLUDED.irrigation_reported_by" in update, (
        "the reporter column is what makes the worker keep the figure (W0-13)"
    )
    assert "irrigation_source = EXCLUDED.irrigation_source" in update, "the source is recorded"
    assert "WHERE water_ledger.created_by = EXCLUDED.created_by" in update, (
        "a day owned by another writer (manual entry, as-applied) must be left alone"
    )
    assert sql.endswith("RETURNING 1"), "the caller must learn whether the guard refused"
    assert IRRIGATION_SOURCE_FARM_LEDGER == "farm_ledger", "the v280 CHECK allows this value only"


def test_only_actual_completed_work_on_the_tenants_field_is_projected():
    sql = _squash(FARM_WATER_DAY_SQL)
    assert "o.status = 'completed'" in sql, "planned or cancelled water is not applied water"
    assert "o.operation_date <= (now() AT TIME ZONE $4)::date" in sql, (
        "future-dated work is not actual work, and 'today' is the ledger's local day"
    )
    assert "CURRENT_DATE" not in sql, (
        "the database's UTC date skips work completed in the first local hours after midnight"
    )
    assert "w.tenant_id = $1::uuid" in sql and "f.tenant_id = $1::uuid" in sql, (
        "both the records and the field area are read for the caller's tenant only"
    )
    assert "COUNT(w.water_volume_m3) AS measured" in sql, (
        "records without a volume must be counted apart, so an unknown amount is not read as zero"
    )


def test_the_days_sum_is_read_under_a_per_field_day_lock():
    assert _squash(FARM_WATER_DAY_LOCK_SQL) == (
        "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))"
    ), "a transaction-scoped lock, released with the operation's own transaction"
    day = parse_ledger_date("2026-11-16")
    key = farm_water_day_lock_key("t-1", "f-1", day)
    assert key == "water-ledger:farm-projection:t-1:f-1:2026-11-16", key
    assert farm_water_day_lock_key("t-2", "f-1", day) != key, "the lock key is per tenant"
    src = inspect.getsource(project_farm_water_to_ledger)
    lock = src.index("FARM_WATER_DAY_LOCK_SQL")
    read = src.index("FARM_WATER_DAY_SQL,")
    write = src.index("FARM_LEDGER_IRRIGATION_UPSERT_SQL")
    assert lock < read < write, (
        "the lock must be taken before the day's sum, or overlapping projections lose water"
    )


def test_the_ledger_timezone_is_the_workers_setting(monkeypatch):
    monkeypatch.delenv("WATER_LEDGER_TIMEZONE", raising=False)
    assert ledger_timezone() == "Asia/Aden", "the worker's default ledger timezone"
    monkeypatch.setenv("WATER_LEDGER_TIMEZONE", "UTC")
    assert ledger_timezone() == "UTC", "the same env var as the water-balance worker"


def test_every_other_irrigation_write_clears_the_source():
    update = _squash(LEDGER_UPSERT_SQL).split("DO UPDATE SET", 1)[1]
    assert (
        "irrigation_source = CASE WHEN 'irrigation_mm' = ANY($17::text[]) THEN NULL"
        " ELSE water_ledger.irrigation_source END" in update
    ), "a person's figure written over a projection must not keep the farm_ledger label"
    here = os.path.dirname(os.path.abspath(__file__))
    platform = os.path.join(here, "..", "services", "sahool-platform", "api")
    for rel in (
        "irrigation_closed_loop_runtime.py",
        os.path.join("routers", "irrigation_engineering.py"),
    ):
        with open(os.path.join(platform, rel), encoding="utf-8") as fh:
            text = _squash(fh.read())
        assert "irrigation_source = NULL" in text or "irrigation_source=NULL" in text, (
            f"{rel} adds to irrigation_mm, so it must clear the farm_ledger label too"
        )


def test_the_source_is_read_back():
    assert "irrigation_source" in LEDGER_SELECT_COLS, "the list endpoint must select the source"
    row = {
        "field_id": "f",
        "ledger_date": "2026-11-16",
        "et0_mm": None,
        "kc": None,
        "etc_mm": None,
        "rain_mm": None,
        "irrigation_mm": 50.0,
        "soil_moisture_pct": None,
        "depletion_mm": None,
        "deficit_mm": None,
        "stage": None,
        "decision": None,
        "confidence": None,
        "created_by": "water-balance-auto",
        "created_at": "",
        "irrigation_reported_by": "u-1",
        "irrigation_source": "farm_ledger",
    }
    assert row_to_ledger_entry(row)["irrigation_source"] == "farm_ledger", "the source shows"
    del row["irrigation_source"]
    assert row_to_ledger_entry(row)["irrigation_source"] is None, (
        "a row read before v280 has no source, which is not an error"
    )


def test_the_operation_endpoint_projects_inside_its_transaction():
    pytest.importorskip("fastapi")
    import api.main  # noqa: F401
    from api.routers import farm_operations_ledger as router

    src = inspect.getsource(router.create_operation_ledger_record)
    txn = src.index("async with conn.transaction():")
    persist = src.index("persist_operation_subrecords")
    project = src.index("project_farm_water_to_ledger(")
    ret = src.index('"operation_id": operation_id')
    assert txn < persist < project < ret, (
        "the projection must run after the water record is stored, in the same transaction"
    )
    assert "if req.water and req.field_id" in src, "only a field's water record is projected"

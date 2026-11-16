"""W0-13 (finding mobile-3) — partial semantics of the water-ledger write, without a database.

The live proof (offline report, worker, replay) is ``test_water_ledger_partial_write_live_pg.py``.
These unit tests pin the pure rules it rests on, so a regression shows up in every job:

* only the columns the caller sent are written on conflict;
* a body of ``{ledger_date, irrigation_mm}`` is an irrigation report, which does not take the day
  away from the worker, and which the worker keeps as the day's irrigation;
* only ``created_by`` decides whether the worker computes a day: a reporter column never hands it
  a day another writer (a manual entry, an as-applied reconciliation) holds;
* an empty write, or a report without a figure, is refused before the database is touched.
"""

from __future__ import annotations

import inspect
import os
import re
import sys
import uuid

import pytest

pytestmark = pytest.mark.unit

ROOT = os.path.join(os.path.dirname(__file__), "..")
CORE = os.path.join(ROOT, "services/sahool-platform")
if CORE not in sys.path:
    sys.path.insert(0, CORE)

from api.water_ledger_auto import (  # noqa: E402
    AUTO_CREATED_BY,
    manual_entry_takes_precedence,
    reported_irrigation,
)
from api.water_ledger_compute import (  # noqa: E402
    LEDGER_SELECT_COLS,
    LEDGER_WRITABLE_COLUMNS,
    is_irrigation_report,
    ledger_write_columns,
    row_to_ledger_entry,
)


class _User:
    def __init__(self):
        self.tenant_id = uuid.uuid4()
        self.user_id = "u-farmer"


@pytest.fixture
def wl_mod():
    pytest.importorskip("fastapi")
    import api.main  # noqa: F401
    import api.routers.water_ledger as m

    return m


def test_only_the_sent_columns_are_written():
    assert ledger_write_columns({"ledger_date", "irrigation_mm"}) == ("irrigation_mm",), (
        "ledger_date is the key, not a column to write"
    )
    assert ledger_write_columns({"ledger_date", "decision", "et0_mm"}) == ("et0_mm", "decision"), (
        "columns come back in INSERT order"
    )
    assert ledger_write_columns({"ledger_date"}) == (), "nothing sent, nothing to write"
    assert set(LEDGER_WRITABLE_COLUMNS) == {
        "et0_mm",
        "kc",
        "etc_mm",
        "rain_mm",
        "irrigation_mm",
        "soil_moisture_pct",
        "depletion_mm",
        "deficit_mm",
        "stage",
        "decision",
        "confidence",
    }, "the writable set must match WaterLedgerUpsertRequest"


def test_an_irrigation_report_is_the_applied_water_alone():
    assert is_irrigation_report(("irrigation_mm",)) is True, "the mobile body is a report"
    assert is_irrigation_report(("irrigation_mm", "et0_mm")) is False, "a full entry is not"
    assert is_irrigation_report(()) is False, "an empty write is not a report"


def test_a_report_never_blocks_the_worker_but_a_manual_entry_does():
    assert manual_entry_takes_precedence("u-farmer") is True, "a manual entry is the person's day"
    assert manual_entry_takes_precedence(AUTO_CREATED_BY) is False, "the worker's own row"
    assert manual_entry_takes_precedence(None) is False, "no row yet"
    assert manual_entry_takes_precedence("as_applied:deadbeef") is True, (
        "an as-applied reconciliation holds its day, whoever reported water on it before"
    )
    params = inspect.signature(manual_entry_takes_precedence).parameters
    assert list(params) == ["existing_created_by"], (
        "the reporter column must not take part in the precedence decision"
    )


def test_the_reported_figure_is_the_days_irrigation():
    assert reported_irrigation(None) is None, "no row, no report"
    assert reported_irrigation({"irrigation_reported_by": None, "irrigation_mm": 5.0}) is None, (
        "the worker's own figure is not a report"
    )
    assert reported_irrigation({"irrigation_reported_by": "u", "irrigation_mm": 12}) == 12.0, (
        "a report is used as the day's total"
    )
    assert reported_irrigation({"irrigation_reported_by": "u", "irrigation_mm": None}) is None, (
        "a cleared figure is no report"
    )


def test_the_entry_exposes_who_reported_and_reads_rows_without_the_column():
    row = {
        "field_id": "f",
        "ledger_date": "2026-11-16",
        "created_at": "x",
        "created_by": AUTO_CREATED_BY,
        **dict.fromkeys(LEDGER_WRITABLE_COLUMNS),
    }
    assert row_to_ledger_entry(row)["irrigation_reported_by"] is None, (
        "a row read before v280 (or a stub) has no such key and must still map"
    )
    row["irrigation_reported_by"] = "u-farmer"
    assert row_to_ledger_entry(row)["irrigation_reported_by"] == "u-farmer", "the reporter shows"
    assert "irrigation_reported_by" in LEDGER_SELECT_COLS, "the list endpoint selects it"


def test_every_column_is_written_on_conflict_only_when_sent(wl_mod):
    sql = wl_mod.LEDGER_UPSERT_SQL
    assert "ON CONFLICT (field_id, ledger_date) DO UPDATE" in sql, "still an idempotent upsert"
    for col in LEDGER_WRITABLE_COLUMNS:
        guarded = (
            f"{col} = CASE WHEN '{col}' = ANY($17::text[]) THEN EXCLUDED.{col} "
            f"ELSE water_ledger.{col} END"
        )
        assert guarded in sql, f"{col} is written on conflict even when the caller omitted it"
    update = sql.split("DO UPDATE SET", 1)[1]
    assert not re.search(r"\b(\w+) = EXCLUDED\.\1\s*,", update), (
        "a bare `x = EXCLUDED.x` overwrites an omitted column with NULL (finding mobile-3)"
    )
    assert "created_by = EXCLUDED" not in update, "a person's write does not rewrite the author"
    assert ("WHEN $16::text IS NOT NULL AND water_ledger.created_by = $18 THEN $16") in update, (
        "a report records its reporter only on a day the worker owns"
    )
    assert "WHEN $16::text IS NOT NULL THEN water_ledger.irrigation_reported_by" in update, (
        "a report on a manual or as-applied day must leave the reporter column alone"
    )
    assert "THEN CASE WHEN EXCLUDED.irrigation_mm IS NULL THEN NULL ELSE $19 END" in update, (
        "a full entry that clears the figure must clear the reporter"
    )
    assert (
        "created_by = CASE WHEN $16::text IS NULL AND (water_ledger.created_by = $18"
        " AND water_ledger.decision IS NULL)"
        " THEN $19 ELSE water_ledger.created_by END"
    ) in update, (
        "a full entry takes any worker day the worker has not computed (a report opened it, or "
        "a farm-ledger projection opened it and later withdrew its figure, W1-13)"
    )


async def test_an_empty_write_is_refused_before_the_database(wl_mod, monkeypatch):
    from fastapi import HTTPException

    monkeypatch.setattr(wl_mod.api_main, "_DB_POOL", None, raising=True)
    req = wl_mod.WaterLedgerUpsertRequest(ledger_date="2026-11-16")
    with pytest.raises(HTTPException) as caught:
        await wl_mod.upsert_water_ledger(req=req, field_id="f", user=_User())
    assert caught.value.status_code == 422, "an empty row used to block the worker for the day"


async def test_a_report_without_a_figure_is_refused(wl_mod, monkeypatch):
    from fastapi import HTTPException

    monkeypatch.setattr(wl_mod.api_main, "_DB_POOL", None, raising=True)
    req = wl_mod.WaterLedgerUpsertRequest(ledger_date="2026-11-16", irrigation_mm=None)
    with pytest.raises(HTTPException) as caught:
        await wl_mod.upsert_water_ledger(req=req, field_id="f", user=_User())
    assert caught.value.status_code == 422, "a report must carry the applied water"


def test_the_worker_keeps_a_reported_figure_and_never_writes_over_a_manual_day():
    from api import phase_runtime_workers as mod

    src = inspect.getsource(mod.run_water_ledger_once)
    assert "WHEN water_ledger.irrigation_reported_by IS NOT NULL" in src, (
        "the worker must not overwrite a report that lands between its read and its write"
    )
    assert "THEN water_ledger.irrigation_mm" in src, "the reported figure is kept on conflict"
    assert "WHERE water_ledger.created_by = EXCLUDED.created_by\n" in src, (
        "the worker's upsert must not write over a manual entry made after its read"
    )
    assert "OR water_ledger.irrigation_reported_by" not in src, (
        "a reporter column must never let the worker write over another writer's day"
    )
    assert "if stored is None:" in src, "a write the guard refused must not reach the bridge"
    assert "reported_irrigation(existing)" in src, "the report feeds the day's balance"
    assert 'manual_entry_takes_precedence(existing["created_by"])' in src, (
        "only created_by decides whether the worker computes the day"
    )

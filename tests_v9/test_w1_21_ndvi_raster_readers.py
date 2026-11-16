"""W1-21 (remote-2 / data-7 / fields-8): NDVI and twin indices come from raster-service.

NL-GIS ``ndvi_drop`` and decision confidence read ``ndvi_timeseries`` (a tenant-less ``RANDOM()``
seed with no live writer); the field twin read ``field_indicators`` (no live writer). All three
now read the raster path, ``api.raster_service_client.latest_index_points``. Pinned here:

1. a repository-wide grep: no service SQL reads ``ndvi_timeseries`` / ``field_indicators`` (or
   the ``v_latest_ndvi`` / ``v_field_summary`` views built on the seed);
2. ``latest_index_points`` asks raster for the newest processed dates only, keeps real finite
   means, and keeps "raster unavailable" (``None``) apart from "no observation" (``[]``);
3. each router's raster stage, with the raster read stubbed at its function: decision
   confidence's freshness, the twin's per-index rows and NL-GIS's drop comparison, including
   the outage paths (never a fabricated value, never an outage shown as an empty field).
"""

from __future__ import annotations

import os
import re
import sys
from datetime import date
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, os.path.join(ROOT, "services", "sahool-platform"))

from api import raster_service_client as rsc  # noqa: E402

# A SQL read of the seed-only tables or of the views over them.
_LEGACY_READ = re.compile(
    r"\b(?:FROM|JOIN)\s+(?:public\.)?(ndvi_timeseries|field_indicators|v_latest_ndvi|v_field_summary)\b",
    re.IGNORECASE,
)
_SCANNED = ("services", "bots", "agents")


def _legacy_hits(text: str) -> list[tuple[int, str]]:
    """Matches over the whole text (``\\s+`` spans newlines), so ``FROM`` and the table name on
    separate lines of a triple-quoted SQL string are still caught; returns (line, match)."""
    return [
        (text.count("\n", 0, m.start()) + 1, " ".join(m.group(0).split()))
        for m in _LEGACY_READ.finditer(text)
    ]


def _legacy_readers(paths) -> list[str]:
    hits = []
    for path in paths:
        text = path.read_text(encoding="utf-8", errors="replace")
        for n, match in _legacy_hits(text):
            hits.append(f"{path.relative_to(ROOT)}:{n}: {match}")
    return hits


def _service_sources() -> list[Path]:
    out = []
    for top in _SCANNED:
        base = ROOT / top
        if not base.is_dir():
            continue
        for ext in ("*.py", "*.ts", "*.js", "*.go", "*.sql"):
            for path in base.rglob(ext):
                parts = set(path.relative_to(ROOT).parts)
                if parts & {"node_modules", "tests", "__pycache__"} or path.name.startswith(
                    "test_"
                ):
                    continue
                out.append(path)
    return out


def test_no_service_reads_the_seed_only_ndvi_tables():
    hits = _legacy_readers(_service_sources())
    assert not hits, (
        "ndvi_timeseries / field_indicators have no live writer (init_v8 RANDOM() seed); read "
        "NDVI through api.raster_service_client.latest_index_points instead:\n" + "\n".join(hits)
    )


def test_the_grep_would_catch_the_pre_fix_readers(tmp_path):
    """Negative control: the three pre-fix queries are caught by the same pattern."""
    probe = tmp_path / "probe.py"
    probe.write_text(
        '"SELECT MAX(acquisition_date) FROM ndvi_timeseries WHERE field_id = $1"\n'
        '"  FROM ndvi_timeseries), "\n'
        "                FROM field_indicators\n",
        encoding="utf-8",
    )
    hits = _legacy_hits(probe.read_text(encoding="utf-8"))
    assert len(hits) == 3, f"the grep missed a pre-fix reader: {hits}"


def test_the_grep_spans_a_line_break_between_from_and_the_table():
    sql = '"""\n    SELECT ndvi_mean FROM\n        ndvi_timeseries\n    WHERE field_id = $1"""\n'
    hits = _legacy_hits(sql)
    assert hits == [(2, "FROM ndvi_timeseries")], f"a multi-line reader slipped the grep: {hits}"


def _catalogue_and_series(dates, points, *, calls=None, fail=None):
    async def fake_get_json(path, *, tenant_id=None, params=None, timeout_s=15.0):
        if calls is not None:
            calls.append((path, dict(params or {}), tenant_id))
        if fail and fail in path:
            raise RuntimeError("raster-service down")
        if path.endswith("/available-dates"):
            return {"field_id": "F-1", "dates": dates}
        return {"available": bool(points), "points": points}

    return fake_get_json


async def test_latest_points_reads_only_the_newest_processed_dates(monkeypatch):
    calls: list = []
    dates = [
        {"date": "2026-10-01", "has_cog": True},
        {"date": "2026-10-20", "has_cog": True},
        {"date": "2026-11-10", "has_cog": False},  # provider date, no COG yet
        {"date": "2026-11-01", "has_cog": True},
        {"date": "2026-09-01", "has_cog": True},
        {"date": "2026-08-01", "has_cog": True},
        {"date": "not-a-date", "has_cog": True},
    ]
    points = [
        {"datetime": "2026-10-20", "mean": 0.61, "scene_id": "S2"},
        {"datetime": "2026-11-01", "mean": float("nan")},  # no real mean: dropped
        {"datetime": "2026-10-01", "mean": 0.70},
        {"datetime": "2026-09-01", "mean": 0.72},
    ]
    monkeypatch.setattr(rsc, "raster_get_json", _catalogue_and_series(dates, points, calls=calls))
    got = await rsc.latest_index_points("F-1", tenant_id="t-1", index="ndvi", count=2)
    assert [p["datetime"] for p in got] == ["2026-10-20", "2026-10-01"], f"wrong points: {got}"
    assert got[0]["scene_id"] == "S2", "raster point identity must pass through"
    series = [c for c in calls if c[0].endswith("/timeseries")]
    assert series and series[0][1]["dates"] == "2026-11-01,2026-10-20,2026-10-01,2026-09-01", (
        f"raster must compute only the newest processed dates (count + 2): {series}"
    )
    assert all(c[2] == "t-1" for c in calls), f"every raster call carries the tenant: {calls}"


async def test_latest_points_no_processed_date_is_no_observation(monkeypatch):
    monkeypatch.setattr(rsc, "raster_get_json", _catalogue_and_series([{"date": "2026-11-01"}], []))
    got = await rsc.latest_index_points("F-1", tenant_id="t", index="ndvi")
    assert got == [], f"no COG date must read as no observation, not {got!r}"


@pytest.mark.parametrize("fail", ["/available-dates", "/timeseries"])
async def test_latest_points_outage_is_none_not_empty(monkeypatch, fail):
    dates = [{"date": "2026-11-01", "has_cog": True}]
    monkeypatch.setattr(
        rsc,
        "raster_get_json",
        _catalogue_and_series(dates, [{"datetime": "2026-11-01", "mean": 0.5}], fail=fail),
    )
    got = await rsc.latest_index_points("F-1", tenant_id="t", index="ndvi")
    assert got is None, f"a raster outage at {fail} must read as unavailable, not {got!r}"


async def test_latest_points_refuses_another_fields_catalogue(monkeypatch):
    async def fake(path, **kw):
        return {"field_id": "OTHER", "dates": [{"date": "2026-11-01", "has_cog": True}]}

    monkeypatch.setattr(rsc, "raster_get_json", fake)
    assert await rsc.latest_index_points("F-1", tenant_id="t") is None, (
        "a catalogue for another field must not become this field's evidence"
    )


# ── routers (raster stage only; the read is stubbed at latest_index_points) ──────────────


def _routers():
    pytest.importorskip("fastapi")
    import api.main  # noqa: F401 — initialise api.main before the routers
    from api.routers import decision_confidence, field_twin, nl_gis

    return decision_confidence, field_twin, nl_gis


def test_decision_confidence_satellite_freshness_from_raster():
    dc, _, _ = _routers()
    today = date(2026, 11, 16)
    value, detail = dc._satellite_component([{"datetime": "2026-11-12", "mean": 0.6}], today)
    assert value == 1.0 and "4" in detail, f"4-day-old NDVI must score fresh: {value}, {detail}"
    value, detail = dc._satellite_component([], today)
    assert value is None and "needs_data" in detail, f"no observation is needs_data: {detail}"
    value, detail = dc._satellite_component(None, today)
    assert value is None and "raster-service" in detail, (
        f"an outage must be named as an outage, not as a field without NDVI: {detail}"
    )


def test_decision_confidence_no_longer_queries_ndvi_in_the_db_block():
    dc, _, _ = _routers()
    import inspect

    src = inspect.getsource(dc.decision_confidence_endpoint)
    assert "latest_index_points(" in src, "decision confidence must read NDVI from raster"
    assert "ndvi_timeseries" not in src, "decision confidence still names the seed table"


async def test_field_twin_rows_come_from_raster_per_index(monkeypatch):
    _, ft, _ = _routers()
    seen: list = []

    async def raster(field_id, *, tenant_id, index="ndvi", count=1, timeout_s=20.0):
        seen.append((field_id, tenant_id, index, count))
        if index == "savi":
            return None  # raster could not answer for this index
        if index == "ndmi":
            return []  # no observation
        return [{"datetime": "2026-11-0" + ("1" if index == "ndvi" else "9"), "mean": 0.5}]

    monkeypatch.setattr(ft, "latest_index_points", raster)
    rows, unavailable = await ft._latest_indicator_rows("F-1", "t-1")
    assert {r["indicator_id"]: r["recorded_at"] for r in rows} == {
        "ndvi": "2026-11-01",
        "evi": "2026-11-09",
    }, f"each index keeps its own observation date: {rows}"
    assert unavailable == ["savi"], f"only the failed index is reported unavailable: {unavailable}"
    assert sorted(i for _, _, i, _ in seen) == sorted(ft._TWIN_INDICATORS), f"indices read: {seen}"
    assert all(f == "F-1" and t == "t-1" for f, t, _, _ in seen), f"tenant/field lost: {seen}"


async def test_nl_gis_ndvi_drop_compares_the_two_newest_raster_readings(monkeypatch):
    _, _, nl = _routers()
    series = {
        "A": [{"datetime": "2026-11-10", "mean": 0.40}, {"datetime": "2026-10-31", "mean": 0.60}],
        "B": [{"datetime": "2026-11-10", "mean": 0.58}, {"datetime": "2026-10-31", "mean": 0.60}],
        "C": [{"datetime": "2026-11-10", "mean": 0.50}],  # one reading: not comparable
        "D": None,  # raster could not answer
    }

    async def raster(field_id, *, tenant_id, index="ndvi", count=1, timeout_s=20.0):
        assert tenant_id == "t-1" and index == "ndvi" and count == 2, (tenant_id, index, count)
        return series[field_id]

    monkeypatch.setattr(nl, "latest_index_points", raster)
    fields = [{"field_id": k, "name": k, "crop": "قمح", "gov": "x"} for k in series]
    out = await nl._raster_ndvi_drop({"fields": fields}, {"threshold_pct": 15}, "t-1")
    assert [it["field_id"] for it in out["items"]] == ["A"], f"only A dropped ≥15%: {out}"
    assert out["items"][0]["drop_pct"] == pytest.approx(33.3), f"drop: {out['items'][0]}"
    assert out["items"][0]["latest_date"] == "2026-11-10", "the observation date is reported"
    assert out["coverage"]["raster_unavailable"] == 1, f"D's outage is counted: {out}"
    assert out["api_called"].startswith("raster-service"), "the audit names the real source"


async def test_nl_gis_ndvi_drop_total_raster_outage_raises(monkeypatch):
    _, _, nl = _routers()

    async def raster(*a, **kw):
        return None

    monkeypatch.setattr(nl, "latest_index_points", raster)
    with pytest.raises(RuntimeError, match="unavailable"):
        await nl._raster_ndvi_drop(
            {"fields": [{"field_id": "A"}, {"field_id": "B"}]}, {"threshold_pct": 1}, "t"
        )


async def test_nl_gis_ndvi_drop_caps_the_raster_scan(monkeypatch):
    _, _, nl = _routers()
    calls: list = []

    async def raster(field_id, **kw):
        calls.append(field_id)
        return []

    monkeypatch.setattr(nl, "latest_index_points", raster)
    fields = [{"field_id": f"F{i}"} for i in range(nl._NDVI_SCAN_FIELDS + 1)]
    out = await nl._raster_ndvi_drop({"fields": fields}, {"threshold_pct": 1}, "t")
    assert len(calls) == nl._NDVI_SCAN_FIELDS, f"scan must stop at the cap: {len(calls)}"
    assert out["coverage"]["fields_truncated"] is True, "a truncated scan is reported as such"
    assert out["coverage"]["complete"] is False, "a truncated scan is not a complete scan"


async def test_nl_gis_partial_outage_is_partial_not_an_honest_empty(monkeypatch):
    """Review W1-21 MEDIUM: 2 of 3 fields unmeasured must not read as 'no fields match'."""
    _, _, nl = _routers()
    series = {"A": None, "B": None, "C": []}

    async def raster(field_id, **kw):
        return series[field_id]

    monkeypatch.setattr(nl, "latest_index_points", raster)
    fields = [{"field_id": k} for k in series]
    out = await nl._raster_ndvi_drop({"fields": fields}, {"threshold_pct": 15}, "t")
    assert out["items"] == [], f"no measured field dropped: {out}"
    assert out["coverage"]["complete"] is False, f"a partial outage is incomplete: {out}"
    status = nl._status_after_raster(out)
    assert status == "partial", f"partial coverage must not be status ok: {status}"
    note = nl._response_note_ar(status, 0, out["coverage"])
    assert "ناقصة" in note and "2 من 3" in note, f"the note must name the gap: {note}"
    assert "لا حقول تطابق" not in note, f"partial must never say 'no fields match': {note}"
    assert nl._audit_status(status, 0) == "needs_data", "an unmeasured empty is not audited ok"
    assert nl._audit_status(status, 1) == "ok", "partial with results is audited ok (v85 CHECK)"


async def test_nl_gis_every_skipped_field_is_counted_with_its_reason(monkeypatch):
    """Review W1-21: a field with no processed date, one reading, or a non-positive previous
    mean is unmeasured — it is counted by reason and the scan is not complete."""
    _, _, nl = _routers()
    series = {
        "A": [{"datetime": "2026-11-10", "mean": 0.58}, {"datetime": "2026-10-31", "mean": 0.60}],
        "B": [],  # no processed NDVI date
        "C": [{"datetime": "2026-11-10", "mean": 0.50}],  # a single observation
        "D": [{"datetime": "2026-11-10", "mean": 0.20}, {"datetime": "2026-10-31", "mean": 0.0}],
    }

    async def raster(field_id, **kw):
        return series[field_id]

    monkeypatch.setattr(nl, "latest_index_points", raster)
    fields = [{"field_id": k} for k in series]
    out = await nl._raster_ndvi_drop({"fields": fields}, {"threshold_pct": 15}, "t")
    cov = out["coverage"]
    assert out["items"] == [], f"only A was measured and it did not drop 15%: {out}"
    assert cov["raster_unavailable"] == 0, f"no outage here: {cov}"
    assert cov["insufficient_history"] == 2, f"B (no date) and C (one reading) counted: {cov}"
    assert cov["not_comparable"] == 1, f"D (previous mean 0) counted: {cov}"
    assert cov["complete"] is False, f"three unmeasured fields are not a complete scan: {cov}"
    status = nl._status_after_raster(out)
    assert status == "partial", f"unmeasured fields must not read as an honest empty: {status}"
    note = nl._response_note_ar(status, 0, cov)
    assert "2 من 4" in note and "1 من 4" in note, f"the note names each reason: {note}"
    assert "لا حقول تطابق" not in note, f"partial must never say 'no fields match': {note}"


async def test_nl_gis_all_fields_measured_is_complete(monkeypatch):
    _, _, nl = _routers()

    async def raster(field_id, **kw):
        return [{"datetime": "2026-11-10", "mean": 0.58}, {"datetime": "2026-10-31", "mean": 0.6}]

    monkeypatch.setattr(nl, "latest_index_points", raster)
    out = await nl._raster_ndvi_drop(
        {"fields": [{"field_id": "A"}, {"field_id": "B"}]}, {"threshold_pct": 15}, "t"
    )
    assert out["coverage"]["complete"] is True, f"every field measured: {out['coverage']}"
    assert nl._status_after_raster(out) == "ok", "a fully measured empty scan is an honest empty"


def test_nl_gis_truncated_scan_note_names_the_cap():
    _, _, nl = _routers()
    cov = {
        "fields_scanned": nl._NDVI_SCAN_FIELDS,
        "fields_truncated": True,
        "raster_unavailable": 0,
        "complete": False,
    }
    note = nl._response_note_ar("partial", 0, cov)
    assert str(nl._NDVI_SCAN_FIELDS) in note, f"the note must say the scan stopped: {note}"
    full = nl._response_note_ar(nl._status_after_raster({"coverage": {"complete": True}}), 0, {})
    assert "لا حقول تطابق" in full, f"a complete empty scan is an honest empty: {full}"


async def test_nl_gis_scan_has_an_overall_deadline(monkeypatch):
    """Review W1-21 LOW: a hanging raster ends at the scan deadline, unread fields unavailable."""
    import asyncio

    _, _, nl = _routers()

    async def raster(field_id, **kw):
        if field_id == "A":
            return [
                {"datetime": "2026-11-10", "mean": 0.4},
                {"datetime": "2026-10-31", "mean": 0.6},
            ]
        await asyncio.sleep(30)  # raster accepted the connection and never answered
        return []

    monkeypatch.setattr(nl, "latest_index_points", raster)
    monkeypatch.setattr(nl, "_NDVI_SCAN_DEADLINE_S", 0.2)
    fields = [{"field_id": k} for k in ("A", "B", "C")]
    out = await asyncio.wait_for(
        nl._raster_ndvi_drop({"fields": fields}, {"threshold_pct": 15}, "t"), timeout=5
    )
    assert [it["field_id"] for it in out["items"]] == ["A"], f"A was measured in time: {out}"
    assert out["coverage"]["raster_unavailable"] == 2, f"timed-out fields are unavailable: {out}"
    assert nl._status_after_raster(out) == "partial", "a deadline cut is a partial result"


async def test_latest_points_whole_read_is_bounded(monkeypatch):
    import asyncio

    async def hang(path, **kw):
        await asyncio.sleep(30)

    monkeypatch.setattr(rsc, "raster_get_json", hang)
    got = await asyncio.wait_for(
        rsc.latest_index_points("F-1", tenant_id="t", timeout_s=0.1), timeout=5
    )
    assert got is None, f"running out of time is an outage, not {got!r}"

"""W1-03 (owner decision 2026-11-16): soil_lab_results is the single canonical soil-lab store.

Unit half (the live half is ``test_w1_03_soil_lab_canonical_live_pg.py``):

- the lab_store read helpers: an approved v156 value wins and cites its ``result_id``; the
  legacy ``soil_lab_tests`` fallback is labelled ``legacy_soil_lab_tests``; a missing or
  unusable value is unavailable (None), never zero; JSON text is read like an object;
- the migrated readers keep their meaning and say which source they used (root zone EC,
  season-workspace readiness, sustainability signals);
- the legacy write routes are frozen (410 Gone pointing at /api/v1/lab/*);
- no platform module but ``api/lab_store.py`` reads or writes ``soil_lab_tests``.

Store functions are stubbed at function level; no connection stand-in is used.
"""

from __future__ import annotations

import ast
import asyncio
import json
import re
import sys
from datetime import date
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
PLATFORM = ROOT / "services" / "sahool-platform"
if str(PLATFORM) not in sys.path:
    sys.path.insert(0, str(PLATFORM))


def _store():
    import api.lab_store as store

    return store


def _candidate(ref: str, result, sampled_on=date(2026, 11, 1), age=15.0) -> dict:
    return {"sampled_on": sampled_on, "result": result, "evidence_ref": ref, "age_days": age}


def _latest(monkeypatch, rows, analyte="ec_dsm", **kwargs):
    store = _store()

    async def candidates(conn, *, field_id, analyte, tenant_id=None, limit=20):
        return rows

    monkeypatch.setattr(store, "soil_analyte_candidates", candidates)
    return asyncio.run(
        store.latest_approved_soil_analyte(None, field_id="f1", analyte=analyte, **kwargs)
    )


# ── the helpers ────────────────────────────────────────────────────────────────────────


def test_approved_v156_result_wins_and_cites_its_result_id(monkeypatch):
    rows = [
        _candidate("soil_lab_results:rid-1", {"ec_dsm": 6.2}),
        _candidate("soil_lab_tests:soil_old", {"ec": 1.0}),
    ]
    out = _latest(monkeypatch, rows)
    assert out["source"] == "soil_lab_results", f"canonical store must win: {out}"
    assert out["value"] == 6.2, out
    assert out["result_id"] == "rid-1" and out["test_id"] is None, out
    assert out["evidence_ref"] == "soil_lab_results:rid-1", out


def test_legacy_fallback_is_labelled(monkeypatch):
    out = _latest(monkeypatch, [_candidate("soil_lab_tests:soil_abc", {"ece_ds_m": 4.4})])
    assert out["source"] == "legacy_soil_lab_tests", f"fallback must be labelled: {out}"
    assert out["value"] == 4.4 and out["test_id"] == "soil_abc", out
    assert out["result_id"] is None, "a legacy row has no v156 result_id"


def test_missing_lab_value_is_unavailable_not_zero(monkeypatch):
    assert _latest(monkeypatch, []) is None, "no lab evidence must be None, never 0"
    rows = [
        _candidate("soil_lab_tests:soil_a", {"ec": True}),  # a bool is not a measurement
        _candidate("soil_lab_tests:soil_b", {"ec": "high"}),
    ]
    assert _latest(monkeypatch, rows) is None, "unusable values must not become a number"


def test_unusable_newest_row_falls_through_to_the_next_eligible(monkeypatch):
    rows = [
        _candidate("soil_lab_tests:soil_new", {"ph": 7.1}),  # matched a key, no usable EC
        _candidate("soil_lab_results:rid-9", {"ec_dsm": 3.3}),
    ]
    out = _latest(monkeypatch, rows)
    assert (out["source"], out["value"]) == ("soil_lab_results", 3.3), out


def test_json_text_is_read_like_an_object(monkeypatch):
    """data-10: asyncpg returns JSONB as text without a codec."""
    rows = [_candidate("soil_lab_results:rid-2", json.dumps({"ec_dsm": 2.5}))]
    assert _latest(monkeypatch, rows)["value"] == 2.5, "JSONB text must be parsed"


def test_accept_predicate_narrows_usable_values(monkeypatch):
    rows = [
        _candidate("soil_lab_results:rid-a", {"texture": "brownish"}),
        _candidate("soil_lab_tests:soil_b", {"soil_texture": "clay"}),
    ]
    out = _latest(monkeypatch, rows, analyte="texture", accept=lambda v: v == "clay")
    assert (out["source"], out["value"]) == ("legacy_soil_lab_tests", "clay"), out


def test_legacy_aliases_cover_every_migrated_reader():
    store = _store()
    for key in ("ec", "ec_ds_m", "ece", "ece_ds_m", "salinity_ec", "ec_dsm", "soil_ec"):
        assert store.legacy_analyte_value({key: 2.0}, "ec_dsm") == 2.0, key
    for key in ("texture", "soil_texture", "textural_class", "texture_class"):
        assert store.legacy_analyte_value({key: " Loam "}, "texture") == "Loam", key
    assert store.legacy_analyte_value({"ph": 0}, "ph") == 0.0, "zero is a measurement"
    assert store.legacy_analyte_value(None, "ph") is None, "no result is no value"


# ── migrated readers ───────────────────────────────────────────────────────────────────


def _season_workspace():
    import api.main  # noqa: F401 — resolve the application's router import cycle
    import api.routers.season_workspace as sw

    return sw


def test_season_readiness_accepts_an_approved_v156_analysis():
    sw = _season_workspace()
    soil = sw._accepted_soil(
        {
            "source": "soil_lab_results",
            "values": {"ec_dsm": 0.0, "ph": 7.2, "nitrogen_mg_kg": 20.0},
            "legacy_result": None,
        }
    )
    assert soil["ec_ds_m"] == 0.0 and soil["ph"] == 7.2 and soil["n_ppm"] == 20.0, soil
    assert sw._accepted_soil(None) == {}, "no analysis must be empty, never invented"


def test_season_readiness_keeps_the_published_rule_for_legacy():
    sw = _season_workspace()
    legacy = {"source": "legacy_soil_lab_tests", "legacy_result": {"ec_ds_m": 2.1}}
    assert sw._accepted_soil({**legacy, "legacy_status": "published"}) == {"ec_ds_m": 2.1}, (
        "a published legacy row stays accepted"
    )
    assert sw._accepted_soil({**legacy, "legacy_status": "approved"}) == {}, (
        "an approved-not-published legacy row was never accepted soil"
    )


def test_sustainability_signals_read_v156_names_without_inventing_units():
    import api.main  # noqa: F401
    from api.routers.reports import _soil_lab_signals

    out = _soil_lab_signals(
        {"ph": 7.0, "organic_matter_pct": 1.5, "phosphorus_mg_kg": 9.0, "nitrogen_mg_kg": 30.0}
    )
    assert out["ph"] == 7.0 and out["organic_matter"] == 1.5 and out["p_ppm"] == 9.0, out
    assert out["n_kg_ha"] is None, "N in mg/kg is not kg/ha: absent, not converted"


def test_root_zone_profile_records_the_ec_source():
    from api.canonical_root_zone_profile import build_canonical_root_zone_profile

    soil = {
        "profile_id": "shp-1",
        "executable": True,
        "source_soil_profile_hash": "h",
        "generated_at": "2026-11-15T00:00:00+00:00",
        "layers": [
            {
                "depth_from_cm": 0,
                "depth_to_cm": 100,
                "field_capacity": {"value": 0.3, "origin": "measured", "confidence": 0.9},
                "wilting_point": {"value": 0.12, "origin": "measured", "confidence": 0.9},
            }
        ],
    }
    policy = {
        "policy_id": "p",
        "initial_depth_m": 0.2,
        "maximum_depth_m": 1.0,
        "policy_version": "v1",
        "evidence_ids": ["e"],
    }
    kwargs = dict(
        tenant_id="t",
        field_id="f",
        season_id="s",
        crop="maize",
        phenology_progress=0.5,
        raw_fraction=0.5,
        root_policy=policy,
        soil_profile=soil,
    )
    evidence = {"source": "soil_lab_results", "evidence_ref": "soil_lab_results:r1"}
    out = build_canonical_root_zone_profile(**kwargs, soil_ec_ds_m=3.0, soil_ec_evidence=evidence)
    assert out.soil_ec_ds_m == 3.0, out
    assert out.evidence["soil_ec"] == evidence, "the EC source must be part of the evidence"
    bare = build_canonical_root_zone_profile(**kwargs)
    assert "soil_ec" not in bare.evidence and bare.soil_ec_ds_m is None, (
        "no lab EC: no evidence entry and no value"
    )


# ── frozen legacy writes ───────────────────────────────────────────────────────────────


@pytest.mark.parametrize("name", ["create_soil_lab_test", "update_soil_lab_test"])
def test_legacy_soil_lab_writes_answer_410_with_a_pointer(name):
    import api.main  # noqa: F401
    import api.routers.fields as fields
    from fastapi import HTTPException

    handler = getattr(fields, name)
    args = ("f1", "t1", None, None) if name == "update_soil_lab_test" else ("f1", None, None)
    with pytest.raises(HTTPException) as caught:
        asyncio.run(handler(*args))
    assert caught.value.status_code == 410, f"{name} must answer 410 Gone"
    detail = caught.value.detail
    assert detail["code"] == "legacy_soil_lab_tests_frozen", detail
    assert any(u.startswith("POST /api/v1/lab/") for u in detail["use"]), detail


_TABLE_SQL = re.compile(r"\b(?:FROM|JOIN|INTO|UPDATE)\s+soil_lab_tests\b", re.I)


def test_only_lab_store_touches_the_legacy_table():
    """One canonical reader: SQL naming soil_lab_tests lives only in api/lab_store.py."""
    offenders = []
    for path in sorted((PLATFORM / "api").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if _TABLE_SQL.search(node.value):
                    offenders.append(f"{path.relative_to(PLATFORM)}:{node.lineno}")
    rel = {o.split(":")[0] for o in offenders}
    assert rel == {"api/lab_store.py"}, f"soil_lab_tests SQL outside lab_store: {offenders}"
    writes = [
        o
        for o in offenders
        if re.search(
            r"\b(?:INSERT\s+INTO|UPDATE|DELETE\s+FROM)\s+soil_lab_tests\b",
            (PLATFORM / o.split(":")[0]).read_text(encoding="utf-8"),
            re.I,
        )
    ]
    assert not writes, f"the frozen legacy table must not be written: {writes}"

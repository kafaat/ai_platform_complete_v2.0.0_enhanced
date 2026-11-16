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


def _candidate(
    ref: str, result, sampled_on=date(2026, 11, 1), age=15.0, method="saturated_paste"
) -> dict:
    legacy = ref.startswith("soil_lab_tests:")
    return {
        "sampled_on": sampled_on,
        "sampled_on_source": "sampled_on",
        "result": result,
        "evidence_ref": ref,
        "method_code": None if legacy else method,
        "age_days": age,
    }


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


@pytest.mark.parametrize(
    "method", ["soil_water_1_1", "soil_water_1_2_5", "soil_water_1_5", "unspecified", None, "SOP-7"]
)
def test_ec_not_on_saturated_paste_is_not_an_ece(monkeypatch, method):
    """An EC 1:5 of 2.0 is roughly an ECe of 12+: it must not come back as ECe, and an older
    ECe (here legacy 1.0) must not stand in for the newer reading that contradicts it."""
    rows = [
        _candidate("soil_lab_results:rid-15", {"ec_dsm": 2.0}, method=method),
        _candidate("soil_lab_results:rid-old", {"ec_dsm": 1.0}, sampled_on=date(2026, 1, 1)),
        _candidate("soil_lab_tests:soil_old", {"ec": 1.0}, sampled_on=date(2025, 1, 1)),
    ]
    assert _latest(monkeypatch, rows) is None, f"{method} EC must leave ECe unavailable"


def test_saturated_paste_ec_is_an_ece_and_other_analytes_ignore_the_method(monkeypatch):
    rows = [_candidate("soil_lab_results:rid-sp", {"ec_dsm": 2.0})]
    assert _latest(monkeypatch, rows)["value"] == 2.0, "a saturated-paste EC is an ECe"
    rows = [_candidate("soil_lab_results:rid-ph", {"ph": 7.7}, method="SOP-7")]
    assert _latest(monkeypatch, rows, analyte="ph")["value"] == 7.7, "pH has no ECe rule"


def test_reading_says_how_its_collection_date_was_known(monkeypatch):
    row = _candidate("soil_lab_results:rid-n", {"ph": 7.0})
    row["sampled_on_source"] = "sample_created_at"
    out = _latest(monkeypatch, [row], analyte="ph")
    assert out["sampled_on_source"] == "sample_created_at", f"date origin must be labelled: {out}"


def test_candidate_sql_dates_undated_samples_and_carries_the_ec_method():
    """Both readers keep a sample without sampled_on (dated by registration, labelled) and
    the v156 EC method; the ECe rule is applied on the method in both readers."""
    import inspect

    store = _store()
    for fn in (store.soil_analyte_candidates, store.latest_approved_soil_analysis):
        src = inspect.getsource(fn)
        assert "COALESCE(s.sampled_on, s.created_at::date)" in src, fn.__name__
        assert "'sample_created_at'" in src and "'legacy_created_at'" in src, fn.__name__
        assert "method_code" in src, f"{fn.__name__} must read the EC method"
    analysis = inspect.getsource(store.latest_approved_soil_analysis)
    assert "ECE_EXTRACTION_METHOD" in analysis and "ec_other_extract" in analysis, (
        "the analysis must keep a non-ECe EC out of values and label it"
    )
    assert store.ECE_EXTRACTION_METHOD == "saturated_paste", "only the saturated paste is ECe"


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


def _reading(source: str, value) -> dict:
    return {"source": source, "value": value}


def test_season_readiness_accepts_approved_v156_ph_and_ece():
    sw = _season_workspace()
    soil = sw._accepted_soil(
        [], _reading("soil_lab_results", 7.2), _reading("soil_lab_results", 0.0)
    )
    assert soil == {"ph": 7.2, "ec_ds_m": 0.0}, f"zero ECe is a measurement: {soil}"
    assert sw._accepted_soil([]) == {}, "no analysis must be empty, never invented"


def test_season_readiness_keeps_the_published_rule_for_legacy():
    """Unchanged legacy rule: the newest *published* row of the listed history — an approved
    newer row does not hide an older published one, and is never itself accepted."""
    sw = _season_workspace()
    history = [
        {"status": "approved", "result": {"ec_ds_m": 9.9}},
        {"status": "published", "result": {"ec_ds_m": 3.1}},
    ]
    assert sw._accepted_soil(history) == {"ec_ds_m": 3.1}, "older published row stays accepted"
    assert sw._accepted_soil(history[:1]) == {}, "approved-not-published was never accepted"
    legacy_reading = _reading("legacy_soil_lab_tests", 9.9)
    assert sw._accepted_soil(history, None, legacy_reading) == {"ec_ds_m": 3.1}, (
        "a legacy-sourced reading must not bypass the published rule"
    )


def test_season_readiness_reads_ece_per_analyte():
    """A newer texture-only v156 sample must not hide an older sample's ECe: readiness takes
    each analyte's newest approved value (latest_approved_soil_analyte), not one sample."""
    sw = _season_workspace()
    history = [{"status": "published", "result": {"ec_ds_m": 1.0, "ph": 7.0}}]
    soil = sw._accepted_soil(history, None, _reading("soil_lab_results", 4.2))
    assert soil == {"ec_ds_m": 4.2, "ph": 7.0}, f"v156 ECe overrides per analyte: {soil}"
    import inspect

    src = inspect.getsource(sw.season_workspace)
    assert 'analyte="ec_dsm"' in src and 'analyte="ph"' in src, (
        "season workspace must read pH and ECe per analyte"
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

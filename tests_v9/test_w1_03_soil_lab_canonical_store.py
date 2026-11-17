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
    assert "soil_ece_evidence(" in src and 'analyte="ph"' in src, (
        "season workspace must read pH and ECe per analyte"
    )


def test_season_readiness_drops_legacy_ec_under_a_newer_non_ece_v156_ec():
    """W1-03 review LOW 2: a v156 value overrides the legacy row per analyte. A newest v156 EC
    that is not an ECe leaves the ECe unknown, so the legacy row's older EC must not count."""
    sw = _season_workspace()
    history = [{"status": "published", "result": {"ec_ds_m": 1.0, "ph": 7.0}}]
    other = {"source": "soil_lab_results", "value": 2.0, "extraction_method": "soil_water_1_5"}
    assert sw._accepted_soil(history, None, None, other) == {"ph": 7.0}, (
        "an older legacy ECe must not stand in for the newer non-ECe v156 reading"
    )
    assert sw._accepted_soil(history, None, _reading("soil_lab_results", 4.2), None) == {
        "ec_ds_m": 4.2,
        "ph": 7.0,
    }


def test_season_readiness_reads_v156_without_the_legacy_candidates():
    """W1-03 review LOW 2: readiness never accepts an approved-but-unpublished legacy row, so
    such a row (newest candidate) must not hide an older approved v156 value."""
    import inspect

    sw = _season_workspace()
    src = inspect.getsource(sw.season_workspace)
    assert src.count("include_legacy=False") == 1, "pH must skip legacy candidates"
    assert src.count("legacy_published_only=True") == 1, (
        "ECe must skip the unpublished legacy candidates (and only those, #1507 review LOW)"
    )


def _ec_candidates(newest_legacy_status: str | None) -> list[dict]:
    """#1507 review LOW: an older v156 EC 1:5 and a newer published legacy ECe (3.0); with
    ``newest_legacy_status`` an even newer legacy ECe (9.9) of that status on top."""
    rows = [
        {
            **_candidate("soil_lab_tests:soil_pub", {"ec": 3.0}, sampled_on=date(2026, 11, 10)),
            "legacy_status": "published",
        },
        {
            **_candidate(
                "soil_lab_results:rid-15",
                {"ec_dsm": 0.4},
                sampled_on=date(2026, 11, 1),
                method="soil_water_1_5",
            ),
            "legacy_status": None,
        },
    ]
    if newest_legacy_status:
        newest = _candidate("soil_lab_tests:soil_new", {"ec": 9.9}, sampled_on=date(2026, 11, 12))
        rows.insert(0, {**newest, "legacy_status": newest_legacy_status})
    return rows


def test_published_only_keeps_a_published_legacy_ece_newer_than_a_v156_extract():
    store = _store()
    rows = _ec_candidates("approved")
    out = store.ece_evidence_from_candidates(rows, legacy_published_only=True)
    assert out["ece"] is not None, f"the published legacy ECe is the newest accepted EC: {out}"
    assert (out["ece"]["test_id"], out["ece"]["value"]) == ("soil_pub", 3.0), out
    assert out["ece"]["legacy_status"] == "published", out
    assert out["newer_other_extract"] is None, "the older 1:5 is not newer than the ECe"
    # Negative control: the earlier reading (include_legacy=False) loses the published row
    # and lets the older 1:5 make the ECe unknown.
    old = store.ece_evidence_from_candidates(rows, include_legacy=False)
    assert old["ece"] is None and old["newer_other_extract"]["result_id"] == "rid-15", old
    # field_state's rule (all approved/published legacy rows) still takes the newest one.
    assert store.ece_evidence_from_candidates(rows)["ece"]["value"] == 9.9, "default unchanged"


def test_published_only_skips_a_legacy_row_without_a_status():
    """Fail closed: a legacy candidate that does not say it is published is not accepted."""
    store = _store()
    rows = [{k: v for k, v in r.items() if k != "legacy_status"} for r in _ec_candidates(None)]
    out = store.ece_evidence_from_candidates(rows, legacy_published_only=True)
    assert out["ece"] is None, f"an unlabelled legacy row must not be read as published: {out}"
    assert out["newer_other_extract"]["result_id"] == "rid-15", out


@pytest.mark.parametrize("newest_legacy_status", [None, "approved"])
def test_season_readiness_and_field_state_agree_on_a_published_legacy_ece(
    monkeypatch, newest_legacy_status
):
    """#1507 review LOW: a published legacy ECe newer than an older v156 EC 1:5 is the ECe of
    field_state; readiness must accept it too instead of reporting soil EC missing. Run the
    reader exactly as the season workspace calls it (the source assertion above pins that)."""
    store = _store()
    sw = _season_workspace()
    rows = _ec_candidates(newest_legacy_status)

    async def candidates(conn, *, field_id, analyte, tenant_id=None, limit=20):
        return rows

    monkeypatch.setattr(store, "soil_analyte_candidates", candidates)
    evidence = asyncio.run(store.soil_ece_evidence(None, field_id="f1", legacy_published_only=True))
    history = [
        {"status": newest_legacy_status, "result": {"ec": 9.9}},
        {"status": "published", "result": {"ec": 3.0, "ph": 7.0}},
    ][0 if newest_legacy_status else 1 :]
    soil = sw._accepted_soil(history, None, evidence["ece"], evidence["newer_other_extract"])
    assert soil.get("ec_ds_m") == 3.0, f"readiness must accept the published legacy ECe: {soil}"
    checks = {c["key"]: c["ok"] for c in sw._readiness({}, None, history, None, soil)["checks"]}
    assert checks["soil_ec"] is True, f"soil EC must not be reported missing: {checks}"
    if newest_legacy_status is None:
        field_state = asyncio.run(store.soil_ece_evidence(None, field_id="f1"))
        assert field_state["ece"]["value"] == soil["ec_ds_m"], (
            f"readiness and field_state must read the same ECe: {field_state} vs {soil}"
        )


def test_season_readiness_ignores_an_unpublished_legacy_reading():
    """A legacy reading counts only when its row is published."""
    sw = _season_workspace()
    approved = {"source": "legacy_soil_lab_tests", "value": 9.9, "legacy_status": "approved"}
    assert sw._accepted_soil([], None, approved) == {}, "approved-not-published never counts"
    published = {**approved, "legacy_status": "published", "value": 3.0}
    assert sw._accepted_soil([], None, published) == {"ec_ds_m": 3.0}, "published counts"


def test_include_legacy_false_skips_a_newer_legacy_candidate(monkeypatch):
    rows = [
        _candidate("soil_lab_tests:soil_new", {"ph": 6.1}, sampled_on=date(2026, 11, 10)),
        _candidate("soil_lab_results:rid-ph", {"ph": 7.7}),
    ]
    assert _latest(monkeypatch, rows, analyte="ph")["source"] == "legacy_soil_lab_tests"
    out = _latest(monkeypatch, rows, analyte="ph", include_legacy=False)
    assert (out["source"], out["value"]) == ("soil_lab_results", 7.7), out
    ec_rows = [
        _candidate("soil_lab_tests:soil_new", {"ec": 1.0}, sampled_on=date(2026, 11, 10)),
        _candidate("soil_lab_results:rid-ece", {"ec_dsm": 9.0}),
    ]
    out = _latest(monkeypatch, ec_rows, include_legacy=False)
    assert (out["source"], out["value"]) == ("soil_lab_results", 9.0), out


def test_ece_evidence_keeps_the_prior_ece_behind_a_non_ece_extract():
    """One ECe rule for every reader: a non-ECe newest EC makes the ECe unknown (None), and
    the ECe before it comes back as ``prior_ece`` so a critical one is never dropped."""
    store = _store()
    rows = [
        _candidate("soil_lab_results:r15", {"ec_dsm": 0.5}, method="soil_water_1_5"),
        _candidate("soil_lab_results:r16", {"ec_dsm": 0.6}, method=None),
        _candidate("soil_lab_results:rid-old", {"ec_dsm": 12.0}, sampled_on=date(2026, 1, 1)),
    ]
    out = store.ece_evidence_from_candidates(rows)
    assert out["ece"] is None, out
    assert out["newer_other_extract"]["result_id"] == "r15", "the newest extract is labelled"
    assert out["newer_other_extract"]["extraction_method"] == "soil_water_1_5", out
    assert out["prior_ece"]["value"] == 12.0 and out["prior_ece"]["result_id"] == "rid-old", out
    out = store.ece_evidence_from_candidates([rows[2]])
    assert out["ece"]["value"] == 12.0 and out["prior_ece"] is None, out
    assert store.ece_evidence_from_candidates([]) == {
        "ece": None,
        "newer_other_extract": None,
        "prior_ece": None,
    }


def test_etc_dual_uses_the_field_state_ece_rule():
    """etc_dual reads field_state's ECe: a newest non-ECe EC leaves the ECe unknown (the
    default 0 is labelled so, not 'default' as if there were no lab data) and a critical
    prior ECe is reported instead of dropped."""
    import api.main  # noqa: F401 — resolve the application's router import cycle
    from api.routers.etc_dual import _soil_ece_input

    prior = {"value_dsm": 12.0, "critical": True}
    other = {"value_dsm": 0.4, "extraction_method": "soil_water_1_5"}
    assert _soil_ece_input(
        None, {"soil_ec": None, "soil_ec_other_extract": other, "soil_ec_prior_ece": prior}
    ) == (
        0.0,
        "default_ece_unknown_newer_extract_not_ece",
        True,
    )
    assert _soil_ece_input(None, {"soil_ec": 12.0, "soil_ec_source": "soil_lab_results"}) == (
        12.0,
        "soil_lab_results",
        False,
    )
    assert _soil_ece_input(None, {}) == (0.0, "default", False)
    assert _soil_ece_input(3.0, {"soil_ec_prior_ece": prior}) == (3.0, "request", False)


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

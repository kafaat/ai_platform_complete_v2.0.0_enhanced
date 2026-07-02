"""اختبارات وحدة (unit) لميزات agriai-engine — 2026-07-02.

تغطّي الوحدات الصرفة (evidence_bundle · replay · wofost_adapter · profit_planner) ونقاط
FastAPI (خلف importorskip). لا خدمات ولا pcse: مسار البديل الحتميّ هو ما تُمارسه CI.
"""

from __future__ import annotations

import importlib.util
import os

import pytest

ROOT = os.path.join(os.path.dirname(__file__), "..")
SVC = os.path.join(ROOT, "services", "agriai-engine")


def _load(mod_name: str):
    spec = importlib.util.spec_from_file_location(mod_name, os.path.join(SVC, f"{mod_name}.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ── evidence_bundle ──


@pytest.mark.unit
def test_evidence_bundle_hash_stable_under_reorder():
    eb = _load("evidence_bundle")
    a = eb.make_evidence_item(source="lab", kind="soil_ph", value=7.1, unit="pH", strength="lab")
    b = eb.make_evidence_item(
        source="iot", kind="soil_moisture", value=0.3, unit="frac", strength="iot"
    )
    bundle1 = eb.assemble_bundle([a, b])
    bundle2 = eb.assemble_bundle([b, a])  # ترتيب إدخال معكوس
    assert eb.canonical_bytes(bundle1) == eb.canonical_bytes(bundle2)
    assert eb.bundle_hash(bundle1) == eb.bundle_hash(bundle2)


@pytest.mark.unit
def test_evidence_bundle_key_order_independent():
    eb = _load("evidence_bundle")
    # نفس البند بترتيب مفاتيح داخليّ مختلف ⇒ نفس البصمة القانونيّة.
    item_a = {
        "kind": "ndvi",
        "source": "satellite",
        "value": 0.6,
        "strength": "satellite",
        "unit": "index",
    }
    item_b = {
        "value": 0.6,
        "unit": "index",
        "strength": "satellite",
        "source": "satellite",
        "kind": "ndvi",
    }
    assert eb.content_hash(item_a) == eb.content_hash(item_b)


@pytest.mark.unit
def test_evidence_bundle_different_evidence_different_hash():
    eb = _load("evidence_bundle")
    a = eb.make_evidence_item(source="lab", kind="soil_ph", value=7.1, unit="pH", strength="lab")
    a2 = eb.make_evidence_item(source="lab", kind="soil_ph", value=6.9, unit="pH", strength="lab")
    assert eb.bundle_hash(eb.assemble_bundle([a])) != eb.bundle_hash(eb.assemble_bundle([a2]))


@pytest.mark.unit
def test_evidence_float_normalization_stable():
    eb = _load("evidence_bundle")
    # 0.1+0.2 != 0.3 عائميّاً، لكن التطبيع يُثبّت البصمة.
    assert eb.content_hash({"x": 0.1 + 0.2}) == eb.content_hash({"x": 0.3})


@pytest.mark.unit
def test_evidence_unknown_strength_fails_closed():
    eb = _load("evidence_bundle")
    with pytest.raises(ValueError):
        eb.make_evidence_item(source="x", kind="y", value=1, strength="telepathy")


# ── replay ──


@pytest.mark.unit
def test_replay_hash_reorder_same_changed_differs():
    rp = _load("replay")
    inputs1 = {"crop": "wheat", "field": "F1", "params": {"a": 1, "b": 2}}
    inputs2 = {"params": {"b": 2, "a": 1}, "field": "F1", "crop": "wheat"}  # ترتيب معكوس
    assert rp.compute_replay_hash(inputs1) == rp.compute_replay_hash(inputs2)
    changed = {"crop": "barley", "field": "F1", "params": {"a": 1, "b": 2}}
    assert rp.compute_replay_hash(changed) != rp.compute_replay_hash(inputs1)


@pytest.mark.unit
def test_verify_replay_true_false():
    rp = _load("replay")
    inputs = {"crop": "wheat", "n": 3}
    h = rp.compute_replay_hash(inputs)
    assert rp.verify_replay({"n": 3, "crop": "wheat"}, h) is True
    assert rp.verify_replay({"crop": "wheat", "n": 4}, h) is False
    assert rp.verify_replay(inputs, "") is False


@pytest.mark.unit
def test_replay_engine_version_changes_hash():
    rp = _load("replay")
    inputs = {"crop": "wheat"}
    assert rp.compute_replay_hash(inputs, engine_version="v1") != rp.compute_replay_hash(
        inputs, engine_version="v2"
    )


@pytest.mark.unit
def test_replay_envelope_shape():
    rp = _load("replay")
    env = rp.build_envelope({"a": 1}, {"result": 42}, evidence_hash="eh")
    assert env["replay_hash"] == rp.compute_replay_hash({"a": 1})
    assert env["evidence_hash"] == "eh"
    assert env["result"] == {"result": 42}


# ── wofost_adapter (مسار البديل الحتميّ) ──


@pytest.mark.unit
def test_wofost_fallback_deterministic_schema():
    wa = _load("wofost_adapter")
    crop = {
        "base_temp_c": 5.0,
        "max_yield_kg_ha": 8000.0,
        "gdd_to_maturity": 1500.0,
        "water_use_efficiency": 18.0,
        "harvest_index": 0.45,
    }
    weather = {"gdd": 1500.0, "total_rain_mm": 200.0}
    soil = {"available_water_mm": 100.0}
    agro = {"irrigation_mm": 100.0}
    out = wa.simulate(crop=crop, weather=weather, soil=soil, agromanagement=agro)
    assert set(out) >= {"yield_kg_ha", "biomass", "water_use", "stages", "provenance"}
    assert out["provenance"] == "deterministic_fallback"
    # قيم حتميّة مُحتسبة يدويّاً: water-limited = 400mm*18 = 7200 < thermal 8000.
    assert out["yield_kg_ha"] == 7200.0
    assert out["biomass"] == 16000.0  # 7200 / 0.45
    assert out["water_use"] == 400.0  # 7200 / 18
    assert out["diagnostics"]["limiting_factor"] == "water"
    # تحديد يدويّ ثانٍ: نفس المدخلات ⇒ نفس المخرجات (تكرار).
    assert wa.simulate(crop=crop, weather=weather, soil=soil, agromanagement=agro) == out


@pytest.mark.unit
def test_wofost_fallback_monotonic_water_and_weather():
    wa = _load("wofost_adapter")
    crop = {"gdd_to_maturity": 3000.0}  # سقف حراريّ عالٍ كي يبقى القيد مائيّاً
    base_w = {"gdd": 1500.0, "total_rain_mm": 100.0}
    low = wa.simulate(crop=crop, weather=base_w, soil={}, agromanagement={"irrigation_mm": 50.0})
    high = wa.simulate(crop=crop, weather=base_w, soil={}, agromanagement={"irrigation_mm": 200.0})
    assert high["yield_kg_ha"] >= low["yield_kg_ha"]  # مزيد من الماء ⇒ ≥ غلّة
    # طقس أفضل (GDD أعلى) ⇒ ≥ غلّة (مع ماء وفير كي لا يُقيّد).
    wet = {"total_rain_mm": 5000.0}
    cool = wa.simulate(crop={}, weather={"gdd": 500.0, **wet}, soil={}, agromanagement={})
    warm = wa.simulate(crop={}, weather={"gdd": 1500.0, **wet}, soil={}, agromanagement={})
    assert warm["yield_kg_ha"] >= cool["yield_kg_ha"]


@pytest.mark.unit
def test_wofost_never_crashes_on_empty():
    wa = _load("wofost_adapter")
    out = wa.simulate()
    assert out["provenance"] == "deterministic_fallback"
    assert out["yield_kg_ha"] == 0.0


# ── profit_planner ──


@pytest.mark.unit
def test_profit_planner_worked_example_and_ranking():
    pp = _load("profit_planner")
    cands = [
        {
            "name": "wheat",
            "yield_kg_ha": 5000,
            "price_per_kg": 0.5,
            "costs": {"seed": 300, "water": 200, "fertilizer": 400, "labor": 100},
        },
        {
            "name": "barley",
            "yield_kg_ha": 4000,
            "price_per_kg": 0.6,
            "costs": {"seed": 250, "water": 150, "fertilizer": 300, "labor": 100},
        },
    ]
    plan = pp.plan_profit(cands, evidence_hash="EH")
    ranked = {r["name"]: r for r in plan["ranked"]}
    assert ranked["wheat"]["expected_profit"] == 1500.0  # 2500 - 1000
    assert ranked["barley"]["expected_profit"] == 1600.0  # 2400 - 800
    assert plan["ranked"][0]["name"] == "barley"  # أعلى ربح أوّلاً
    assert plan["ranked"][0]["rank"] == 1
    assert plan["best"] == "barley"
    assert plan["best_expected_profit"] == 1600.0
    assert plan["evidence_hash"] == "EH"


@pytest.mark.unit
def test_profit_planner_tie_broken_by_name():
    pp = _load("profit_planner")
    # ربح متساوٍ (1000 لكليهما) ⇒ كسر التعادل بالاسم تصاعديّاً بغضّ النظر عن الإدخال.
    cands = [
        {"name": "zebra", "yield_kg_ha": 2000, "price_per_kg": 1.0, "costs": {"c": 1000}},
        {"name": "alpha", "yield_kg_ha": 2000, "price_per_kg": 1.0, "costs": {"c": 1000}},
    ]
    plan = pp.plan_profit(cands)
    assert [r["name"] for r in plan["ranked"]] == ["alpha", "zebra"]
    assert plan["ranked"][0]["expected_profit"] == plan["ranked"][1]["expected_profit"] == 1000.0


@pytest.mark.unit
def test_profit_planner_empty():
    pp = _load("profit_planner")
    plan = pp.plan_profit([])
    assert plan["ranked"] == []
    assert plan["best"] is None


# ── نقاط FastAPI (خلف importorskip) ──


def _load_main(monkeypatch, token: str = "testtoken"):
    monkeypatch.setenv("SAHOOL_AGENT_TOKEN", token)
    return _load("main")


@pytest.mark.unit
def test_endpoint_recommend_returns_hashes_and_token_gate(monkeypatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    main = _load_main(monkeypatch)
    client = TestClient(main.app)
    body = {
        "field_id": "F1",
        "crop": "wheat",
        "candidates": [
            {"name": "wheat", "price_per_kg": 0.5, "costs": {"seed": 300}},
            {"name": "barley", "price_per_kg": 0.6, "costs": {"seed": 250}},
        ],
        "weather": {"gdd": 1500.0, "total_rain_mm": 300.0},
        "soil": {"available_water_mm": 100.0},
        "agromanagement": {"irrigation_mm": 100.0},
    }
    # بلا توكن ⇒ 401 (التوكن مضبوط)
    assert client.post("/recommend", json=body).status_code == 401
    # بتوكن صالح ⇒ 200 مع بصمتَي أدلّة/إعادة
    r = client.post("/recommend", json=body, headers={"x-agent-token": "testtoken"})
    assert r.status_code == 200
    data = r.json()
    assert "evidence_hash" in data and "replay_hash" in data
    assert data["evidence_sufficient"] is True  # NDVI+soil_ph مشتقّان
    assert data["plan"]["best"] in {"wheat", "barley"}


@pytest.mark.unit
def test_endpoint_replay_verify_roundtrips(monkeypatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    main = _load_main(monkeypatch)
    client = TestClient(main.app)
    hdr = {"x-agent-token": "testtoken"}
    inputs = {"a": 1, "b": {"c": 2}}
    rec = client.post(
        "/recommend",
        json={"field_id": "F1", "candidates": [{"name": "wheat", "price_per_kg": 0.5}]},
        headers=hdr,
    ).json()
    # تحقّق دائريّ لبصمة إعادة التشغيل من نقطة /replay/verify.
    import importlib.util as _u

    spec = _u.spec_from_file_location("replay", os.path.join(SVC, "replay.py"))
    rp = _u.module_from_spec(spec)
    spec.loader.exec_module(rp)
    h = rp.compute_replay_hash(inputs)
    ok = client.post("/replay/verify", json={"inputs": inputs, "prior_hash": h}, headers=hdr).json()
    assert ok["verified"] is True
    bad = client.post(
        "/replay/verify", json={"inputs": inputs, "prior_hash": "deadbeef"}, headers=hdr
    ).json()
    assert bad["verified"] is False
    assert rec["replay_hash"]  # نقطة recommend تُصدر بصمة إعادة


@pytest.mark.unit
def test_endpoint_token_unset_returns_503(monkeypatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    main = _load_main(monkeypatch)
    main.AGENT_TOKEN = ""  # محاكاة غياب التوكن ⇒ معطّل بأمان
    client = TestClient(main.app)
    assert client.post("/simulate", json={"crop": {}}).status_code == 503

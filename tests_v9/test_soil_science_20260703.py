"""test_soil_science_20260703.py — تفسير التربة (قوام USDA + ملاءمة محصول + SoilGrids).

يسدّ فجوة حقيقيّة مُستلهَمة من بحث OpenFarm/SoilGrids: soil-service كان يخزّن قراءات
الحسّاسات فقط دون تفسير زراعيّ. يغطّي:
  • ``soil_science`` (نقيّ): تصنيف قوام USDA + ملاءمة محصول شفّافة (Liebig min).
  • ``soilgrids_client``: استخراج/تحويل خصائص SoilGrids + فشل ناعم (لا اختراع).
  • نقطتا HTTP (/soil/suitability · /soil/soilgrids) — importorskip للتبعيّات.

الوحدتان النقيّتان تُحمَّلان مباشرةً من مجلّد الخدمة (كما يفعل حارس التفكيك).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_SVC = Path(__file__).resolve().parents[1] / "services" / "soil-service"


def _load_isolated(unique_name: str, filename: str):
    """يحمّل وحدة قائمة بذاتها من مجلّد الخدمة باسم فريد **دون لمس sys.path** —
    يتفادى تصادم أسماء الوحدات العامّة (main/db_persist/routers) عبر الخدمات."""
    spec = importlib.util.spec_from_file_location(unique_name, _SVC / filename)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


soil_science = _load_isolated("soil_science_under_test", "soil_science.py")
soilgrids_client = _load_isolated("soilgrids_client_under_test", "soilgrids_client.py")


@pytest.fixture(autouse=True)
def _preserve_sibling_main():
    """يستعيد أيّ وحدة عامّة الاسم (main/routers لخدمة أخرى) بعد كلّ اختبار — عزل صادق."""

    def _keys():
        return [
            k
            for k in sys.modules
            if k in ("main", "router_registry", "routers", "db_persist") or k.startswith("routers.")
        ]

    saved = {k: sys.modules[k] for k in _keys()}
    yield
    for k in _keys():
        sys.modules.pop(k, None)
    sys.modules.update(saved)
    while str(_SVC) in sys.path:
        sys.path.remove(str(_SVC))


# ── قوام USDA (نقاط مرجعيّة قياسيّة) ─────────────────────────────────────────────
@pytest.mark.parametrize(
    "clay,sand,silt,expected",
    [
        (50, 20, 30, "clay"),
        (5, 90, 5, "sand"),
        (8, 84, 8, "loamy sand"),
        (15, 60, 25, "sandy loam"),
        (20, 40, 40, "loam"),
        (15, 20, 65, "silt loam"),
        (10, 5, 85, "silt"),
        (30, 55, 15, "sandy clay loam"),
        (32, 33, 35, "clay loam"),
        (30, 20, 50, "silty clay loam"),
        (35, 50, 15, "sandy clay"),
        (45, 10, 45, "silty clay"),
    ],
)
def test_usda_texture_reference_points(clay, sand, silt, expected):
    assert soil_science.usda_texture_class(clay, sand, silt)["key"] == expected


def test_texture_normalizes_and_validates():
    # مجموع ≠ 100 يُطبَّع.
    assert soil_science.usda_texture_class(60, 60, 60)["clay"] == pytest.approx(33.3, abs=0.1)
    with pytest.raises(ValueError):
        soil_science.usda_texture_class(-1, 50, 51)
    with pytest.raises(ValueError):
        soil_science.usda_texture_class(0, 0, 0)


# ── ملاءمة المحصول (قواعد شفّافة) ────────────────────────────────────────────────
def test_suitability_optimal_is_excellent():
    r = soil_science.crop_suitability(crop="wheat", ph=6.8, ec=1.0, texture_key="loam")
    assert r["score"] == 1.0 and r["rating_ar"] == "ممتاز"


def test_suitability_liebig_minimum_governs():
    # الملوحة العالية هي العامل المُقيِّد رغم مثاليّة pH/القوام.
    r = soil_science.crop_suitability(crop="tomato", ph=6.4, ec=2.5, texture_key="loam")
    assert r["score"] == 0.0
    assert r["limiting_ar"] == "الملوحة (EC)"


def test_date_palm_tolerates_salinity_better_than_tomato():
    dp = soil_science.crop_suitability(crop="date_palm", ph=8.0, ec=9.0, texture_key="sandy loam")
    tom = soil_science.crop_suitability(crop="tomato", ph=8.0, ec=9.0, texture_key="sandy loam")
    assert dp["score"] > tom["score"], "النخيل أكثر تحمّلاً للملوحة من الطماطم"


def test_suitability_missing_data_is_honest():
    r = soil_science.crop_suitability(crop="wheat")
    assert r["score"] is None and "غير كافية" in r["rating_ar"]


def test_unknown_crop_raises():
    with pytest.raises(ValueError):
        soil_science.crop_suitability(crop="banana", ph=6.0)


def test_rank_crops_orders_by_score_desc():
    ranked = soil_science.rank_crops(ph=8.0, ec=10.0, texture_key="sandy loam")
    scores = [r["score"] for r in ranked if r["score"] is not None]
    assert scores == sorted(scores, reverse=True)
    assert ranked[0]["crop"] == "date_palm"  # الأنسب لتربة مالحة رمليّة قلويّة


# ── عميل SoilGrids (استخراج + فشل ناعم) ──────────────────────────────────────────
def _sg_payload():
    def layer(name, mean):
        return {"name": name, "depths": [{"label": "0-5cm", "values": {"mean": mean}}]}

    return {
        "properties": {
            "layers": [
                layer("clay", 250),  # 25.0%
                layer("sand", 400),  # 40.0%
                layer("silt", 350),  # 35.0%
                layer("phh2o", 72),  # pH 7.2
                layer("soc", 150),  # 1.5%
                layer("cec", 180),  # 180 mmol(c)/kg
            ]
        }
    }


def test_soilgrids_extract_converts_units():
    props = soilgrids_client._extract(_sg_payload())
    assert props["clay_pct"] == 25.0
    assert props["ph"] == 7.2
    assert props["soc_pct"] == 1.5
    assert props["cec"] == 180.0


def test_soilgrids_extract_empty_returns_none():
    assert soilgrids_client._extract({"properties": {"layers": []}}) is None
    assert soilgrids_client._extract({}) is None


class _FakeResp:
    def __init__(self, status_code, payload=None, raise_exc=None):
        self.status_code = status_code
        self._payload = payload
        self._raise = raise_exc

    def json(self):
        return self._payload


class _FakeClient:
    def __init__(self, resp=None, exc=None):
        self._resp = resp
        self._exc = exc

    def get(self, url, params=None):
        if self._exc:
            raise self._exc
        return self._resp


def test_fetch_soil_properties_success_with_injected_client():
    cli = _FakeClient(resp=_FakeResp(200, _sg_payload()))
    out = soilgrids_client.fetch_soil_properties(46.0, 24.0, client=cli)
    assert out is not None and out["source"] == "soilgrids"
    assert out["properties"]["clay_pct"] == 25.0


def test_fetch_soil_properties_failsoft_on_error():
    # تعذّر وصول ⇒ None.
    assert (
        soilgrids_client.fetch_soil_properties(
            46.0, 24.0, client=_FakeClient(exc=RuntimeError("boom"))
        )
        is None
    )
    # ردّ غير 2xx ⇒ None.
    assert (
        soilgrids_client.fetch_soil_properties(46.0, 24.0, client=_FakeClient(resp=_FakeResp(500)))
        is None
    )


# ── نقاط HTTP (importorskip fastapi + asyncpg) ──────────────────────────────────
def _load_soil_main(monkeypatch):
    pytest.importorskip("fastapi")
    pytest.importorskip("asyncpg")
    monkeypatch.setenv("SAHOOL_AGENT_TOKEN", "test-token")
    while str(_SVC) in sys.path:
        sys.path.remove(str(_SVC))
    sys.path.insert(0, str(_SVC))
    for name in ("main", "router_registry", "routers", "routers.soil_profile", "routers.modbus"):
        sys.modules.pop(name, None)
    import main

    return main


def test_suitability_endpoint_requires_token(monkeypatch):
    main = _load_soil_main(monkeypatch)
    from fastapi.testclient import TestClient

    client = TestClient(main.app)
    r = client.post("/soil/suitability", json={"clay": 25, "sand": 40, "silt": 35, "ph": 7.0})
    assert r.status_code == 401  # لا توكن ⇒ يُرفَض


def test_suitability_endpoint_returns_texture_and_crops(monkeypatch):
    main = _load_soil_main(monkeypatch)
    from fastapi.testclient import TestClient

    client = TestClient(main.app)
    r = client.post(
        "/soil/suitability",
        json={"clay": 25, "sand": 40, "silt": 35, "ph": 7.0, "ec": 1.0},
        headers={"X-Agent-Token": "test-token"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["texture"]["key"] == "loam"
    assert body["crops"] and all("score" in c for c in body["crops"])


def test_soilgrids_endpoint_503_when_unavailable(monkeypatch):
    main = _load_soil_main(monkeypatch)
    import soilgrids_client as sgc

    monkeypatch.setattr(sgc, "fetch_soil_properties", lambda lon, lat: None)
    from fastapi.testclient import TestClient

    client = TestClient(main.app)
    r = client.get("/soil/soilgrids?lon=46&lat=24", headers={"X-Agent-Token": "test-token"})
    assert r.status_code == 503
    assert r.json()["detail"]["error"] == "soilgrids_unavailable"


def test_soilgrids_endpoint_200_with_data(monkeypatch):
    main = _load_soil_main(monkeypatch)
    import soilgrids_client as sgc

    monkeypatch.setattr(
        sgc,
        "fetch_soil_properties",
        lambda lon, lat: {
            "source": "soilgrids",
            "lon": lon,
            "lat": lat,
            "properties": {"clay_pct": 25.0, "sand_pct": 40.0, "silt_pct": 35.0, "ph": 7.0},
        },
    )
    from fastapi.testclient import TestClient

    client = TestClient(main.app)
    r = client.get("/soil/soilgrids?lon=46&lat=24", headers={"X-Agent-Token": "test-token"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["source"] == "soilgrids"
    assert body["texture"]["key"] == "loam"
    assert body["crops"]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))

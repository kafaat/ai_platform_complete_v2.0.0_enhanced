"""انقطاعُ فهرس CDSE لا يُقرأ «لا مشاهد» — CDSE-CATALOG-OUTAGE-READ-AS-NO-SCENES-01.

كان أيُّ استثناءٍ في بحث الفهرس يصير قائمةً فارغة بـ``warning: None``، فمهلةُ اتّصالٍ وبحثٌ
ناجحٌ بلا مشاهد يُنتجان النتيجةَ نفسها من ``stac_search`` ثمّ الاستجابةَ العامّةَ نفسها من
``/v1/imagery/best`` (``best: None`` · «لا مشاهد ضمن المعايير»).

**حدُّ الإغلاق باختبارين** (لكلّ طبقة):
  • مهلةٌ ⇒ حالةٌ مميَّزة مُسمّاة (``catalog_unavailable``)، و``/best`` يُعيد 502 بالسبب.
  • نتيجةٌ صحيحة فارغة ⇒ «لا مشاهد» كما كانت (``status: ok`` · ``best: None``).

بالموجِّه الحقيقيّ والوحدة الحقيقيّة؛ عميلُ CDSE وحده مُزيَّف (لا شبكة).
"""

from __future__ import annotations

import asyncio
import importlib.util
import pathlib
import sys
import types

import pytest

pytestmark = pytest.mark.unit

_RASTER = pathlib.Path(__file__).resolve().parents[1] / "services" / "raster-service"
_GUARDED = ("cdse_client", "imagery_source_gate", "stac_search")


@pytest.fixture(autouse=True)
def _isolate_modules():
    saved = {k: sys.modules.get(k) for k in _GUARDED}
    added_path = str(_RASTER) not in sys.path
    if added_path:
        sys.path.insert(0, str(_RASTER))
    yield
    for key, val in saved.items():
        if val is None:
            sys.modules.pop(key, None)
        else:
            sys.modules[key] = val
    for k in [k for k in sys.modules if k.startswith("cdse_outage_")]:
        sys.modules.pop(k, None)
    if added_path:
        sys.path.remove(str(_RASTER))


def _fake_cdse(search):
    client = types.SimpleNamespace(search_scenes=search)
    fake = types.ModuleType("cdse_client")
    fake.is_configured = lambda: True  # type: ignore[attr-defined]
    fake.get_client = lambda: client  # type: ignore[attr-defined]
    return fake


def _fake_gate():
    gate = types.ModuleType("imagery_source_gate")
    gate.enforce_enabled = lambda: False  # type: ignore[attr-defined]
    return gate


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, _RASTER / rel)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def _timeout(**_kw):
    raise TimeoutError("catalog timed out")


def _empty(**_kw):
    return []


def _stac(search):
    pytest.importorskip("fastapi")
    sys.modules["cdse_client"] = _fake_cdse(search)
    sys.modules["imagery_source_gate"] = _fake_gate()
    mod = _load("cdse_outage_stac", "stac_search.py")
    mod.HISTORICAL_SEARCH_PROVIDER = "cdse"
    return mod


def _search(mod):
    return asyncio.run(
        mod.stac_search(
            [44.0, 15.0, 44.1, 15.1], "2026-09-01T00:00:00Z", "2026-10-01T23:59:59Z", 40, 10
        )
    )


def test_a_catalog_timeout_is_a_named_state_not_an_empty_search():
    mod = _stac(_timeout)
    out = _search(mod)
    assert out["items"] == [] and out["count"] == 0
    assert out["status"] == mod.SEARCH_STATUS_CATALOG_UNAVAILABLE == "catalog_unavailable"
    assert out["warning"] == "catalog_unavailable"
    assert out["error_type"] == "TimeoutError"


def test_a_successful_empty_search_stays_no_scenes():
    mod = _stac(_empty)
    out = _search(mod)
    assert out["items"] == [] and out["count"] == 0
    assert out["status"] == mod.SEARCH_STATUS_OK == "ok"
    assert out["warning"] is None


def _best_client(search):
    pytest.importorskip("fastapi")
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    stac = _stac(search)
    sys.modules["stac_search"] = stac
    router_mod = _load("cdse_outage_router", "routers/imagery_search.py")
    app = FastAPI()
    app.include_router(router_mod.router)
    return TestClient(app)


_BEST = "/v1/imagery/best?west=44.0&south=15.0&east=44.1&north=15.1"


def test_best_scene_reports_a_catalog_outage_as_a_named_502():
    resp = _best_client(_timeout).get(_BEST)
    assert resp.status_code == 502, resp.text
    detail = resp.json()["detail"]
    assert detail["error"] == "catalog_unavailable"
    assert detail["error_type"] == "TimeoutError"
    assert "best" not in resp.json()


def test_best_scene_still_says_no_scenes_for_a_real_empty_result():
    resp = _best_client(_empty).get(_BEST)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["best"] is None and body["candidates"] == 0
    assert "لا مشاهد" in body["note"]

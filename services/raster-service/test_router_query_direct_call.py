"""Guard: new terrain/soil endpoints survive direct (non-HTTP) invocation.

External review found every new endpoint crashing on a direct call with
`AttributeError: 'Query' object has no attribute 'split'` — the `= Query(...)`
defaults are FastAPI Query objects, not real values, unless FastAPI injects them
over HTTP. Unit tests / internal calls hit the raw object. Converting to
`Annotated[T, Query()] = <default>` makes the Python default a genuine value, so
direct calls work for both HTTP and unit paths. This locks that in.

Run in the raster-service suite (numpy/rasterio available).
"""

from __future__ import annotations

import asyncio

import main
import routers.soil_tiles as st
import routers.terrain_tiles as tt


async def _noop_tenant(field_id, **kwargs):
    return None


def _patch_tenant(monkeypatch):
    monkeypatch.setattr(tt, "require_field_tenant", _noop_tenant)
    monkeypatch.setattr(st, "require_field_tenant", _noop_tenant)
    main._REQ_TENANT.set("t-test")  # ContextVar.get للقراءة فقط — نضبط القيمة


def test_terrain_endpoints_direct_call_no_query_crash(monkeypatch):
    _patch_tenant(monkeypatch)
    # لا bbox مُمرَّر ⇒ الافتراضيّ يجب أن يكون None حقيقيّاً لا كائن Query.
    contours = asyncio.run(tt.field_contours("f-test"))
    assert contours["computed"] is False  # fail-closed (لا DEM) لا استثناء
    tj = asyncio.run(tt.terrain_tilejson())
    assert "available" in tj


def test_soil_endpoints_direct_call_no_query_crash(monkeypatch):
    _patch_tenant(monkeypatch)
    summary = asyncio.run(st.field_soil_summary("f-test"))
    assert summary.get("computed") is False
    zones = asyncio.run(st.field_soil_sampling_zones("f-test"))
    assert zones.get("computed") is False
    plan = asyncio.run(st.field_soil_sampling_plan("f-test"))
    assert plan.get("computed") is False
    tj = asyncio.run(st.soil_tilejson())
    assert "available" in tj and "disclaimer" in tj


def test_no_bare_query_default_in_new_routers():
    # حارس انحدار: لا يعود أيّ `= Query(...)` كافتراضيّ بايثونيّ (يجب Annotated).
    import pathlib

    here = pathlib.Path(__file__).resolve().parent
    for rel in ("routers/terrain_tiles.py", "routers/soil_tiles.py"):
        src = (here / rel).read_text(encoding="utf-8")
        assert "= Query(" not in src, f"{rel}: بارامتر Query كافتراضيّ بايثونيّ (استخدم Annotated)"


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-v"]))

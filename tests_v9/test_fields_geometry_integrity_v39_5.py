"""v39.5-1: DB-enforced validity for fields.geometry + inline geometry_version.

The real draw/PATCH store is ``fields.geometry`` (JSONB GeoJSON, v30). v27 only guards a
DIFFERENT table (``field_boundaries.geom``) and v43's ``trg_fields_sync_geom`` SWALLOWS invalid
GeoJSON (derived ``fields.geom`` := NULL) — so a self-intersecting polygon written straight into
``fields.geometry`` was accepted with no DB-level rejection. v134 adds a BEFORE trigger that
RAISEs ``check_violation`` (SQLSTATE 23514) on ``fields`` and an inline ``geometry_version`` that
bumps ONLY when the boundary changes.

Mirrors ``tests_v9/test_gis_enforce.py`` — same ``_BOWTIE`` self-intersection pattern and the
anti-false-positive assert (a VALID polygon is NOT rejected). Integration test skips with no DB.
"""

from __future__ import annotations

import json
import os
import sys
import uuid

import pytest

# ── valid unit square vs self-intersecting bow-tie, as GeoJSON geometry objects ──
_VALID_GEOJSON = {"type": "Polygon", "coordinates": [[[0, 0], [0, 1], [1, 1], [1, 0], [0, 0]]]}
_VALID2_GEOJSON = {"type": "Polygon", "coordinates": [[[0, 0], [0, 2], [2, 2], [2, 0], [0, 0]]]}
_BOWTIE_GEOJSON = {"type": "Polygon", "coordinates": [[[0, 0], [1, 1], [1, 0], [0, 1], [0, 0]]]}


# ════════════════════════ unit (pure model, no DB) ════════════════════════
# geometry_version must be a first-class field on FieldDetail so clients get a real boundary
# version without a field_geometry_history join. Pure pydantic ⇒ runs in the default CI gate.

ROOT = os.path.join(os.path.dirname(__file__), "..")
CORE = os.path.join(ROOT, "services/sahool-platform")
if CORE not in sys.path:
    sys.path.insert(0, CORE)


@pytest.mark.unit
def test_field_detail_surfaces_geometry_version():
    pytest.importorskip("pydantic")
    from api.field_models import FieldDetail, _row_to_field_detail

    detail = FieldDetail(
        field_id="fld_1",
        farm_id="farm_1",
        name_ar="حقل",
        crop="قمح",
        area_ha=1.0,
        quality_grade="READY",
        health_summary_ar="صحّي",
        geometry_version=7,
    )
    assert detail.geometry_version == 7
    assert detail.model_dump()["geometry_version"] == 7

    # default (column absent from an older row) ⇒ None, never an exception.
    default_detail = FieldDetail(
        field_id="fld_2",
        farm_id="farm_1",
        name_ar="حقل",
        crop="قمح",
        area_ha=1.0,
        quality_grade="READY",
        health_summary_ar="صحّي",
    )
    assert default_detail.geometry_version is None

    # _row_to_field_detail reads geometry_version from a mapping row.
    row = {
        "field_id": "fld_3",
        "farm_id": "farm_1",
        "name": "حقل",
        "crop": "قمح",
        "area_ha": 1.0,
        "soil_type": None,
        "manager": None,
        "lat": None,
        "lon": None,
        "geometry": None,
        "geometry_version": 4,
    }
    assert _row_to_field_detail(row).geometry_version == 4


# ════════════════════════ integration (needs Postgres + PostGIS) ════════════════════════

TEST_DB_URL = os.getenv(
    "TEST_DATABASE_URL", "postgresql://sahool_test:test_password@127.0.0.1:5433/sahool_test"
)


async def _insert_field(conn, tid: str, field_id: str, geometry: dict | None):
    await conn.execute(
        "INSERT INTO fields (field_id, name, area_ha, tenant_id, geometry) "
        "VALUES ($1, $2, $3, $4::uuid, $5::jsonb)",
        field_id,
        "اختبار الهندسة",
        1.0,
        tid,
        json.dumps(geometry) if geometry is not None else None,
    )


@pytest.mark.integration
async def test_fields_geometry_db_validity_and_inline_version():
    asyncpg = pytest.importorskip("asyncpg")
    try:
        # statement_cache_size=0 keeps this safe behind a pgbouncer/transaction pooler.
        conn = await asyncpg.connect(TEST_DB_URL, timeout=5, statement_cache_size=0)
    except Exception:  # noqa: BLE001
        pytest.skip("قاعدة الاختبار غير مشغّلة")

    tid = str(uuid.uuid4())
    try:
        tr = conn.transaction()
        await tr.start()
        try:
            # fields has FORCE RLS (v9) ⇒ must set the tenant context to write.
            await conn.execute("SELECT set_config('app.current_tenant', $1, true)", tid)

            # ① false-positive guard: a VALID polygon is accepted and starts at version 1.
            fid_ok = "fld_geo_" + uuid.uuid4().hex[:8]
            await _insert_field(conn, tid, fid_ok, _VALID_GEOJSON)
            gv = await conn.fetchval(
                "SELECT geometry_version FROM fields WHERE field_id = $1", fid_ok
            )
            assert gv == 1, f"إدراج هندسة صالحة يجب أن يبدأ بـgeometry_version=1، الفعليّ: {gv}"

            # ② a geometry change bumps geometry_version (1 → 2).
            await conn.execute(
                "UPDATE fields SET geometry = $2::jsonb WHERE field_id = $1",
                fid_ok,
                json.dumps(_VALID2_GEOJSON),
            )
            gv2 = await conn.fetchval(
                "SELECT geometry_version FROM fields WHERE field_id = $1", fid_ok
            )
            assert gv2 == 2, f"تغيير الهندسة يجب أن يرفع geometry_version إلى 2، الفعليّ: {gv2}"

            # ③ an attribute-only UPDATE must NOT bump geometry_version (stays 2).
            await conn.execute(
                "UPDATE fields SET name = $2 WHERE field_id = $1", fid_ok, "اسم جديد"
            )
            gv3 = await conn.fetchval(
                "SELECT geometry_version FROM fields WHERE field_id = $1", fid_ok
            )
            assert gv3 == 2, f"تحديث حقل غير الهندسة يجب ألّا يرفع geometry_version، الفعليّ: {gv3}"

            # ④ INSERT of a self-intersecting bow-tie is rejected with check_violation (23514).
            #    Assert the specific SQLSTATE so a missing table / RLS / connection failure is
            #    NOT counted as a false success (same anti-false-positive rule as v27's test).
            err_insert = None
            sp = conn.transaction()
            await sp.start()
            try:
                await _insert_field(conn, tid, "fld_bt_" + uuid.uuid4().hex[:8], _BOWTIE_GEOJSON)
            except Exception as e:  # noqa: BLE001
                err_insert = getattr(e, "sqlstate", None)
            finally:
                await sp.rollback()
            assert err_insert == "23514", (
                f"متوقّع رفض إدراج الفراشة بـcheck_violation (23514)، الفعليّ: {err_insert}"
            )

            # ⑤ UPDATE to a bow-tie is likewise rejected (the PATCH path the API actually uses).
            err_update = None
            sp2 = conn.transaction()
            await sp2.start()
            try:
                await conn.execute(
                    "UPDATE fields SET geometry = $2::jsonb WHERE field_id = $1",
                    fid_ok,
                    json.dumps(_BOWTIE_GEOJSON),
                )
            except Exception as e:  # noqa: BLE001
                err_update = getattr(e, "sqlstate", None)
            finally:
                await sp2.rollback()
            assert err_update == "23514", (
                f"متوقّع رفض تحديث الهندسة إلى فراشة بـcheck_violation (23514)، الفعليّ: {err_update}"
            )
        finally:
            await tr.rollback()
    finally:
        await conn.close()

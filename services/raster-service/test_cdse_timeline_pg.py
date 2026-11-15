"""Read the cold asset timeline using PostgreSQL and actual native receipt fields."""

import asyncio
import json
import os
import uuid

import asyncpg
import db_persist
import pytest

DB_URL = os.getenv("RASTER_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DB_URL, reason="RASTER_TEST_DATABASE_URL is not configured")


@pytest.mark.parametrize(
    "case",
    [
        "verified",
        "wrong_scene",
        "wrong_cog",
        "wrong_day",
        "no_valid_pixels",
        "no_receipt",
        "wrong_algorithm",
        "wrong_mask",
        "bare_date",
    ],
)
def test_native_timestamp_must_belong_to_this_pixel_source(monkeypatch, case):
    monkeypatch.setattr(db_persist, "DATABASE_URL", DB_URL)
    tenant = str(uuid.uuid4())
    field = "time-regression"
    subject = "cdse:sh:120001"
    uri = "file:///tmp/native-test.tif"
    capture = "2024-02-26T07:35:29.425000+00:00"
    qa = {
        "scene_id": subject,
        "acquisition_datetime": capture,
        "input_checksum": "e" * 64,
        "algorithm_version": "cdse-evalscript-sha256:" + "1" * 64,
        "qa_mask_version": "cdse-native-scl-datamask/2",
        "native_valid_pixels": 20,
    }
    algorithm, mask = qa["algorithm_version"], qa["qa_mask_version"]
    qa.update(
        {
            "wrong_scene": {"scene_id": "cdse:sh:120002"},
            "wrong_day": {"acquisition_datetime": capture.replace("-26T", "-27T")},
            "no_valid_pixels": {"native_valid_pixels": 0},
            "wrong_algorithm": {"algorithm_version": "different"},
            "wrong_mask": {"qa_mask_version": "different"},
            "bare_date": {"acquisition_datetime": "2024-02-26"},
        }.get(case, {})
    )
    provenance = {
        "provider": "cdse",
        "current_cog_uri": "file:///previous.tif" if case == "wrong_cog" else uri,
        "stats": {"cdse_native_qa": None if case == "no_receipt" else qa},
    }

    async def run():
        conn = await asyncpg.connect(DB_URL)
        try:
            await conn.execute("SELECT set_config('app.current_tenant', $1, false)", tenant)
            await conn.execute(
                """INSERT INTO raster_assets(field_id,tenant_id,scene_id,acquisition_date,index_name,cog_uri,
                    algorithm_version,qa_mask_version,provenance,asset_status)
                    VALUES ($1,$2::uuid,$3,'2024-02-26','ndvi',$4,$5,$6,$7::jsonb,'ready')""",
                field,
                tenant,
                subject,
                uri,
                algorithm,
                mask,
                json.dumps(provenance),
            )
            # Catalogue candidates do not establish the contributor to this output.
            await conn.execute(
                """INSERT INTO stac_item_registry(tenant_id,scene_id,collection,captured_at)
                VALUES($1::uuid,$2,'sentinel-2-l2a','2024-02-26T13:00:00Z')""",
                tenant,
                subject,
            )
            rows = await db_persist.list_available_asset_dates(field, tenant)
            assert len(rows) == 1
            assert rows[0]["acquisition_datetime"] == (
                capture.replace("+00:00", "Z") if case == "verified" else None
            )
        finally:
            await conn.execute("DELETE FROM stac_item_registry WHERE tenant_id=$1::uuid", tenant)
            await conn.execute("DELETE FROM raster_assets WHERE tenant_id=$1::uuid", tenant)
            await conn.close()

    asyncio.run(run())

"""يُثبت أنّ مسار القراءة (شبكة/بلاطات) يُعيد الترطيب من raster_assets عند
غياب الفهرس من الذاكرة (محاكاة إعادة تشغيل) — أي أنّ persistence مُستهلَك فعلاً.

يتطلّب DATABASE_URL يشير إلى قاعدة بها جدول raster_assets (الترحيلات مطبَّقة).
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def main_test():
    import db_persist
    import main as svc
    import numpy as np
    import pyproj
    import rasterio
    from rasterio.transform import from_origin

    os.makedirs(svc.UPLOAD_DIR, exist_ok=True)
    cog_path = os.path.join(svc.UPLOAD_DIR, "rehydrate_ndvi.tif")
    prof = dict(
        driver="GTiff",
        width=20,
        height=20,
        count=1,
        dtype="float32",
        crs="EPSG:32638",
        transform=from_origin(400000, 1772000, 10, 10),
        nodata=float("nan"),
    )
    with rasterio.open(cog_path, "w", **prof) as ds:
        ds.write(np.full((20, 20), 0.6, "float32"), 1)  # NDVI=0.6

    tf = pyproj.Transformer.from_crs("EPSG:32638", "EPSG:4326", always_xy=True)
    lon0, lat0 = tf.transform(400000, 1772000)
    lon1, lat1 = tf.transform(400200, 1771800)
    footprint = {
        "type": "Polygon",
        "coordinates": [[[lon0, lat0], [lon1, lat0], [lon1, lat1], [lon0, lat1], [lon0, lat0]]],
    }

    field = "rehydrate_field_X"
    # مستأجِر UUID حقيقيّ (لا None): قراءات الإنتاج تُرشِّح بـtenant_id=$uuid صراحةً،
    # فصفّ tenant_id=NULL لا يُرى ⇒ الاختبار يجب أن يعكس واقع الإنتاج (تدقيق 2026-07-05).
    tenant = "33333333-3333-3333-3333-333333333333"
    svc._REQ_TENANT.set(tenant)
    ok = asyncio.run(
        db_persist.insert_raster_asset(
            field_id=field,
            tenant_id=tenant,
            scene_id="s",
            acquisition_date="2026-06-01",
            satellite="sentinel-2",
            index_name="ndvi",
            cloud_pct=0.0,
            srid=32638,
            cog_uri="file://" + cog_path,
            bands={"red": 1, "nir": 2},
            nodata=0.0,
            footprint=footprint,
            processing_job_id="rehydrate_job_1",
            provenance={},
        )
    )
    assert ok, "insert_raster_asset فشل — هل DATABASE_URL/جدول raster_assets متاح؟"

    # محاكاة إعادة التشغيل: أفرغ فهرس الذاكرة لهذا الحقل
    svc._field_layers.pop(field, None)
    for lid in [k for k in svc._layers if field in k]:
        svc._layers.pop(lid, None)
    assert field not in svc._field_layers, "الذاكرة لم تُفرَّغ"

    from fastapi.testclient import TestClient

    c = TestClient(svc.app)
    # الترويسة X-Tenant-Id يحقنها الجيت-واي في الإنتاج؛ القراءة tenant-scoped فتلزم.
    _h = {"x-tenant-id": tenant}
    r = c.get(f"/v1/fields/{field}/indicator-grid?index=ndvi&grid=8", headers=_h)
    j = r.json()
    print(
        f"status={r.status_code} real_data={j.get('real_data')} "
        f"source={j.get('source')} mean={j.get('stats', {}).get('mean')}"
    )
    assert r.status_code == 200
    assert j["real_data"] is True, (
        f"يجب الترطيب من DB (real_data=True) لكن حصلنا {j.get('real_data')} "
        f"(source={j.get('source')}) — persistence غير مُستهلَك"
    )

    # وتبلاطة: يجب أن تُصيَّر فعليّاً (ليست شفّافة بالكامل) بعد الترطيب
    rt = c.get(f"/v1/fields/{field}/tilejson?index=ndvi", headers=_h)
    assert rt.status_code == 200 and rt.json().get("tiles"), "tilejson بعد الترطيب فشل"
    print(
        "✓ الترطيب من raster_assets يعمل — persistence مُستهلَك (شبكة + tilejson) عبر إعادة التشغيل"
    )


if __name__ == "__main__":
    main_test()
    print("ALL REHYDRATE ASSERTIONS PASSED")

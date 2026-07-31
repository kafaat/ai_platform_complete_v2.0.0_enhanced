"""يُثبت جسر الاستيراد→المعالجة: نطاقات STAC منفصلة (COG لكلّ نطاق) → VRT →
/v1/fields/{id}/process-from-stac → قصّ→مؤشّر→COG→persist→قراءة حقيقيّة.

محلّيّ بالكامل (بلا شبكة): نحاكي COGs المنفصلة بملفّات .tif محلّيّة.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def run():
    import numpy as np
    import rasterio
    import stac_vrt
    from rasterio.transform import from_origin

    # نطاقان منفصلان (red, nir) — كما يقدّمهما Element84 لـSentinel-2 L2A
    prof = dict(
        driver="GTiff",
        width=30,
        height=30,
        count=1,
        dtype="float32",
        crs="EPSG:32638",
        transform=from_origin(400000, 1772000, 10, 10),
    )
    # تحت UPLOAD_DIR — حارس المصدر (_safe_raster_source) يقبل المسارات المحلّيّة
    # (خام أو file://) داخل هذا المجلّد فقط؛ /tmp مباشرة يُرفَض 400.
    upload_dir = os.environ.get("RASTER_UPLOAD_DIR", "/tmp/sahool_rasters")
    os.makedirs(upload_dir, exist_ok=True)
    paths = {}
    for name, val in [("red", 0.2), ("nir", 0.7)]:
        p = os.path.join(upload_dir, f"_stac_{name}.tif")
        with rasterio.open(p, "w", **prof) as ds:
            ds.write(np.full((30, 30), val, "float32"), 1)
        paths[name] = p

    # (أ) المُولّد يبني VRT متعدّد النطاقات من الملفّات المنفصلة
    vrt, idx = stac_vrt.build_band_vrt(paths)
    with rasterio.open(vrt) as src:
        assert src.count == 2, f"VRT يجب أن يكون نطاقين، حصلنا {src.count}"
    assert idx == {"red": 1, "nir": 2}, f"خريطة الفهارس خاطئة: {idx}"
    print(f"(أ) VRT بُني: bands={src.count} index_map={idx}")

    # (ب) النقطة end-to-end عبر HTTP
    os.environ.setdefault("DATABASE_URL", "postgresql://sahool_user@/sahool?host=/tmp/pgrun")
    os.environ["SAHOOL_AGENT_TOKEN"] = "stac-token"
    import main as svc
    from fastapi.testclient import TestClient

    field = "stac_bridge_field_42"
    c = TestClient(svc.app)
    r = c.post(
        f"/v1/fields/{field}/process-from-stac",
        json={
            "band_hrefs": paths,
            "indicator": "ndvi",
            "tenant_id": "33333333-3333-3333-3333-333333333333",
            "scene_id": "S2_STAC_TEST",
            "capture_datetime": "2026-06-07",
        },
        headers={"x-agent-token": "stac-token"},
    )
    assert r.status_code == 200, f"process-from-stac فشل: {r.status_code} {r.text[:200]}"
    job = r.json()["job_id"]
    js = c.get(f"/v1/jobs/{job}").json()
    print(f"(ب) job={job} status={js.get('status')} progress={js.get('progress_pct')}")
    assert js.get("status") == "completed", f"المهمّة لم تكتمل: {js.get('status')}"

    # (ج) قراءة الشبكة → NDVI حقيقي = (0.7-0.2)/(0.7+0.2) ≈ 0.556
    g = c.get(f"/v1/fields/{field}/indicator-grid?index=ndvi&grid=8").json()
    print(
        f"(ج) indicator-grid real_data={g.get('real_data')} source={g.get('source')} "
        f"ndvi_mean={round(g.get('stats', {}).get('mean', 0), 3)}"
    )
    assert g.get("real_data") is True, "يجب أن تكون القراءة حقيقيّة بعد المعالجة من STAC"
    assert abs(g["stats"]["mean"] - 0.556) < 0.02, f"NDVI غير متوقّع: {g['stats']['mean']}"
    print("✓ جسر STAC→VRT→معالجة→تخزين→قراءة يعمل end-to-end")


if __name__ == "__main__":
    run()
    print("ALL STAC-VRT ASSERTIONS PASSED")

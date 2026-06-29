# SAHOOL GIS Phase 4 — Cloud-native best practices implementation

تم تحويل أفكار المراجع الظاهرة في الصور إلى عقود قابلة للتنفيذ داخل المشروع:

- **farmOS / farmOS-map**: مراجعات هندسية كسجل append-only، جلسات تحرير، وأقفال تحرير لمنع التعارض.
- **TiTiler / Terracotta**: COG registry، MosaicJSON، واجهة STAC خفيفة، وسجل TileJSON/COG.
- **s2cloudless / Sentinel Hub cloud masks**: `scene_quality_score` قبل المعالجة لفرز المشاهد حسب الغيوم/الظلال/no-data.
- **GeoParquet**: مسار partition ثابت لتصدير الحقول إلى data lake.
- **OGC Testbed / OGC APIs**: descriptors أولية للـ collections وروابط items/tiles قابلة للتوسيع.

## الملفات الجديدة

- `shared/gis/cloud_native_gis.py`
- `services/raster-service/cloud_native_catalog.py`
- `migrations/v114_cloud_native_gis_best_practices.sql`
- `shared/gis/test_cloud_native_gis.py`
- `services/raster-service/test_cloud_native_catalog.py`

## endpoints الجديدة في raster-service

- `GET /stac`
- `GET /stac/collections`
- `POST /stac/mosaicjson`
- `POST /v1/scenes/quality-score`
- `POST /v1/cog/registry/preview`

هذه endpoints لا تكتب في قاعدة البيانات، لذلك آمنة كمرحلة أولى. الجداول موجودة في migration v97 لتفعيل التخزين لاحقاً عبر RLS.

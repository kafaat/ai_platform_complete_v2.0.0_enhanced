# قرار اتّجاه: ذكاء الحقل المتمحور حول الكائن (Field-Centric) — إلهام Agribound

> سجلّ اتّجاه معماريّ. لا فكرة بلا مصدر، ولا اقتباس بلا حالته الفعليّة في SAHOOL (file:line).
> الحالة: `proposed` — مراجعة وإلهام. آخر تحديث: 2026-06-23.

## المصدر (الإلهام)
- **Agribound** (`montimaj/agribound`): خطّ مفتوح لاستخراج **حدود الحقول** من صور الأقمار وإخراجها
  **GeoJSON/GeoPackage/GeoParquet** قابلة للتدقيق. المبدأ: «الحقل (Polygon) هو الوحدة الذرّيّة للذكاء
  الزراعي، لا البكسل/NDVI». خطّ متعدّد المحرّكات (SAM2/DINOv3/Prithvi/embeddings/ensemble) + تصفية
  غير-زراعيّ (LULC) + تنظيف طوبولوجي + تقييم (IoU/F1). يقترح المستخدم نقله كـ Blueprint لذكاء حقل في SAHOOL.

## أين يقف SAHOOL اليوم (مُتحقَّق — متقدّم جدّاً؛ معظم «الفجوات» موجود)
| طبقة مقترَحة | حالة SAHOOL | المصدر |
|---|---|---|
| استخراج آليّ للحدود | ✅ | خدمتا `field-segmentation`+`sam2-inference` · `api/field_boundary_pipeline.py` · `frontend/.../AutoSegmentControl.tsx` |
| Boundary Confidence | ✅ | `api/boundary_confidence.py` (+ `tests/test_boundary_confidence.py`) |
| Geometry QA / Topology | ✅ | `api/gis_kernel.py` · `geospatial_integrity.py` · `gis_geometry_guard.py` · `pivot_geometry.py` |
| Boundary Versioning | ✅ | `migrations/v96_spatial_geometry_integrity.sql` (سجلّ تنقيحات الهندسة) |
| Human-in-the-loop | ✅ | `FieldSplitMergeTool` · `DrawControl` · `AutoSegmentControl` · `FieldDetailDrawer` + دمج/قصّ ذرّيّ (#443) |
| Field Registry / CanonicalFieldState | ✅ | `field_state_projection` · `api/routers/boundaries.py` · `field_boundary_contracts.py` |
| استيراد GeoJSON/KML/GPS | ✅ | `api/geo_import.py` |
| **GeoParquet (تخزين/تحليل على نطاق)** | ⛔ **فجوة** | لا إنتاج/تخزين GeoParquet |
| **Field Embeddings (Prithvi/DINOv3/Clay)** | ⛔ **فجوة** (كبيرة) | نماذج أساس — غير مُنفَّذة |
| **Multi-engine Ensemble للحدود** | ⛔ **فجوة** | SAM2 محرّك واحد؛ لا تصويت/إجماع متعدّد |
| **تصفية غير-زراعيّ (LULC/Dynamic World)** | ⛔ جزئيّ/فجوة | لا تحقّق LULC قبل قبول المضلّع |

**الخلاصة (صدق):** SAHOOL **ليس متخلّفاً عن Agribound** — بل متمحور حول الحقل أصلاً (SAM2 + GIS kernel +
boundary_confidence + versioning v96 + human-review). التحليل يُقلّل قدره بوضوح. **لا نُعيد بناء ما هو قائم.**

## الفجوات الحقيقيّة والنافعة (بترتيب القيمة/الجدوى)
1. **تصدير/تخزين GeoParquet** — للتحليل على نطاق (10k+ حقل) + توافق DuckDB (يبني على ورشة SQL #451!).
   **الأكثر جدوى** (صغير نسبيّاً، يكمّل مسار GeoJSON القائم). يُوصى به أوّلاً.
2. **تصفية غير-زراعيّ (Agricultural Validity)** — تحقّق LULC/الميل/الغطاء قبل قبول حدود مُستخرَجة
   (يقلّل الإيجابيّات الكاذبة: طرق/مبانٍ/ظلال). يبني على boundary_confidence القائم.
3. **Field Embeddings (نماذج أساس جيومكانيّة)** — تمثيل لكلّ حقل (شكل/نسيج/NDVI/فينولوجيا) لإيجاد
   حقول مشابهة/نقل توصيات/كشف شذوذ. **كبير** (نماذج أساس + بنية تحتيّة) — رهان بعيد.
4. **Multi-engine Ensemble** — إضافة محرّكات حدود (Sentinel/Drone/SAM2) + تصويت/إجماع + ثقة مُجمَّعة.
   متوسّط-كبير؛ يبني على SAM2 + boundary_confidence القائمين.

## السبب
SAHOOL متمحور حول الحقل أصلاً؛ القيمة الحقيقيّة ليست إعادة البناء بل: **(1) GeoParquet** (يربط الحدود
بورشة SQL/DuckDB على نطاق) و**(2) تصفية الصلاحية الزراعيّة** (جودة الحدود). Embeddings/Ensemble رهانات
أكبر مؤجَّلة. **صدق:** لا ندّعي ensemble/foundation-models بينما المحرّك الحاليّ SAM2 (غير منشور — GPU، انظر
[`../gaps/registry.md`](../gaps/registry.md)).

## الخطوة التالية
موصى بها: **(1) تصدير/تخزين GeoParquet للحدود/الوصفات** (يكمّل GeoJSON + يربط ورشة SQL). تُخطَّط بمسارها.

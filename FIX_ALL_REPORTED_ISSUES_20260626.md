# إصلاح مشاكل الحقول/المرئيات/الأمان — 2026-06-26

## تم الإصلاح

1. **مقارنة توكن الخدمة بزمن ثابت**
   - الملف: `services/raster-service/main.py`
   - استبدال `x_agent_token != AGENT_TOKEN` بـ `hmac.compare_digest(...)`.

2. **حماية مسارات التخزين التشغيلية**
   - الملفات: `services/raster-service/main.py`
   - إضافة `X-Agent-Token` إلزامي إلى:
     - `GET /storage/stats`
     - `GET /offline/packs`
     - `GET /offline/packs/{pack_name}`

3. **إغلاق نافذة IDOR في طبقات الراستر بعد إعادة التشغيل**
   - الملفات:
     - `services/raster-service/main.py`
     - `services/raster-service/db_persist.py`
   - إضافة fallback من `raster_assets` عبر `layer_owner_tenant(layer_id)` عند غياب مالك الطبقة من الذاكرة.

4. **إضافة endpoint لقيمة البكسل/النقطة**
   - الملف: `services/raster-service/main.py`
   - endpoint جديد:
     - `GET /v1/fields/{field_id}/pixel?lat=&lon=&index=&date=`
   - يتحقق من ملكية الحقل، وجود COG حقيقي، حدود الطبقة، ويعيد القيمة أو `nodata` بصدق.

5. **Cloud mask لم يعد يتخطى بصمت**
   - الملف: `services/raster-service/main.py`
   - عند `apply_cloud_mask=True` وغياب SCL يتم تسجيل تحذير صريح.
   - عند توفر SCL يتم حساب `cloud_pct` وتسجيل `cloud_mask_applied`.

6. **تحسين قراءة البلاطات**
   - الملف: `services/raster-service/tile_render.py`
   - استبدال قراءة `src.read(1)` الكاملة بإعادة إسقاط مباشرة من `rasterio.band(src, 1)` إلى بلاطة 256×256، ليستفيد COG من القراءة الجزئية/الأهرامات.

7. **دفاع عميق في استعلامات الحقول الفردية**
   - الملف: `services/sahool-platform/api/routers/fields.py`
   - إضافة `AND tenant_id = $2::uuid` في قراءة تفاصيل الحقل وحذف الحقل، فوق RLS.

8. **اختبارات تحقق جديدة**
   - الملف: `tests_v9/test_raster_security_visual_fixes_20260626.py`
   - يغطي: توكن ثابت الزمن، حماية storage/offline، pixel endpoint، DB fallback للطبقات، windowed tile rendering، tenant filter، cloud mask warning.

## نتائج الاختبار

- الاختبارات الموجهة للإصلاحات والحقول/الراستر:
  - `38 passed, 2 skipped`
- الاختبار الكامل `pytest -q` بدأ وجمع `2270` اختباراً، واستمر حتى منتصف المجموعة دون فشل ظاهر، لكنه انتهى بمهلة بيئة التنفيذ قبل الإكمال.

## ملاحظات بقيت كتحسينات غير كاسرة

- دعم MultiPolygon الكامل ما زال يتطلب قرار API/UX: قبول MultiPolygon أو رفضه برسالة واضحة.
- إزالة تكرار GiST في الترحيلات تحتاج ترحيل تنظيف آمن على قواعد الإنتاج بعد التحقق من أسماء الفهارس الفعلية.
- فرض MFA في الإنتاج يعتمد على إعدادات النشر `SAHOOL_ENV=production` أو `ENFORCE_SENSITIVE_MFA=true`.

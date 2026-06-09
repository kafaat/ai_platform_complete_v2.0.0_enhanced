# إغلاق فجوات المزوّدين/الأدوات + تحقّق الأتمتة

نُفّذت كلّ الفجوات من تقرير المزوّدين، وتُحقّق من أساليب أتمتة الطقس والصور
مقابل أفضل الممارسات.

## ✅ الفجوات المُغلقة

### ١. خرائط offline للموبايل (الأولويّة العليا — بيئة اليمن)
- pubspec: أُضيفت flutter_map_mbtiles + flutter_map_pmtiles + mbtiles + path_provider
- widget: offline_field_map.dart — خريطة تستخدم MBTiles (SQLite، offline) كأساس
  مع بلاطات الشبكة fallback؛ مؤشّر مصدر شفّاف (محفوظة/شبكة)؛ fail-safe (فشل
  offline → شبكة، لا تعطّل)
- خادم: endpoints /offline/packs (سرد) + /offline/packs/{name} (تنزيل) + حماية
  path traversal
- script: generate_mbtiles.sh (قالب توليد حزمة لمنطقة كالجوف)

### ٢. أداة ترحيل بتتبّع وتراجع (Alembic-style، بلا تبعيّات)
- scripts_v9/migrate.py: جدول schema_migrations (نسخة + checksum + وقت) +
  up (تطبيق المعلّق) + down (تراجع) + status + كشف انجراف checksum
- ملفّات تراجع: v9_rls_tenant_isolation.down.sql + v9_append_only_enforcement.down.sql
- صدق: يرفض التراجع بلا .down.sql صريح (خطر فقد بيانات)؛ يُبلّغ بصدق بلا DATABASE_URL

## ✅ تحسين أتمتة الطقس (أفضل ممارسة)
- connector: fetch_current_batch — يجلب عدّة إحداثيّات في طلب واحد (Open-Meteo
  يدعم إحداثيّات مفصولة بفواصل). يقلّل الطلبات ويخفّف ضغط rate limit.

## ✅ تحقّق أساليب الأتمتة (مطابقة للمعايير — لا تغيير مطلوب)
### أتمتة الطقس
- المصدر: Open-Meteo (مجّاني، بلا مفتاح، الأفضل لغير التجاري) ✓
- cache بـTTL (3600ث) يقلّل الاستدعاء — أفضل ممارسة معياريّة ✓
- backoff تصاعدي عند الفشل (سقف ساعة) + عزل المهامّ ✓
- ⚠ ملاحظة ترخيص: Open-Meteo للاستخدام التجاري يحتاج اشتراكاً — راجع عند التوسّع

### أتمتة جلب الصور
- STAC search بفلتر الغيوم (eo:cloud_cover) — مطابق للمعيار ✓
- deduplication: TrackedField.last_image_id يمنع إعادة معالجة نفس المشهد ✓
- جلب تزايدي (lookback window) + عزل خطأ لكلّ حقل ✓
- استمرار الحالة (لا إعادة معالجة بعد إعادة التشغيل) ✓
- provenance (scene_id + capture_datetime) لإعادة الإنتاج ✓

هذه الأساليب تطابق أفضل الممارسات (STAC filtering, incremental fetch, dedup,
scheduled automation) — لا تغيير مطلوب.

## التحقّق
- 415/415 roadmap (+7) · 0 خطأ ترجمة · offline 34/0 · لا كسر

## ملاحظة صدق
- حزم Flutter (mbtiles/pmtiles) تحتاج flutter pub get على جهازك؛ أسماء الحزم
  ونسخها معياريّة. التشغيل الفعلي يحتاج بناء Flutter.
- migrate.py + generate_mbtiles.sh يحتاجان psql/gdal على جهازك — اختبرتُ المنطق
  (الترتيب، التتبّع، التحقّق) وبنية الأوامر؛ التطبيق الحيّ على postgres.
- توليد MBTiles فعليّاً يحتاج مصدر بلاطات + gdal — وفّرتُ القالب والتوجيه، لم
  أزيّف توليداً يحتاج بنية تحتيّة.

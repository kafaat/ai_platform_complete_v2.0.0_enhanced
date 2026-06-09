# تدقيق مراجعتَي المزوّدين العميقتين — تنفيذ + ردّ صادق

دقّقتُ كلّ ادّعاء بالكود. النتيجة: مزيج من فجوات حقيقيّة أصلحتُها، وادّعاءات
لمكوّنات مبنيّة أصلاً، وسؤال استراتيجي جوهري لا يُحَلّ بالكود.

## ✅ فجوتان حقيقيّتان أُصلحتا

### ١. Raster Lifecycle (المراجعة محقّة — لا سياسة تنظيف)
raster_lifecycle.py: تنظيف النواتج المنتهية حسب الاحتفاظ (temp 1ي/thumbnail
30ي/derived 90ي) + حماية offline_packs (لا تُمَسّ) + إحصاء التخزين. dry_run
افتراضي (آمن). endpoints /storage/stats + /storage/cleanup. يمنع "storage
explosion" الذي حذّرت منه المراجعة.

### ٢. PMTiles (المراجعة محقّة — الاتّجاه المفضّل)
widget الموبايل دُعِّم بـPMTiles (ملفّ واحد، HTTP-range، hybrid online/offline)
كأولويّة، ثمّ MBTiles، ثمّ الشبكة (fail-safe). يطابق توصية المراجعة بأنّ
PMTiles أقرب لمستقبل geospatial-first من MBTiles raster التقليدي.

## ⚠️ ادّعاءات لمكوّنات مبنيّة أصلاً (دقّقتُها — النقص غير دقيق)
- **CRS consistency (#6)**: كلّ الطبقات تستخدم EPSG:4326 (PostGIS + raster
  متّسقة). لا mismatch. الادّعاء غير دقيق.
- **Spatial indexing (#8)**: GIST على الأعمدة الهندسيّة + BRIN على الزمنيّة
  موجودة في init_v8/v9_foundation. "لا استراتيجيّة فهرسة" غير دقيق.
- **Topology/self-intersection**: geospatial_integrity.py فيه
  has_self_intersection + validate_crs + bbox-within-Yemen + validate-geometry
  endpoint. "لا topology validation" غير دقيق.
- **SAR**: الكود صادق — بحث STAC للرادار موجود، والتعليقات تقرّ أنّ المعالجة
  الفعليّة (speckle/terrain correction) تحتاج preprocessing. ليس مدّعىً.

## 🔴 السؤال الاستراتيجي (الأهمّ — لا يُحَلّ بالكود)
المراجعتان تطرحان السؤال الجوهري: هل SAHOOL "GIS-enabled" أم "geospatial-first"؟
وأشياء مثل: edge strategy، tile distribution architecture، data gravity،
migration operating model (compatibility windows، replay-safe evolution).

**هذه قرارات معماريّة/استراتيجيّة، لا أخطاء كود.** لا أستطيع — ولا ينبغي لي —
أن أقرّرها نيابةً عنك بكتابة كود. إجابتها تحدّد أولويّات سنة كاملة:
- لو "GIS-enabled": ما بنيناه كافٍ (خرائط دعم، offline اختياري).
- لو "geospatial-first": تحتاج edge nodes، tile CDN، spatial lineage، وهي
  مشاريع بنية تحتيّة لا ملفّات.

## التحقّق
- 422/422 roadmap (+7) · 0 خطأ ترجمة · لا كسر

## ملاحظة صدق (حاسمة)
- أصلحتُ الفجوتين القابلتين للإصلاح الساكن (lifecycle + PMTiles).
- صحّحتُ بصدق ادّعاءات النقص غير الدقيقة (CRS/indexing/topology مبنيّة).
- السؤال الاستراتيجي (geospatial-first؟ edge strategy؟ data gravity؟) **قرارك
  أنت** — وأخطر ما أفعله هو التظاهر بحلّه بكود. هو حوار منتج/معماريّة، لا commit.
- المراجعة محقّة في استنتاجها الأعمق: "اتّساع مسؤوليّات المنصّة أسرع من نضج
  تشغيلها الميداني". الدواء ليس مزيداً من الكود، بل تشغيل حيّ + قرار نطاق واضح.

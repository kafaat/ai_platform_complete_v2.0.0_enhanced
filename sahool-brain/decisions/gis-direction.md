# قرار اتّجاه: GIS في المتصفّح (Browser-native) — إلهام GeoLibre

> سجلّ اتّجاه معماريّ. لا فكرة بلا مصدر، ولا اقتباس بلا حالته الفعليّة في SAHOOL (file:line / #PR).
> الحالة: `proposed` — بانتظار اختيار المستخدم للخطوة الأولى. آخر تحديث: 2026-06-23.

## المصادر (الإلهام)
- **GeoLibre** — `opengeos/GeoLibre` (https://github.com/opengeos/GeoLibre): منصّة GIS خفيفة في
  المتصفّح (MapLibre GL + deck.gl + DuckDB-WASM Spatial + Turf.js + Pyodide + Tauri). الفلسفة:
  «البيانات محليّة · المعالجة في المتصفّح · الخادم أخفّ · الخصوصيّة أعلى».
- **claude-obsidian** — `AgriciDaniel/claude-obsidian` + نمط Karpathy «LLM Wiki»: قاعدة معرفة
  يصونها الوكيل — جُسِّدت في هذا الـbrain ([`../README.md`](../README.md)).

## أين يقف SAHOOL اليوم (مُسنَد)
| فكرة GeoLibre | الحالة | المصدر |
|---|---|---|
| MapLibre GL (2D/3D) | ✅ خلف flag | `frontend/src/lib/featureFlags.ts:61` · PR #434 |
| Turf client-side (union/intersect/difference) | ✅ مُستعمل | `frontend/src/lib/fieldGeometryOps.ts` (FieldSplitMergeTool) |
| استيراد GeoJSON/KML/GPS | ✅ جزئيّ | `services/sahool-platform/api/geo_import.py` |
| دمج/قصّ مكانيّ ذرّيّ | ✅ خادميّ | PR #443 → [`../gaps/registry.md`](../gaps/registry.md) |
| بوّابة QA لـWebGL | ✅ Playwright | PR #441 |
| deck.gl · DuckDB-WASM Spatial · Plugin system · حفظ مساحة العمل · SQL Workspace · AI GIS Assistant | ⛔ غير موجود | فرص النقل |

## الاتّجاه المقترَح (اقتباس تدريجيّ — لا «غلي المحيط»)
1. **حفظ مساحة العمل (`.sahool-project.json`)** — ✅ **منفَّذ:** تصدير/استيراد ملفّ (#449،
   [`../../frontend/src/lib/projectFile.ts`](../../frontend/src/lib/projectFile.ts)) + **استرجاع
   تلقائيّ** عبر localStorage (#450،
   [`../../frontend/src/lib/workspaceStorage.ts`](../../frontend/src/lib/workspaceStorage.ts)):
   إعدادات MapHub (الأساس/المؤشّر/الشفافية/المقارنة/الأدوات/التراكبات) عميل-فقط. مؤجَّل لـv2:
   مركز/تكبير الخريطة + الرسومات (تحتاج تحكّم خريطة).
2. **محرّك SQL في المتصفّح (DuckDB-WASM)** — ✅ **منفَّذ v1 (#451):** قسم «ورشة SQL» (lazy)
   يحمّل الحقول إلى جدول `fields` ويستعلمها محليّاً
   ([`../../frontend/src/services/duckdb.ts`](../../frontend/src/services/duckdb.ts) +
   [`../../frontend/src/components/sql/SQLEditor.tsx`](../../frontend/src/components/sql/SQLEditor.tsx)).
   عميل-فقط، مستضاف ذاتيّاً، كسول (لا يمسّ الحزمة الرئيسة) + **تصدير النتائج CSV** (#452). **مؤجَّل لـv2:** spatial extension
   (`ST_Area`/`ST_Intersects` — يُحمَّل من extensions.duckdb.org، يحتاج تجميعاً أوفلاين) + المؤشّرات
   (NDVI async لكلّ حقل) + ربط النتائج بإبراز الخريطة.
3. **نظام إضافات (Plugin) + AI GIS Assistant** (لغة طبيعيّة → Spatial SQL → تحديث الخريطة) —
   معماريّ، يعتمد على (2)، ويتوافق مع مستشار SAHOOL (`/api/agent/query`).

## السبب (لِمَ هذا الاتّجاه)
SAHOOL متوافق أصلاً مع فلسفة browser-native (MapLibre + Turf مُستعملان)، فالاقتباس **تطوّريّ لا
ثوريّ**: يقلّل حمل/كلفة الخادم، يرفع الخصوصيّة، ويُمكّن باحثي/جهات الحكومة عبر SQL مكانيّ. البدء
بالفكرة (1) لأنّها مكتفية ذاتيّاً ولا تتطلّب تبعيّات WASM ثقيلة.

## الخطوة التالية
عند اختيار الخطوة الأولى → تُنقَل إلى [`../gaps/registry.md`](../gaps/registry.md) كبند مفتوح
بمصدر، وتُخطَّط بمسارها (plan mode).

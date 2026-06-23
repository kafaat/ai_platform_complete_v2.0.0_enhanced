# قرار اتّجاه: GIS في المتصفّح (Browser-native) — إلهام GeoLibre

> سجلّ اتّجاه معماريّ. لا فكرة بلا مصدر، ولا اقتباس بلا حالته الفعليّة في SAHOOL (file:line / #PR).
> الحالة: **الأفكار 1-4 منفَّذة v1** (#449-#454). آخر تحديث: 2026-06-23. التحسينات المؤجَّلة موسومة أدناه.

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
   إعدادات MapHub (الأساس/المؤشّر/الشفافية/المقارنة/الأدوات/التراكبات) عميل-فقط + **v2 (#453):**
   التقاط/استعادة **مركز+تكبير الخريطة** عبر المحرّكين (Leaflet `HubMap` + MapLibre `HubMapGL`، بمنع
   حلقة moveend↔restore وحفظ auto-fit). مؤجَّل: الرسومات (سريعة الزوال).
2. **محرّك SQL في المتصفّح (DuckDB-WASM)** — ✅ **منفَّذ v1 (#451):** قسم «ورشة SQL» (lazy)
   يحمّل الحقول إلى جدول `fields` ويستعلمها محليّاً
   ([`../../frontend/src/services/duckdb.ts`](../../frontend/src/services/duckdb.ts) +
   [`../../frontend/src/components/sql/SQLEditor.tsx`](../../frontend/src/components/sql/SQLEditor.tsx)).
   عميل-فقط، مستضاف ذاتيّاً، كسول (لا يمسّ الحزمة الرئيسة) + تصدير CSV (#452) + **v2 UX (#453):** سجلّ
   استعلامات (localStorage) + أمثلة جاهزة + نسخ JSON. **مؤجَّل:** spatial extension
   (`ST_Area`/`ST_Intersects` — يُحمَّل من extensions.duckdb.org، يحتاج تجميعاً أوفلاين) + المؤشّرات
   (NDVI async لكلّ حقل) + ربط النتائج بإبراز الخريطة.
3. **استوديو الهندسة المكانيّة (Field GIS Studio)** — ✅ **منفَّذ v1 (#453):** قسم «أدوات الهندسة»
   يطبّق Turf (`buffer`/`simplify`) على هندسة الحقل **معاينةً** (مساحة/رؤوس قبل/بعد، عميل-فقط، لا حفظ
   خادميّ) — [`../../frontend/src/sections/GisToolsPage.tsx`](../../frontend/src/sections/GisToolsPage.tsx)
   + [`fieldGeometryOps.ts`](../../frontend/src/lib/fieldGeometryOps.ts). مؤجَّل: dissolve/clip + الحفظ.
4. **AI GIS Assistant (NL → SQL)** — ✅ **منفَّذ v1 (#454):** صندوق «اسأل بالعربيّة» في ورشة SQL →
   نقطة خادميّة `POST /api/v1/nl-sql` تستدعي Claude (المفتاح خادميّ) لترجمة السؤال إلى SELECT للقراءة
   فقط → يملأ المحرّر للمراجعة → يُنفَّذ في DuckDB العميل. الخادم:
   [`api/routers/nl_sql.py`](../../services/sahool-platform/api/routers/nl_sql.py) +
   [`api/nl_sql_validate.py`](../../services/sahool-platform/api/nl_sql_validate.py) (تحقّق نقيّ).
   صدق: خصوصيّة (السؤال فقط يُرسَل) · آمن (SELECT مُتحقَّق + sandbox العميل + إنسان-في-الحلقة) ·
   مُغلَق بـ`FEATURE_NATURAL_LANGUAGE_GIS`+`ANTHROPIC_API_KEY` (honest-503 بلا مفتاح). النموذج
   `claude-opus-4-8` (قابل للضبط بـ`NL_SQL_MODEL`). **مؤجَّل:** ربط النتائج بإبراز الخريطة + نظام إضافات.

## السبب (لِمَ هذا الاتّجاه)
SAHOOL متوافق أصلاً مع فلسفة browser-native (MapLibre + Turf مُستعملان)، فالاقتباس **تطوّريّ لا
ثوريّ**: يقلّل حمل/كلفة الخادم، يرفع الخصوصيّة، ويُمكّن باحثي/جهات الحكومة عبر SQL مكانيّ. البدء
بالفكرة (1) لأنّها مكتفية ذاتيّاً ولا تتطلّب تبعيّات WASM ثقيلة.

## الخطوة التالية
عند اختيار الخطوة الأولى → تُنقَل إلى [`../gaps/registry.md`](../gaps/registry.md) كبند مفتوح
بمصدر، وتُخطَّط بمسارها (plan mode).

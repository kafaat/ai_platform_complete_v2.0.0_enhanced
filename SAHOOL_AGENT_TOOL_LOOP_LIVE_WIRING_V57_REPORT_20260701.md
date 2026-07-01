# SAHOOL v57 — Agent Tool Calling Loop Live Wiring

## الهدف
وصل حلقة أدوات الوكيل المنفذة في v56 بمسار المحادثة الحي داخل `ai_agronomist` بدل بقائها بنية منفصلة. القرار المعماري محفوظ: النموذج يقرر طلب الأدوات، والـHarness ينفّذ فقط ضمن الأدوات/المعرفة/المراقبة/الصلاحيات/التدقيق.

## ما تغير

### Backend — `services/ai_agronomist/main.py`
- أضيف حقل اختياري إلى `AdvisorQuery`:
  - `tool_calls: list[dict[str, Any]] | None`
- تم استدعاء `tool_loop.run_tool_calls(...)` داخل `_build_evidence_response`.
- القدرات تأتي من سياسة المستأجر بعد `normalize_policy(...)`، وليس من الطلب مباشرة.
- أضيف جالب قراءة محلي `_build_agent_tool_fetcher(...)` يستند إلى:
  - `CanonicalFieldState`
  - `AI Context Pack`
  - `imagery_timeline`
  - `weather_history`
  - `alerts_context`
  - `drawing_context`
- أضيفت نتائج الأدوات إلى الاستجابة:
  - `tool_calls`
  - `pending_approvals`
  - `tool_calls_truncated`
- أضيفت النتائج إلى `harness_transparency` حتى تظهر للواجهة بصدق.

## سلوك الحوكمة
- أداة قراءة مع قدرة ممنوحة: تنفذ من السياق المتاح.
- أداة مجهولة: `denied`.
- أداة بلا قدرة: `denied`.
- أداة معدّلة أو عالية الأثر: `pending_approval` ولا تنفذ داخل chat.
- سقف الأدوات يبقى 8 لمنع حلقات لا نهائية.
- لا يتم إرسال أوامر ري/رش/توصيات نهائية دون موافقة بشرية.

## أدوات القراءة التي أصبحت موصولة بسياق الحقل
- `get_field_state`
- `get_truecolor_scene`
- `get_index_timeline`
- `get_weather_history`
- `get_operation_windows`
- `get_alerts`
- `get_drawings_and_zones`
- `open_map_layer`

## قرار MapHub
لم يتم تغيير قرار الواجهة:
- `MapHub default = truecolor raw Sentinel-2 imagery`
- `weather` لا يفتح إلا صراحة.
- `NDVI/NDMI` طبقات تفسيرية اختيارية.

## التحقق

### Backend
```bash
PYTHONPATH=. python3 -m pytest -q \
  tests_v9/test_ai_tool_loop_chat_integration_v57.py \
  tests_v9/test_ai_tool_loop_v56.py \
  tests_v9/test_ai_tool_executor_v55.py

python3 -m compileall -q \
  services/sahool-platform/api \
  services/sahool-platform/core \
  services/ai_agronomist \
  tools
```
النتيجة: 22 اختباراً ناجحاً + compile guard ناجح.

### Frontend
```bash
cd frontend
npm test -- src/sections/MapHubTrueColorRuntime.v54.static.test.ts src/sections/MapHubSatelliteDefault.static.test.ts
npm run typecheck
npm run build
```
النتيجة: 7 اختبارات ناجحة + typecheck ناجح + build ناجح. بقي تحذير Vite السابق عن `LeafletDrawAdapter` فقط.

## حدود التنفيذ
لم أجر اتصال live بمزود LLM أو raster-service. هذا الإصلاح يثبت عقد حلقة الأدوات في runtime ويمنع الأفعال غير المصرح بها. الاختبار الحي التالي يجب أن يحاكي/يشغل طلب chat يحتوي `tool_calls` ويراقب الـharness الناتج.

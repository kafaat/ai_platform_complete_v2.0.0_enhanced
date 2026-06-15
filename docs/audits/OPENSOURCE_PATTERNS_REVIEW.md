# مراجعة استلهام المشاريع المفتوحة — تحقّق وبناء

المرفق قائمة مشاريع للاستلهام (LangGraph/Temporal/FarmOS/OpenHands/Haystack/
OpenDroneMap/Airbyte/Superset/QGIS/Ollama). وفق المبدأ: استلهام النمط لا نسخ
المشروع؛ التحقّق من كلّ فكرة مقابل الكود، والبناء للفجوة الحقيقيّة فقط.

## التحقّق: معظم الأفكار موجودة فعلاً
| الفكرة (المصدر) | الحالة في SAHOOL |
|----------------|------------------|
| Agent orchestration (OpenHands) | ✅ supervisor-agent (router + skills + mcp_client) |
| Retrieval/RAG (Haystack) | ✅ local-ai-rag + qdrant-seed |
| Farm records (FarmOS) | ✅ farm_ledger + field_operational_state + activities |
| Drone imagery (OpenDroneMap) | ✅ /upload/drone في raster |
| Connectors/ingestion (Airbyte) | ✅ providers متعدّدون (soil/weather/market/ERP) |
| Edge AI offline (Ollama) | ✅ edge-inference (pest_detector + yield + sync) |
| Event sourcing/replay (Temporal) | ✅ event_bus (outbox) + event_replay + command_store |
| State machine (LangGraph) | ✅ field_lifecycle (انتقالات صالحة) |

## الفجوة الحقيقيّة الوحيدة: محرّك workflow متعدّد الخطوات قابل للاستئناف
النظام يملك state machine + exactly-once، **لكن لا محرّك يحفظ تقدّم workflow
متعدّد الخطوات ليُستأنف من حيث توقّف** عند الفشل/إعادة التشغيل — جوهر
LangGraph/Temporal. تأكّد: لا step_index/completed_steps/resume في أيّ مكان.

الأثر العملي الزراعي: تدفّقات مثل تصعيد الآفة (رصد→تأكيد→توصية→موافقة→تنفيذ→
متابعة) أو حلقة قرار الريّ — إن انقطع النظام في المنتصف، تبدأ من الصفر أو
تضيع، وقد تتكرّر خطوات ذات أثر جانبي (تنبيه مُرسَل مرّتين، تكلفة مدفوعة مرّتين).

## ما بُني: core/workflow_engine.py (+ migration v16)
محرّك durable خفيف نقيّ-بايثون (لا Temporal كامل، لا broker — استلهام النمط):
- **استئناف**: يحفظ completed_steps + step_results فور نجاح كلّ خطوة؛ إعادة
  التشغيل تتخطّى المكتمل (لا إعادة تنفيذ ذي أثر جانبي).
- **تعليق**: suspends=True يوقف الـworkflow بانتظار حدث خارجي (موافقة بشريّة)
  ثمّ يُستأنف.
- **صدق**: الخطوة الفاشلة تُعلَن (status=FAILED + error)، يتوقّف قابلاً
  للاستئناف — لا تخطّي صامت، لا نجاح زائف.
- **store قابل للحقن**: InMemory (تطوير) + migration v16 لجدول workflow_state
  (DB، RLS مُطبَّق) للإنتاج.

## التحقّق (مُختبَر حيّاً)
- 691/691 roadmap (+6) · 0 خطأ (419 ملفّ)
- تشغيل كامل ✓ · فشل+استئناف بلا إعادة تنفيذ ✓ · تعليق للموافقة ✓ · migration RLS ✓

## ما لم أبنِه (صدق)
- **Temporal/LangGraph كاملاً**: لا — تبعيّة ثقيلة (broker/خادم) تخالف بنية
  SAHOOL الحاليّة. استلهمتُ النمط (durable resumable) بمحرّك خفيف مناسب.
- **FarmOS/ODM/Superset features**: موجودة بشكل ما؛ لا نسخ ميزات لمجرّد ذكرها.
- **PostgresWorkflowStore الفعلي**: المحرّك store-agnostic؛ migration v16 جاهز،
  لكن ربط asyncpg store الحيّ يُكتب على بيئة التشغيل (نفس نمط command_store).

## ملاحظة صدق
استلهمتُ النمط الأهمّ (durable resumable workflow) وبنيتُه خفيفاً مناسباً لـ
SAHOOL — لا نسخ Temporal. المحرّك مُختبَر حيّاً (استئناف، عدم إعادة تنفيذ،
تعليق). الحدّ المعلَن: الـInMemoryStore للتطوير (يُفقَد عند إعادة التشغيل)؛
الحفظ المعمّر الحقيقي يحتاج PostgresWorkflowStore (migration v16 جاهز،
الـasyncpg store يُكتب على جهازك). دمج المحرّك في تدفّق زراعي فعلي (تصعيد آفة)
خطوة تالية — المحرّك جاهز ومُختبَر كبنية.

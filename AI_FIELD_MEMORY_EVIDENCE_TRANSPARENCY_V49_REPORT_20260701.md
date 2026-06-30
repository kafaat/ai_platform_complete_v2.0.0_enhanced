# v49 — AI Field Memory Evidence Transparency

## الهدف
تحسين شاشة المستشار الذكي ومسار `services/ai_agronomist` بحيث لا يكتفي بتمرير `ai_context_pack` خاماً، بل يستخدمه فعلياً في التأريض ويعرض للمستخدم مصادر الأدلة التي بُنيت عليها الإجابة.

## التغييرات الخادمية
- تحديث `services/ai_agronomist/main.py`:
  - استخراج `current_field_state.ai_context_pack` بشكل صريح.
  - تضمين ذاكرة الحقل لسنتين داخل نص التأريض المرسل للمولّد المحلي/الخارجي.
  - توليد معرفات أدلة من ذاكرة الحقل: imagery/weather/events/drawings/alerts/saved-advice.
  - إرجاع `evidence_sources` كبطاقات مصدر آمنة للواجهة.
  - إرجاع `ai_context_pack_readiness` لكي تظهر تحذيرات الجاهزية في الشات.
  - تحسين الثقة المركّبة عند توفر صور تاريخية وطقس تاريخي موثوقين.

## التغييرات في الواجهة
- تحديث `frontend/src/sections/ChatbotPage.tsx`:
  - عرض مصادر الأدلة كـ chips منفصلة عن نص الإجابة.
  - عرض `confidence`، و`mode`، واسم المزوّد/النموذج عند وجود توليد.
  - عرض تحذيرات جاهزية سياق الحقل مثل الحاجة إلى backfill سنتين.
  - إزالة دمج الأدلة داخل نص الإجابة، حتى يبقى النص نظيفاً والمصادر ظاهرة UI.

## الاختبارات المضافة
- `services/ai_agronomist/test_ai_field_memory_v49.py`
- `frontend/src/sections/ChatbotAiEvidenceTransparency.static.test.ts`

## التحقق المنفذ
- `PYTHONPATH=. python3 -m pytest -q services/ai_agronomist/test_ai_field_memory_v49.py` → 3 passed
- `npm test -- src/sections/ChatbotAiContextPack.static.test.ts src/sections/ChatbotPage.endpoint.test.ts src/sections/ChatbotAiEvidenceTransparency.static.test.ts` → 3 files / 7 tests passed
- `npm run typecheck` → passed
- `npm run build` → passed
- `python3 -m compileall -q services/sahool-platform/api services/sahool-platform/core services/ai_agronomist` → passed

## ملاحظة
لم يتم تشغيل مزوّد LLM خارجي live. هذه المرحلة تربط الذاكرة والأدلة وتعرضها، وتحافظ على السقوط الآمن إلى evidence-only عند غياب المولّد أو مفاتيحه.

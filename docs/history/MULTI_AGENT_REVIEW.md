# مراجعة متعدّدة المسارات + إصلاحات على النسخة المرفوعة

نُفّذت كخمسة مسارات فحص متخصّصة متسلسلة (لا وكلاء متوازين فعليّين — جلسة
واحدة منظّمة بصدق).

## وكيل ١: الأمان — مسح كلّ نقاط الكتابة
فحص 12 خدمة. النتيجة:
- محميّة مسبقاً: actuator, guardrails, odoo, auth, supervisor, tts, video (إصلاحات سابقة)
- **فجوات جديدة وُجدت وأُصلحت** (نقاط كتابة تُغيّر الحالة بلا مصادقة):
  - soil-service /soil/ingest → أُضيف توكن خدمة (منع حقن بيانات مستشعرات)
  - local-ai-rag /ingest → أُضيف توكن خدمة (منع تسميم قاعدة المعرفة RAG)
  - raster-service /upload/raster + /upload/drone → أُضيف توكن خدمة (منع
    إساءة التخزين/الحقن)
- مقبولة بلا مصادقة (تحليليّة، خلف عزل الشبكة): inference, /process,
  /query, /recommend, /imagery/search
- كلّ الحرّاس بفشل آمن: لو SAHOOL_AGENT_TOKEN غير مضبوط → 503 (لا يقبل تزويراً)

## وكيل ٢: جودة الكود — F401
وجد 25 استيراداً غير مستخدم عبر 11 خدمة. أُزيلت كلّها (نسخة احتياطيّة +
تحقّق ترجمة بعد كلّ إزالة). F401 في الخدمات = 0.

## وكيل ٣: الاتّساق — متغيّرات البيئة (كود vs compose)
النمط الذي سبّب أعطالاً حقيقيّة. النتيجة:
- raster-service: الحارس الجديد يحتاج SAHOOL_AGENT_TOKEN → أُضيف لـcompose
- local-ai-rag: SAHOOL_AGENT_TOKEN → أُضيف لـcompose
- video-processor + soil-service: معلّقان في compose (لا أثر حيّ؛ عند
  تفعيلهما يجب إضافة JWT_SECRET/AGENT_TOKEN حينها)
- auth/guardrails/supervisor: JWT_SECRET ممرّر فعلاً ✓

## وكيل ٤: الصحّة الهيكليّة
- py_compile: 329 ملفّ · صفر خطأ
- F821: صفر undefined names
- compose YAML: سليم (31 خدمة)
- الاختبارات: 304/304 · 9/9 e2e · 6/6 CERTIFIED

## وكيل ٥: الدمج (حافظ على إصلاحات Claude Code)
حُوفظ على إصلاحات جهازك (supervisor /health، منافذ 127.0.0.1، DB_PASSWORD،
odoo:8126، BOM) أثناء تطبيق الإصلاحات الأمنيّة والأتمتة.

## ملخّص ما طُبّق على النسخة المرفوعة
1. كلّ الإصلاحات الأمنيّة السابقة (actuator/guardrails/odoo/bot B5/register/RLS)
2. إصلاحات أمنيّة جديدة (soil/rag/raster ingest+upload)
3. imagery_automation + migrations (أتمتة + RLS persistence)
4. raster-service في compose + volume + token
5. تنظيف 25 استيراداً غير مستخدم
6. اختبارات محدّثة (304/304)

## ملاحظة صدق (الحدود)
- لم أشغّل Docker/PostgreSQL — كلّ التحقّق بنيويّ (ترجمة، YAML، F821/F401،
  منطق المصادقة، تطابق المتغيّرات). التشغيل الحيّ على جهازك.
- soil + video معلّقان في compose — حرّاسهما جاهزة لكن تحتاج إضافة
  التوكنات لـenv عند إلغاء التعليق.
- F401 نُظّف في الخدمات؛ قد تبقى حالات في api/ المنصّة (نُظّفت سابقاً).
- لم أشغّل ruff (غير متاح بيئيّاً) — استخدمت فاحص AST مكافئ.

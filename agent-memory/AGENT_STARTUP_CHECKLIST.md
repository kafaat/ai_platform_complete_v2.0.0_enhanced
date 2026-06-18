# قائمة بدء الوكيل — إجباريّة قبل أيّ كود (AGENT_STARTUP_CHECKLIST.md)

> أيّ وكيل تنفيذ/فحص **يجب** أن يُكمِل هذه الخطوات **قبل كتابة أيّ كود**.

## الخطوة 1 — اقرأ الذاكرة (بالترتيب)
1. `agent-memory/MEMORY.md`
2. `agent-memory/FACTS.md`
3. `agent-memory/CORRECTIONS.md`
4. `agent-memory/SCHEMA_FACTS.md`
5. `agent-memory/TEST_FACTS.md`
6. آخر ~20 سطراً من `agent-memory/JOURNAL.jsonl`

## الخطوة 2 — أقرّ بالقيود (اكتبها صراحةً)
> «فهمت القيود التالية قبل أن أكتب أيّ كود:»
- لا SQLAlchemy — asyncpg فقط (`ANY($1::text[])`, `CAST($1 AS jsonb)`).
- مواضيع NATS ببادئة `sahool.` فقط.
- لا postgres superuser في الخدمات — `sahool_app`/`sahool_jobs`.
- المكانيّ عبر `fields.geom` — لا `boundary`، و`field_id` نصّ لا UUID.
- لا منفذ `8084`/`8210` ولا خدمة `weather-map-api` في هذا المستودع (انحراف v05).
- هجرة الطقس = `v74_weather_intelligence.sql`؛ لا ترقيم `002`.
- Flutter في `mobile/sahool_app/`.
- `ruff==0.15.8` مثبّتة؛ افحص `pip-audit` قبل أيّ requirement حرج.

## الخطوة 3 — اكتشف قبل الافتراض
- إن لمست المخطّط: اقرأ ملفّ الهجرة المعنيّ. لم تجد العمود/الجدول؟ **توقّف وأبلِغ — لا تخترع.**
- إن «تحتاج خدمة جديدة»: أثبِت غيابها من `docker-compose.v9.yml` والكود أوّلاً.

## الخطوة 4 — نفّذ ثمّ تحقّق
- النواة النقيّة في `services/sahool-platform/core/` (بلا I/O/numpy، docstrings عربيّة، frozen dataclasses).
- شغّل: ملفّاتك + `pytest -m unit` + (لنواة المنصّة) `cd services/sahool-platform && PYTHONPATH=. pytest tests` + `ruff check`/`format --check`.
- حوّل كلّ ثابت معماريّ جديد إلى حارس CI ثابت.

## الخطوة 5 — حدّث الذاكرة
- خطأ تكرّر؟ ⇐ قاعدة في `CORRECTIONS.md`.
- حقيقة مخطّط/معماريّة جديدة مُتحقَّقة؟ ⇐ `FACTS.md`/`SCHEMA_FACTS.md`.
- أضِف سطر JSON واحداً إلى `JOURNAL.jsonl` يصف ما فُعِل/اكتُشِف.

# SAHOOL — خطّة ما بعد التشغيل (Post-Deployment Roadmap)

خطّة **مؤجَّلة** للبنود التي لا تُنفَّذ في الكود الآن، بل **بعد تشغيل المنصّة** على بيئة
حقيقيّة (قاعدة + NATS + Ollama + بوّابات). مرتّبة بالمراحل: ما يجب أن يسبق، ثمّ
التحقّق الفوريّ، ثمّ التقوية، ثمّ النضج المعماريّ، ثمّ الميزات المؤجَّلة بقرار.

> الحالة عند كتابة الخطّة: المنصّة على `main` بعد **١١ دفعة (#49→#59)** — كلّ
> مراجعات الكود/المعماريّة أُغلقت عدا بند P2 واحد (Aggregate Root). الكود جاهز؛
> المتبقّي تشغيليّ/تحقّقيّ + نضج معماريّ مخطَّط.

الرموز: ☐ لم يبدأ · ◐ يحتاج بيئة/قرار · ⬛ تشغيليّ بحت (لا كود)

---

## المرحلة ٠ — مُتطلّبات النشر (قبل أيّ شيء) ⬛

| البند | الإجراء | معيار القبول |
|------|---------|-------------|
| قاعدة البيانات | `DATABASE_URL` + تشغيل `migrations/bootstrap_postgres.sh` (يطبّق init_v8 → **v48** عبر MANIFEST). يتطلّب PostGIS. | كلّ الجداول/القيود/المُطلِقات مُنشأة؛ `\dt` يُظهر fields/seasons/activities/events/event_outbox |
| الأسرار | `.env`: `JWT_SECRET`(≥32) أو `JWT_PRIVATE_KEY`/`JWT_PUBLIC_KEY` (RS256)، `DB_PASSWORD`، `REDIS_PASSWORD`، `MINIO_ROOT_PASSWORD` | الخدمات تُقلع بلا `:?required` errors |
| NATS (لازم الآن) | تشغيل `sahool-nats` — **مطلوب لتدفّق الأحداث فعليّاً** (OutboxWorker ينشر إليه) | في سجلّ المنصّة: `✓ OutboxWorker بدأ — relay الأحداث إلى nats://…` |
| Ollama + التضمين | تشغيل `sahool-ollama` + `ollama pull nomic-embed-text` قبل `qdrant-seed` | بذور Qdrant تنجح (لا «تخطّي البذر») |
| البوّابات الخارجيّة | اضبط عند الحاجة: SMS (`SMS_PROVIDER_URL`/`SMS_API_KEY`)، بريد (`SMTP_*`)، واتساب/تلغرام (`WHATSAPP_WEBHOOK_URL`/`TELEGRAM_BOT_TOKEN`)، Sentinel Hub (`SH_CLIENT_*`)، MQTT | إرسال فعليّ بدل «logged_not_sent» |

---

## المرحلة ١ — تحقّق فوريّ بعد التشغيل (يوم ٠) ◐

- ☐ **تدفّق الأحداث end-to-end:** أنشئ حقلاً عبر الـAPI ثمّ تحقّق:
  ```sql
  SELECT event_type, entity_id FROM events ORDER BY occurred_at DESC LIMIT 5;
  SELECT status, COUNT(*) FROM event_outbox GROUP BY status;  -- توقّع 'sent'
  ```
  والاستماع على NATS: `nats sub 'sahool.events.>'` يجب أن يلتقط `field.created`.
- ☐ **حوكمة DLQ:** `SELECT * FROM v_event_dead_letter;` يجب أن يكون فارغاً. لو علِقت
  أحداث (مثلاً كان NATS متوقّفاً): بعد إصلاح السبب شغّل `SELECT requeue_all_dead_letter();`.
- ☐ **الموبايل (Flutter):** `flutter pub get && flutter analyze && flutter build apk`
  ثمّ اختبار جهاز: تسجيل → onboarding (٠ حقول) → معالج إنشاء الحقل (رسم/استيراد) →
  Field Workspace. (كود #54 لم يُبنَ في بيئة CI — يلزم تحقّق جهاز قبل الإطلاق.)
- ☐ **تفعيل قيود `NOT VALID` رجعيّاً** بعد تدقيق سلامة البيانات القائمة:
  ```sql
  ALTER TABLE seasons    VALIDATE CONSTRAINT fk_seasons_field_tenant;     -- v47
  ALTER TABLE activities VALIDATE CONSTRAINT fk_activities_field_tenant;  -- v47
  ALTER TABLE seasons    VALIDATE CONSTRAINT chk_seasons_dates;           -- v47
  ALTER TABLE fields     VALIDATE CONSTRAINT fk_fields_manager_user;      -- v47
  ALTER TABLE activities VALIDATE CONSTRAINT fk_activities_season;        -- v48
  ```
  (تفشل لو وُجدت صفوف مخالفة ⇒ نظّفها أوّلاً. حتى التفعيل، القيود تُطبَّق على الجديد فقط.)

---

## المرحلة ٢ — تقوية الحاويات على المضيف (أسبوع ١) ⬛
المرجع الكامل: `docs/DEPLOYMENT_HARDENING.md`. تحتاج بناء Docker/تشغيل حقيقيّاً
(لا يُتحقَّق منها في CI لأنّ سياسة الشبكة تمنع apt/pip أثناء البناء).
- ☐ تثبيت الصور بالـ**digest** (`@sha256:…`) بدل الوسوم؛ والتحقّق من وسوم
  minio/ollama/titiler الافتراضيّة مقابل السجلّ.
- ☐ **بناء Python متعدّد المراحل** لكلّ خدمة (نقل gcc/libpq-dev لمرحلة builder) — بناء
  محليّ للتحقّق قبل النشر.
- ☐ **تثبيت إصدارات apt** (أو صورة أساس مثبّتة بالـdigest).
- ☐ **تقسيم الشبكة ٣ طبقات** (`public`/`internal`/`data` بـ`internal: true`) — اختبار
  اتّصال فعليّ بعد التطبيق.
- ☐ **أسرار Docker/K8s** بدل `environment:` (ملفّات `/run/secrets/*`).
- ☐ **حدود CPU** لكلّ خدمة (`cpus:` بقيم مضبوطة حسب الحمل).

---

## المرحلة ٣ — نضج معماريّ (P2): Field Aggregate Root (أسابيع ٢–٤)
**الهدف:** حدّ كتابة واحد للحقل وما يتفرّع عنه، فتمرّ كلّ التغييرات عبر مسار موحّد
`Command → FieldAggregate → State + Events (ذرّيّاً)` — مصدر حقيقة واحد، لا كتابة
مباشرة للجداول خارج هذا المسار.

**الوضع الحاليّ (أساس قويّ بُني هذه الجلسة):** Outbox ذرّيّ + idempotency (v11)،
CommandStore + RLS (v10)، lifecycle state-machine + ثابت زمنيّ (v46 trigger)،
وإصدار أحداث على كلّ مسارات الكتابة (#57/#58). الناقص: **مُوجِّه أوامر (Command
Dispatcher/Registry)** و**حدّ aggregate** يلفّ الحقل+الموسم+النشاط+الدورة.

**خطوات مقترحة (تدريجيّة، غير كاسرة):**
1. ☐ **Command Handler Registry:** `register(command_type, handler)` + `dispatch(cmd)`
   فوق `CommandStore` القائم (idempotency جاهز). يبدأ بأمر واحد (`CreateField`).
2. ☐ **FieldAggregate:** كائن يحمّل حالة الحقل (+ الموسم النشط + آخر lifecycle) ويعرّف
   عمليّات (`create/update/start_season/record_activity`) تتحقّق من الـinvariants ثمّ
   تُنتج (state change + events) ضمن معاملة واحدة.
3. ☐ **توجيه الـendpoints تدريجيّاً** إلى الـaggregate بدل الـINSERT المباشر — endpoint
   واحد كلّ مرّة، مع إبقاء التوافق الخلفيّ.
4. ☐ **حارس قاعديّ (اختياريّ):** منع UPDATE/INSERT المباشر على جداول الحالة خارج
   مسار محدَّد (أدوار/مُطلِقات) — يمنع الالتفاف على الـaggregate.
5. ☐ **فصل Field Lifecycle عن Season Lifecycle:** تحويل النموذج إلى
   `Field Aggregate └── Season Lifecycle` (ملاحظة مراجعتك) بدل lifecycle على الحقل.

**معيار القبول:** كلّ كتابة للحقل/الموسم/النشاط تمرّ عبر `dispatch` → اختبار يثبت أنّ
لا مسار INSERT مباشر خارج الـaggregate؛ والحالة والأحداث متّسقتان دائماً.
**مخاطر:** إعادة هيكلة واسعة لمسارات الكتابة — تُنفَّذ تدريجيّاً مع اختبارات تكامل.

---

## المرحلة ٤ — ميزات مؤجَّلة بقرار منتج (حسب الأولويّة)
- ☐ **Command Handler Registry / Dispatcher كامل** (P1 من مراجعة CQRS) — يُمهّد للمرحلة ٣.
- ☐ **DLQ admin endpoint/UI:** `GET /admin/events/dead-letter` + `POST …/requeue`
  (فوق `v_event_dead_letter`/`requeue_*` الجاهزة) — لتشغيل بلا SQL يدويّ.
- ☐ **توسيع تغطية الأحداث:** `FIELD_DELETED` عند إضافة endpoint حذف الحقل؛ أحداث
  إغلاق/تحديث الموسم.
- ☐ **`farm_id` إلزاميّ:** نافذة انتقاليّة (ترحيل البيانات بلا مزرعة → افتراضيّة، ثمّ
  `NOT NULL` + إلزام الواجهة بإنشاء مزرعة أوّلاً — منطق `canCreateFarm` جاهز).
- ☐ **Workflow مخبري للتربة:** عيّنة → نتيجة مختبر → اعتماد → إصدارات (جداول +
  endpoints + شاشة)؛ يستبدل أعمدة soil_* الحاليّة بدورة حياة.
- ☐ **الإثراء الجغرافيّ التلقائيّ:** بعد الرسم، ملء elevation/slope/aspect/climate/
  rainfall من DEM (SRTM/Copernicus) — يحتاج مصدر بيانات DEM. (الأعمدة جاهزة v37.)
- ☐ **بوّابة تأكيد بريد صلبة** قبل الوصول (بدل التحقّق الناعم الحاليّ) — قرار UX.

---

## ملاحظات تشغيليّة دائمة
- **مراقبة DLQ:** أنشئ تنبيهاً على سجلّ `DEAD_LETTER` (ERROR) أو على
  `SELECT COUNT(*) FROM v_event_dead_letter > 0`.
- **النسخ الاحتياطيّ:** `postgres-data` + `minio-data` + `nats-js` + `qdrant`.
- **الهجرات اللاحقة:** التزِم ترقيم `vNN` + إضافتها إلى `MANIFEST.txt` + idempotent +
  `NOT VALID` للقيود الجديدة على جداول فيها بيانات.

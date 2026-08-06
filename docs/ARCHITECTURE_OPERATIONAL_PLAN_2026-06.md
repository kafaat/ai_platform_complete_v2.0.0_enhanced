# خطّة المعالجة المعماريّة/التشغيليّة — يونيو ٢٠٢٦

> هذا المستند يوثّق فجوات **معماريّة/تشغيليّة** كُشِفت في مراجعة المكوّنات المشتركة
> (NATS · Redis · PgBouncer · `shared/helpers.py`) ولم تُطبَّق في الكود عمداً —
> لأنّها تتطلّب قراراً تشغيليّاً، أو تغييراً واسعاً عبر كلّ الخدمات، أو بيئة حيّة
> للتحقّق. الهدف: خطّة تنفيذ قابلة للتنفيذ بدل تطبيق متسرّع يكسر التشغيل دون أن
> تلتقطه بوّابة CI (التي تتحقّق من صياغة compose لا من تشغيل الحاويات فعليّاً).
>
> مكمّل لـ`DEPLOYMENT_HARDENING.md` و`AUTH_DENYLIST_DESIGN.md`.

الأولويّة العامّة: **(1) استنزاف اتّصالات DB** (أعلى احتمالاً للوقوع تحت الحمل)
→ **(2) هشاشة JetStream stream** (فقد أحداث صامت) → **(3) مصادقة NATS**
(عزل المستأجرين على الناقل) → **(4) حدود تخزين JetStream**.

---

## ١) استنزاف اتّصالات Postgres — لا مُجمِّع اتّصالات (PgBouncer)

### المشكلة
كلّ خدمة تُنشئ بركة `asyncpg` مستقلّة تتّصل مباشرةً بـPostgres. لا يوجد
PgBouncer منشور، رغم أنّ الكود **جاهز له** (`statement_cache_size=0` في كلّ
البرك — وهو الشرط لتوافق وضع `transaction` في PgBouncer).

### الدليل (سعة البرك القصوى)
| الخدمة | `max_size` | المرجع |
|--------|-----------|--------|
| sahool-platform | 10 | `services/sahool-platform/api/main.py:136` |
| auth | 10 | `services/auth/main.py:123` |
| shared `init_db` (الافتراضيّ) | 10 | `shared/helpers.py:51` |
| actuator / soil / odoo-bridge / market-mcp / notification / base_agent | 5 لكلٍّ | `*/main.py` (`create_pool ... max_size=5`) |
| guardrails HIL | 3 | `services/guardrails-engine/human_in_loop.py:25` |

الخدمات التي تستدعي `shared.init_db` تأخذ 10 لكلٍّ افتراضيّاً. المجموع التقديريّ
للسعة القصوى المتزامنة عبر ١٠+ خدمة يتجاوز **~110 اتّصالاً**.

`postgres` (`postgis/postgis:15-3.4`) **غير مضبوط** — `max_connections`
الافتراضيّ **100** (لا ضبط في `docker-compose.v9.yml` ولا في الهجرات). تحت حمل
متزامن: `FATAL: remaining connection slots are reserved` / `too many clients`.

### الخيارات والمفاضلات
| الخيار | المزايا | العيوب |
|--------|---------|--------|
| **أ. نشر PgBouncer** (موصى به) | يفصل سعة العميل عن خادم DB؛ الكود جاهز؛ يتوسّع | خدمة جديدة + تحديث `DATABASE_URL` لكلّ الخدمات لتشير إليه |
| ب. رفع `max_connections` | تغيير بسيط (سطر command) | كلّ اتّصال يستهلك ذاكرة؛ 200 على `mem_limit: 1g` متوسّط الخطورة؛ يؤجّل الحدّ لا يحلّه |
| ج. خفض `max_size` لكلّ بركة | بلا مكوّنات جديدة | يقلّل التوازي لكلّ خدمة؛ تعديل واسع؛ هشّ |

### التوصية (PgBouncer)
1. أضف خدمة في `docker-compose.v9.yml` على `sahool-internal` (لا منفذ مكشوف):
   ```yaml
   sahool-pgbouncer:
     image: bitnami/pgbouncer:1.23.1   # ثبّت إصداراً (يُفضّل @sha256)
     environment:
       POSTGRESQL_HOST: sahool-postgres
       POSTGRESQL_USERNAME: sahool_user
       POSTGRESQL_PASSWORD: ${DB_PASSWORD:?}
       POSTGRESQL_DATABASE: sahool
       PGBOUNCER_POOL_MODE: transaction      # يتطلّب statement_cache_size=0 (موجود)
       PGBOUNCER_MAX_CLIENT_CONN: "500"
       PGBOUNCER_DEFAULT_POOL_SIZE: "25"     # ← الاتّصالات الفعليّة لـPostgres
     depends_on: { sahool-postgres: { condition: service_healthy } }
     security_opt: [ "no-new-privileges:true" ]
   ```
2. وجّه `DATABASE_URL` لكلّ خدمات التطبيق إلى `...@sahool-pgbouncer:6432/sahool`.
   (DDL/الهجرات تبقى على `sahool-postgres` المباشر — لا تمرّ عبر pooler.)
3. تحقّق: `default_pool_size × عدد قواعد/مستخدمين` يجب أن يبقى < `max_connections`
   لـPostgres (احتفظ بـ`max_connections=100`، و`default_pool_size=25` يكفي).
4. **قيد مهمّ:** وضع `transaction` لا يدعم session-level features (LISTEN/NOTIFY،
   advisory locks عبر معاملات، `SET` خارج معاملة). راجع: RLS هنا تستخدم
   `SET LOCAL`/`set_config(..., true)` (محصور بالمعاملة) — **متوافق**. تأكّد ألّا
   تعتمد أيّ خدمة على حالة جلسة تتجاوز المعاملة.

### التحقّق
- بعد النشر: `SHOW POOLS;` على PgBouncer (منفذ admin 6432) لمراقبة `cl_active`/`sv_active`.
- اختبار حمل: تأكّد أنّ `sv_active` لا يتجاوز `default_pool_size`، وأنّ
  `SELECT count(*) FROM pg_stat_activity` يبقى أقلّ بكثير من 100.

---

## ٢) هشاشة دورة حياة JetStream stream — فقد أحداث صامت

### المشكلة
الـstream `sahool` (الذي يغطّي كلّ المواضيع `sahool.>`) يُنشَأ **حصراً** داخل وكيل
الإشعارات عند إقلاعه. الناشرون يستخدمون `js.publish` التي تفشل إن لم يوجد stream
يطابق الموضوع — والفشل **مبتلَع** (يُسجَّل تحذيراً، تُرجَع `False`) فتُفقَد الأحداث
دون إشارة واضحة.

### الدليل
- إنشاء الـstream: `agents/notification/agent.py:359`
  `await _js.add_stream(StreamConfig(name="sahool", subjects=["sahool.>"]))`.
- النشر عبر JetStream:
  - `shared/helpers.py:306-316` (`publish_event` → `js.publish`، يبتلع الاستثناء).
  - `services/vegetation-analysis-service/main.py:535-536` (`js.publish`).
- النتيجة: إن أقلع ناشرٌ ونشر **قبل** أن ينشئ وكيل الإشعارات الـstream — أو إن كان
  الوكيل معطّلاً/غير منشور — يفشل كلّ نشر صامتاً ⇒ فقد أحداث (لا at-least-once فعليّ).

### الخيارات
| الخيار | المزايا | العيوب |
|--------|---------|--------|
| **أ. توفير الـstream مستقلّاً عند الإقلاع** (موصى به) | يفصل دورة الحياة عن أيّ مستهلك؛ at-least-once حقيقيّ | يحتاج مهمّة/خدمة تهيئة أو `add_stream` idempotent في كلّ ناشر |
| ب. `add_stream` idempotent في `init_nats` المشترك | مركزيّ، أيّ خدمة تضمنه | يكرّر منطق الإعداد؛ سباقات حميدة (idempotent) |
| ج. عدم ابتلاع فشل النشر | يكشف المشكلة بدل إخفائها | يحتاج سياسة معالجة (إعادة محاولة/DLQ) في كلّ مُستدعٍ |

### التوصية
- اجعل توفير الـstream **idempotent ومستقلّاً**: مهمّة تهيئة `nats-init` (تشبه
  `qdrant-seed`) تُنشئ `sahool` (subjects `sahool.>`, retention، حدود) قبل بدء
  الناشرين، أو ضع `_ensure_stream()` idempotent في `shared.init_nats` يُستدعى مرّةً.
  مثال إعداد الـstream (يحدّد retention وحدوداً صريحة):
  ```python
  from nats.js.api import StreamConfig, RetentionPolicy

  await js.add_stream(
      StreamConfig(
          name="sahool",
          subjects=["sahool.>"],
          retention=RetentionPolicy.LIMITS,
          max_age=7 * 24 * 3600,  # احتفاظ ٧ أيّام
          max_bytes=1_000_000_000,  # سقف ١GB (يكمّل حدود الخادم في §٤)
      )
  )
  ```
- رفع مستوى ملاحظة فشل النشر في `publish_event`: أبقِ الابتلاع لكن **زِد عدّاد
  Prometheus** (`sahool_nats_publish_failed_total`) كي يُرصَد الفقد بدل أن يُخفى.

### التحقّق
- `nats stream info sahool` (أو واجهة `:8222`) يُظهِر الـstream والرسائل المتراكمة.
- بعد إيقاف وكيل الإشعارات مؤقّتاً ونشر حدث: يجب أن يبقى الحدث في الـstream (لا يُفقَد).

---

## ٣) مصادقة NATS — الناقل مفتوح داخليّاً (عزل المستأجرين)

### المشكلة
خادم NATS يعمل **بلا مصادقة**: `--js --store_dir … --http_port 8222` فقط — لا
`--user`/`--pass`/`--auth`/nkey/حساب. أيّ حاوية على شبكة `sahool-internal` تستطيع
النشر/الاشتراك في **أيّ** موضوع، بما فيه `sahool.tenant.{أيّ مستأجِر}.*`. فحاوية
مخترقة (أو خدمة بها ثغرة) يمكنها قراءة أو حقن أحداث أيّ مستأجِر على الناقل.

### الدليل
- الخادم: `docker-compose.v9.yml` خدمة `sahool-nats` (`command: --js --store_dir
  /data/jetstream --http_port 8222`) — لا مصادقة.
- العملاء: `shared/helpers.py:132-141` (`nats.connect(nats://sahool-nats:4222)`
  بلا بيانات اعتماد). المواضيع لكلّ مستأجِر: `shared/helpers.py:322`
  (`sahool.tenant.{tenant_id}.{event_type}`).

> هذا **داخليّ** (الشبكة غير مكشوفة للخارج)، فهو دفاع‑في‑العمق لا ثغرة مكشوفة —
> لكنّه يكسر مبدأ عزل المستأجرين على مستوى الناقل في منصّة متعدّدة المستأجرين.

### الخيارات (متدرّجة)
| المستوى | ما يوفّره | الكلفة |
|---------|----------|--------|
| **أ. توكن واحد للخادم** (`--auth <token>`) | يمنع أيّ عميل بلا توكن من الاتّصال | تحديث سلسلة اتّصال كلّ الخدمات (`nats://:TOKEN@…`) |
| ب. مستخدم/كلمة سرّ أو nkey لكلّ خدمة | هويّة لكلّ خدمة | إدارة بيانات اعتماد متعدّدة |
| ج. **حسابات + صلاحيّات مواضيع** (NATS accounts) | عزل فعليّ: خدمة تنشر فقط لمواضيعها | الأعقد؛ ملفّ إعداد accounts كامل |

### التوصية (مرحلتان)
1. **الآن (أ):** توكن خادم واحد عبر `${NATS_TOKEN:?}`، وتحديث `NATS_URL` لكلّ
   الخدمات إلى `nats://:${NATS_TOKEN}@sahool-nats:4222`. تغيير ميكانيكيّ لكنّه
   يلمس **كلّ** خدمة تتّصل بـNATS — يجب تطبيقه دفعةً واحدة وإلّا تفشل الخدمات
   غير المُحدَّثة في الاتّصال. لذا **لم يُطبَّق عمياءً** (خطر كسر اتّصال جزئيّ).
2. **لاحقاً (ج):** حسابات NATS بصلاحيّات مواضيع: ناشر القمر الصناعيّ يُسمَح له
   `publish` على `sahool.tenant.*.satellite.>` فقط، إلخ — عزل حقيقيّ على الناقل.

### التحقّق
- بعد (أ): عميل بلا توكن يجب أن يُرفَض (`nats pub` بلا creds ⇒ Authorization Violation).
- كلّ الخدمات تبقى متّصلة (`:8222/connz` يُظهِر الاتّصالات النشطة).

---

## ٤) حدود تخزين JetStream — منع امتلاء القرص

### المشكلة
JetStream مفعّل بمخزن دائم (`--store_dir /data/jetstream` على الوحدة `nats-js`)
**بلا حدّ تخزين** — الافتراضيّ على مستوى الخادم غير محدود، فقد يمتلئ القرص.

### لماذا لم يُطبَّق في الكود
أعلام CLI لحدود التخزين في `nats:2-alpine` **غير مؤكَّدة الاسم/الصيغة** عبر
الإصدارات، وعلمٌ خاطئ **يكسر إقلاع الخادم** — وبوّابة `Validate Docker Compose`
تتحقّق من صياغة compose فقط، **لا تشغّل الحاوية**، فلن تلتقط الكسر. (صدقاً:
تجنّبتُ تغييراً قد يمرّ في CI ثمّ يفشل في الإنتاج.)

### التوصية (ملفّ إعداد بدل أعلام مشكوكة)
ركّب ملفّ إعداد NATS وحدّد الحدود فيه (مستقرّ عبر الإصدارات):
```
# nats/nats-server.conf
jetstream {
  store_dir: /data/jetstream
  max_memory_store: 128MB
  max_file_store:   2GB
}
http_port: 8222
# (أضف بلوك authorization هنا عند تنفيذ §٣)
```
ثمّ `command: ["-c", "/etc/nats/nats-server.conf"]` مع تركيب الملفّ `:ro`.
**تحقّق محليّاً أوّلاً:** `docker run --rm -v $PWD/nats:/etc/nats nats:2-alpine -c
/etc/nats/nats-server.conf` يجب أن يُقلِع بلا خطأ قبل الدمج.

### التحقّق
- `:8222/jsz` يُظهِر `max_memory`/`max_storage` بالقيم المضبوطة.

---

## ملخّص الأولويّات والجهد

| # | البند | الأثر | الجهد | يتطلّب |
|---|------|-------|------|--------|
| ١ | PgBouncer | استنزاف اتّصالات تحت الحمل | متوسّط | خدمة جديدة + تحديث DATABASE_URL |
| ٢ | توفير JetStream stream | فقد أحداث صامت | منخفض–متوسّط | مهمّة تهيئة أو ensure idempotent |
| ٣ | مصادقة NATS | عزل مستأجرين على الناقل | متوسّط (دفعة واحدة) | تحديث NATS_URL لكلّ خدمة |
| ٤ | حدود تخزين JetStream | امتلاء قرص | منخفض | ملفّ إعداد + تحقّق إقلاع حيّ |

> **مبدأ مشترك:** كلّ هذه تلمس البنية التشغيليّة الحيّة ولا تلتقط بوّابة CI الحاليّة
> أخطاء تشغيلها. لذا التنفيذ يجب أن يقترن بتحقّق على بيئة فعليّة (compose up +
> فحوص الدخان) لا بالقراءة وحدها — وهو خارج نطاق هذا الصندوق.

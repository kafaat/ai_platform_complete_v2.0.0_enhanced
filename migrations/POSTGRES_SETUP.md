# تشغيل PostgreSQL لـسهول

## الوضع الحالي (صدق)
في بيئة التطوير المعزولة هذه **لا يُمكن تشغيل PostgreSQL فعلياً**: لا توجد
binaries، لا Docker، والشبكة محجوبة (apt يفشل بـ403 على تنزيل الحزم). لذلك
بنينا **حزمة تشغيل كاملة جاهزة** تعمل بأمر واحد على أيّ جهاز فيه Docker —
بدل تزييف قاعدة وهميّة.

## ما في هذه الحزمة
| الملفّ | الوظيفة |
|-------|---------|
| `bootstrap_postgres.sh` | أمر واحد: يشغّل PostGIS، يطبّق كل الـmigrations بالترتيب، يتحقّق |
| `MANIFEST.txt` | ترتيب الـmigrations الصحيح (يُصلح خطأ الترتيب الأبجدي: v10/11/12 قبل v9) |
| `validate_migrations.py` | فحص ثابت بلا DB (أقواس، اقتباسات، فهارس non-IMMUTABLE، ON CONFLICT) |
| `*.sql` | الـmigrations العشرة |

## التشغيل (على جهاز فيه Docker)
```bash
cd migrations
./bootstrap_postgres.sh
```
يطبع في النهاية `DATABASE_URL` جاهزاً للـbackend.

متغيّرات اختياريّة:
```bash
PGPASSWORD=my_pw PGPORT=5433 ./bootstrap_postgres.sh
```

## الفحص الثابت (يعمل هنا الآن، بلا Docker)
```bash
python3 validate_migrations.py
```

## ما أصلحناه في هذه الجلسة (كشفه الفحص الثابت)
- **خطأ ترتيب الـmigrations:** الترتيب الأبجدي يطبّق v10/v11/v12 قبل v9 →
  تنكسر الاعتماديّات. `MANIFEST.txt` يفرض الترتيب الصحيح.
- **خطأ `ON CONFLICT (field_id)` في v9_foundation:** كان جدول `fields` لا
  يُنشأ (الكود المسؤول حُذِف وبقي تعليق "dead code removed")، و`field_id`
  لم يكن مفتاحاً فريداً → `ON CONFLICT (field_id)` كان سيفشل وقت التشغيل
  ("no unique constraint matching"). أنشأنا `fields` صراحةً بـ
  `field_id PRIMARY KEY`.

## نموذج الدورين (أمان RLS) — مهمّ
`bootstrap_postgres.sh` يُنشئ **بعد** كلّ الهجرات دوراً مقيّداً للتشغيل اسمه
`sahool_app`، ويطبع `DATABASE_URL` خاصّاً به. السبب:

- **مالك الهجرات** (`sahool_user`، superuser في صورة postgres الرسميّة) يُنشئ
  الجداول/الامتدادات/سياسات RLS. لكنّ **superuser يتجاوز RLS حتى مع FORCE** —
  فلو اتّصل التطبيق به لانهار عزل المستأجرين بالكامل رغم وجود السياسات.
- **دور التطبيق** `sahool_app` يُنشأ بـ
  `NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE LOGIN` ويُمنح
  `USAGE` على schema + `SELECT/INSERT/UPDATE/DELETE` على الجداول +
  `USAGE,SELECT` على التسلسلات + `EXECUTE` على الدوال (و`ALTER DEFAULT
  PRIVILEGES` لتغطية كائنات الهجرات المستقبليّة). هذا كافٍ لأنّ التطبيق لا
  ينفّذ DDL وقت التشغيل (DML + `SET LOCAL app.current_tenant` + `emit_event()`).

> القاعدة: وجّه `DATABASE_URL` للتطبيق إلى **`sahool_app`** (لا `sahool_user`).
> كلمة سرّه من `APP_DB_PASSWORD`. أبقِ `sahool_user` للهجرات/الإدارة فقط.

السكربت idempotent: إعادة تشغيله لا تُخطئ على دور موجود (CREATE مشروط +
ALTER لتثبيت السمات/كلمة السرّ).

## بعد التشغيل: ما الذي يُفتَح؟
بمجرّد توفّر القاعدة، تُغلَق فجوات المرحلة ٠ المتبقّية:
1. توصيل الوحدات الأربع (command_store/event_bus/data_lineage/sharing) — لها
   pool حقيقي الآن.
2. اختبارات asyncpg الفعليّة.
3. أمثلة تشغيل الـendpoints الـ٣٣ مع DB.

الترتيب: شغّل `bootstrap_postgres.sh` → ضع `DATABASE_URL` في `.env` →
شغّل الـbackend → نفّذ اختبارات التكامل.

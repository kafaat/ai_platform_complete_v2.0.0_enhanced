# النسخ الاحتياطي/الاستعادة + هيكل الهجرات — النتيجة

أنجزتُ البندين معاً. كلاهما قابل للكتابة بصدق offline، تختبرهما على جهازك.

## ١. النسخ الاحتياطي والاستعادة
| السكربت | الحالة | يغطّي |
|---------|--------|-------|
| backup_postgres.sh | موجود أصلاً | PostgreSQL: pg_dump + PITR/WAL + retention |
| **restore_postgres.sh** | **جديد** | استعادة كاملة/انتقائيّة + فحص سلامة + dry-run + تأكيد |
| **backup_minio.sh** | **جديد** | MinIO: نسخ+استعادة الكائنات (رواستر/صور) |

### لماذا restore_postgres.sh؟
backup_postgres.sh كان يحوي **إرشادات** استعادة فقط (تعليقات)، لا سكربتاً
قابلاً للتشغيل. الآن:
```bash
./restore_postgres.sh backup.dump              # كاملة (بتأكيد)
./restore_postgres.sh backup.dump --table soil_readings  # جدول واحد
./restore_postgres.sh backup.dump --dry-run    # عرض دون تنفيذ
```
حماية: يرفض الملفّ التالف، يطلب تأكيداً قبل الكتابة فوق البيانات.

### لماذا backup_minio.sh؟
الكائنات (رواستر COG، صور كاميرات الحقل) **لم تكن مشمولة** بأيّ نسخ. فقدانها
= فقدان بيانات لا تُعوَّض. الآن:
```bash
./backup_minio.sh backup           # كلّ الـbuckets
./backup_minio.sh restore <dir>    # استعادة
./backup_minio.sh list             # النسخ المتاحة
```
يستخدم mc (أداة MinIO الرسميّة) + mirror.

## ٢. هيكل الهجرات (Alembic)
المشروع يستخدم 20 هجرة SQL يدويّة (لا ORM، لا أداة versioning). أضفتُ Alembic
يحترم التاريخ:
- `alembic.ini` — إعداد (DATABASE_URL من البيئة، لا سرّ)
- `alembic/env.py` — بيئة تشغيل (SQL خام، لا ORM)
- `alembic/versions/0001_baseline.py` — يقرّ بالهجرات الـ18 كمُطبَّقة
- `alembic/README.md` — دليل

### الاستخدام (في بيئتك)
```bash
pip install alembic
export DATABASE_URL='postgresql://user:pass@host:5432/sahool'
alembic stamp 0001_baseline          # مرّة واحدة (وسم الحالي)
alembic revision -m "وصف"; alembic upgrade head   # هجرات جديدة
```

### لماذا baseline لا تحويل كامل؟
تحويل الـ20 هجرة لمراجعات Alembic محفوف بالمخاطر (RLS/triggers/PostGIS).
الأأمن: baseline يقرّ بها، والجديد يُدار بـAlembic.

## التحقّق
- 632/632 roadmap (+6) · 0 خطأ
- 3 سكربتات صالحة (bash -n) · alembic.ini صالح · baseline يُترجم

## ملاحظة صدق
السكربتات **مُتحقَّق من بنيتها** (bash -n) لكن **لم أشغّلها** (بيئتي بلا
docker/postgres/mc). منطقها قياسي (pg_restore/mc mirror). Alembic **هيكل**
مُترجَم وصالح — لكنّ `alembic stamp/revision` يحتاج DB حيّة + الحزمة على جهازك.
لم أحوّل الهجرات الـ20 لـAlembic (خطر على RLS/PostGIS) — baseline أأمن.
ستتأكّد من كلّ هذا بالتشغيل الفعلي.

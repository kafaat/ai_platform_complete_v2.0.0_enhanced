# Historical Alembic prototype — not a deployment migration runner

The canonical platform schema is managed by `migrations/MANIFEST.txt` and the
`sahool-migrate` runner using `scripts_v9/run_migrations.sql`. The decision service
has its own owned migration path. This Alembic prototype is not part of either
production chain and must not be stamped or upgraded on a deployed database.
Its two revisions are retained as historical source, not future migration guidance.

For a new platform migration, follow the canonical migration manifest/runbook
and its ownership and GATE-01 requirements. Any future Alembic adoption requires
an explicit mapping from the full canonical history and a tested transition.
The old "20 migrations" baseline is not a representation of the current schema.

The material below is historical context only; its setup commands are obsolete.

---

# هجرات Alembic — SAHOOL

## السياق
المشروع بدأ بـ20 هجرة SQL يدويّة (`migrations/*.sql`، asyncpg، لا ORM). هذا
الهيكل يُدير الهجرات **المستقبليّة** عبر Alembic مع احترام التاريخ اليدوي.

## الإعداد (مرّة واحدة، في بيئتك)
```bash
pip install alembic
export DATABASE_URL='postgresql://user:pass@host:5432/sahool'
# وسم الهجرات الـ20 الحاليّة كمُطبَّقة (لا يُعيد تشغيلها)
alembic stamp 0001_baseline
```

## الهجرات الجديدة
```bash
alembic revision -m "add irrigation_log table"   # ينشئ ملفّاً في versions/
# حرّر الملفّ: op.execute("""CREATE TABLE ...""")  (SQL خام، لا ORM)
alembic upgrade head        # طبّق
alembic downgrade -1        # تراجع خطوة
alembic current             # المراجعة الحاليّة
alembic history             # كلّ المراجعات
```

## لماذا baseline لا تحويل كامل؟
تحويل الـ20 هجرة اليدويّة لمراجعات Alembic ممكن لكن محفوف بالمخاطر (قد يكسر
ترتيب RLS/triggers/PostGIS). الأأمن: baseline يقرّ بها كمُطبَّقة، والجديد
يُدار بـAlembic. لإعادة بناء قاعدة من الصفر: طبّق `migrations/*.sql` بالترتيب
ثمّ `alembic stamp 0001_baseline`.

## الأمان
`env.py` يقرأ `DATABASE_URL` من البيئة — لا كلمة سرّ في الملفّات.

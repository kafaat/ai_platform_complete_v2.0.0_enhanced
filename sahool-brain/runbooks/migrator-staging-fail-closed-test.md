# رَنبوك — اختبارُ المُهاجر المعزول على staging (fail-closed + قراءةٌ فقط)

> **الغرض:** شرطُ `verified` لـ`MIGRATOR-PROCEEDS-TO-APPLY-AFTER-READINESS-TIMEOUT-01` (الصفّ في
> [`../gaps/registry.md`](../gaps/registry.md)). الإصلاحُ البرمجيّ (`48f6d666`، PR #1160) مُثبَتٌ بشواهدَ
> محلّيّة فقط؛ هذا الرَّنبوك يُثبته من **سجلّ نشرٍ حقيقيّ على staging**. لا يُنفَّذ على production.
>
> **عقد الصدق:** كلُّ خطوةٍ هنا نشرٌ على Railway = **قرارُ المالك وموافقتُه الصريحة** قبل التنفيذ؛ لا
> أسرارَ في المحادثة (أسماءُ المتغيّرات فقط)؛ لا تُضبط `SAHOOL_MIGRATE_APPLY=1` في أيٍّ من السيناريوهين؛
> والدليلُ هو سجلُّ النشر بمعرّفه لا وصفُه.

---

## 0. المتطلّبات

| المطلب | التفصيل |
|---|---|
| الفرع | `main` بعد دمج #1159 ثمّ #1160 (أو رأسُ #1160 مُثبَّتاً مصدراً لخدمة `sahool-migrate-main` في staging عبر `connect-service-source` مع `staged:true` ثمّ القبول — النمطُ المُعتمَد في ledger «staging أوّلاً») |
| الخدمة | `sahool-migrate-main` في staging (`70cc51f8-…`)؛ `restartPolicy=NEVER` كما هو |
| المتغيّرات | `PGHOST=sahool-postgres.railway.internal` كما هو؛ **`SAHOOL_MIGRATE_APPLY` غيرُ مضبوط** (أو ≠ `1`)؛ اختياريّاً `PROBE_PGUSER`/`PROBE_PGPASSWORD` لدورٍ قراءةٍ أدنى صلاحيّةً |
| الأثرُ على staging | لا هجرة ولا أدوار في أيٍّ من السيناريوهين بالتصميم — وهذا ما يُقاس |

---

## 1. السيناريو أ — القاعدةُ غائبة (fail-closed)

**الحال:** `sahool-postgres` في staging بلا نشرٍ حيّ (كما هي منذ 2026-10-05) — لا يُنشأ ولا يُشغَّل شيء.

1. انشر `sahool-migrate-main` (بموافقة المالك). سجّل معرّفَ النشر.
2. اقرأ سجلّ النشر (`get-logs(deploymentId)`). **المتوقَّع حرفيّاً:**
   ```
   بانتظار postgres (1)… … بانتظار postgres (30)…
   MIGRATIONS_NOT_APPLIED reason=database_unreachable host=sahool-postgres.railway.internal:5432 attempts=30
   ✗ لم تُثبَت جاهزيّةُ القاعدة … — لا تُطبَّق أيُّ هجرة (fail-closed).
   ```
   وحالةُ النشر **CRASHED** (خروج 1، لا إعادةَ تشغيل).
3. **برهانُ (١):** لا يظهر في السجلّ أيُّ سطرٍ من `─ تطبيق الهجرات` ولا `→ <file>.sql` ولا `psql:` —
   أي **لا استدعاءَ psql** (قبل الإصلاح كان السجلّ يُظهر `→ init_v8.sql` ثمّ خطأَ DNS: نشر `87cc687b`).

## 2. السيناريو ب — القاعدةُ جاهزة بلا إذن (قراءةٌ فقط)

**الحال:** `sahool-postgres` في staging حيّ (بعد قرار المالك بإعادة نشرها وفق بوّابة #1158) و`SAHOOL_MIGRATE_APPLY` غيرُ مضبوط.

1. **جردٌ قبلُ** (قراءةً فقط، من طرفيّة القاعدة أو `probe_platform_db.py`):
   ```sql
   SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relkind='r';
   SELECT count(*) FROM information_schema.columns WHERE table_schema='public';
   SELECT rolname, rolsuper, rolbypassrls FROM pg_roles WHERE rolname LIKE 'sahool%' ORDER BY 1;
   ```
2. انشر `sahool-migrate-main` (بموافقة المالك). سجّل معرّفَ النشر.
3. اقرأ سجلّ النشر. **المتوقَّع:**
   ```
   MIGRATIONS_NOT_APPLIED reason=apply_not_permitted host=sahool-postgres.railway.internal:5432
   ─ القاعدةُ جاهزة، لكنّ تطبيقَ الهجرات غيرُ مأذونٍ به … ─
   ─ قراءةُ هويّة القاعدة (read-only) … ─
     transaction_read_only=on · PostgreSQL … · db=… · user=… (super=…) · server=…
   ─ المتوقَّع من MANIFEST (231 ملفّاً): 341 جدولاً · 127 عموداً ─
   … (الغائب إن وُجد، وأوّلُه في ترتيب MANIFEST)
   SCHEMA_STATE readable=true read_only=on db=… user=… tables=p/341 columns=p/127 first_missing=<file|none> scope=tables_and_columns_only
   MIGRATION_INSPECTION_COMPLETED apply=false
   ```
   وحالةُ النشر **SUCCESS** (خروج 0). غيابُ `MIGRATION_INSPECTION_COMPLETED` مع SUCCESS مستحيلٌ بالعقد؛ إن
   فشلت القراءة فالمتوقَّع `SCHEMA_PROBE_FAILED exit=3` وحالةُ النشر **CRASHED** — وليس ذلك نجاحاً (السيناريو ج).
4. **جردٌ بعدُ:** الاستعلاماتُ الثلاث نفسُها — **المتوقَّع: الأرقامُ والأدوارُ متطابقةٌ تماماً** مع «قبلُ».
5. **برهانُ (٢):** لا `→ <file>.sql` في السجلّ، و`transaction_read_only=on` مطبوعةٌ من الخادم، والجردُ
   قبل/بعد متطابق ⇒ القاعدةُ الجاهزة لم تُمَسّ بلا إذن.
6. **قيمةٌ مضافة:** سطرُ `SCHEMA_STATE` هو أوّلُ قراءةٍ كاملة لحالة الهجرات على staging —
   يُلحَق بصفّ `MIGRATION-STATE-IN-PRODUCTION-IS-UNREAD-01` (الذي يبقى open حتّى يُقرأ من production).

## 2ب. السيناريو ج — القاعدةُ جاهزة لكنّ القراءةَ تفشل (ليس نجاحاً)

اختياريٌّ لكنّه يثبت الجانبَ الثالث من العقد: اضبط `PROBE_PGUSER` على دورٍ غير موجود (أو بياناتِ اعتمادٍ غير
صالحة) وانشر. **المتوقَّع:** `MIGRATIONS_NOT_APPLIED reason=apply_not_permitted` ثمّ
`SCHEMA_STATE readable=false reason=connect_or_query_failed …` و`SCHEMA_PROBE_FAILED exit=3`، وحالةُ النشر
**CRASHED**، والجردُ قبل/بعد متطابق. ثمّ أعِد المتغيّرَ إلى قيمته.

---

## 3. التسجيل (شرطُ الانتقال إلى verified)

يُلحَق بخليّة حالة الصفّ، بتاريخٍ ومعرّفَي النشر: الأسطرُ الآليّة الثلاثة (`MIGRATIONS_NOT_APPLIED …` ×2،
`SCHEMA_STATE …`)، وحالتا النشر (CRASHED / SUCCESS)، وجردُ «قبل/بعد» للسيناريو ب. بدون السيناريو ب
(لأنّ القاعدة لم تعُد) يُسجَّل السيناريو أ وحده **ولا** تنتقل الحالة — فالبرهانُ (٢) جزءٌ من الشرط.

**ما لا يُثبته هذا الرَّنبوك:** استعادةُ الإنتاج (`PRODUCTION-ENVIRONMENT-ALL-DEPLOYMENTS-REMOVED-SINCE-20261005-01`)
ولا سلامةُ النسخ الاحتياطيّ؛ هذان في بوّابة #1158 قبله.

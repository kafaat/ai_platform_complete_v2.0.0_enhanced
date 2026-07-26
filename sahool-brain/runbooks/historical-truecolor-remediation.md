# رَنبوك التشغيل — معالجة «الخطّ الزمنيّ التاريخيّ الفارغ» (Historical Truecolor)

> **قابل للنسخ من الشاشة.** كتل الأوامر مُصمَّمة للصقّ المباشر في صدفة المُشغّل على البيئة الحيّة (نمط `v22-*`).
> نشأ من تقرير تشخيصيّ للحقل `fld_d5015f12578c` (خطّ زمنيّ truecolor فارغ). **الإصلاحان الكوديّان مدموجان
> بالفعل** (PR #657، `75b3ad5`)؛ هذا الرَّنبوك يغطّي **فقط** البنود التشغيليّة/البيئيّة المتبقّية التي لا
> يملكها المستودع.
>
> **عقد الصدق (صارم):**
> - **الأسرار عبر البيئة فقط** — كلمات مرور القاعدة/S3 تُحقَن من مدير الأسرار/`.env` غير المُتعقَّب؛ لا تُكتَب هنا.
> - لا TLS معطَّل · لا منح أوسع من اللازم (least-grant) · `%G? = N` ليس سبباً لـforce على main.

---

## خلفية — ما أُصلِح كوديّاً (لا فعل تشغيليّ)

| البند | الجذر | الحالة |
|---|---|---|
| **Finding 2** (حرِج) — الخطّ الزمنيّ الفارغ | `fetch_latest_asset` مرّر نصّ التاريخ خاماً إلى `$3::date` ⇒ asyncpg يستدعي `.toordinal()` على `str` ⇒ خطأ مُبتلَع ⇒ صفر صفوف. | **مُصلَح** — `_iso_date_or_none` مشترك (`services/raster-service/db_persist.py`)، PR #657. |
| **Finding 4** (عالٍ) — حلقة إعادة تشغيل projection-worker | العامل المُعطَّل كان يخرج فوراً مع `restart:unless-stopped` + فحص `pgrep`. | **مُصلَح** — يخمل بدل الخروج (`services/scout-ingest-service/projection_worker.py`)، PR #657. |
| **Finding 1** (واجهة) — رابط `field_id` غير مُحلّ | صار يُظهر لافتة صريحة (`data-testid="fieldview-status"`) + احتياطيّ لطيف. | **مُنفَّذ مسبقاً** — `MapHub.tsx:346,1676` + `lib/fields.ts` + اختبار `fields.fieldview.test.ts`. لا فعل. |

> بعد نشر `75b3ad5`: أعِد تشغيل `raster-service` و`scout-ingest-projection` لالتقاط الكود الجديد.

---

## Finding 1 (بيانات) — الحقل `fld_d5015f12578c` غير موجود في القاعدة

**التشخيص:** الحقل غير مُسجَّل لأيّ مستأجِر (صفر صفوف في `fields`)؛ الواجهة تحلّ الرابط، تجده غير متاح،
تُظهر اللافتة وترجع للحقل النشط. **ليس عطلاً** — سلوك مقصود. المطلوب تشغيليّاً: تسجيل الحقل الصحيح أو
تصحيح الرابط.

**تحقّق (للقراءة فقط):**
```bash
docker exec -i v22-sahool-postgres-1 psql -U sahool_user -d sahool -c \
  "SELECT field_id, tenant_id, name FROM fields WHERE field_id = 'fld_d5015f12578c';"
# صفر صفوف ⇒ الرابط يشير إلى حقل غير مُسجَّل (لا معالجة مطلوبة على القاعدة)
```
**الحلّ:** أنشئ الحقل عبر مسار المنصّة العاديّ (`POST /api/v1/fields`، JWT-محميّ، يضبط `tenant_id`
من الهويّة) — **لا إدراج يدويّ في القاعدة** (يتجاوز RLS والتحقّق الهندسيّ). ثمّ افتح الرابط بمعرّف الحقل
المُسجَّل الفعليّ.

---

## Finding 5 — `sahool_user` يفتقر SELECT على جدول هندسة PostGIS (503 على drawing-features)

**التشخيص:** المستودع يشغّل `CREATE EXTENSION postgis` **كـ`sahool_user`** (`migrations/v9_foundation.sql:19`
وغيرها)، فيملك تحت التهيئة الصحيحة كلّاً من `spatial_ref_sys` والجداول التي أنشأها ⇒ لا حاجة لأيّ منح
صريح (صفر `GRANT ... TO sahool_user` في المستودع). ظهور `InsufficientPrivilegeError` حيّاً يعني أنّ
PostGIS/الجداول أُنشئت على تلك البيئة بمستخدم superuser **مختلف** — تفاوت تهيئة، لا عيب كوديّ.

**تحقّق (للقراءة فقط) — من يملك spatial_ref_sys والجداول:**
```bash
docker exec -i v22-sahool-postgres-1 psql -U sahool_user -d sahool -c \
  "SELECT relname, pg_get_userbyid(relowner) AS owner
     FROM pg_class WHERE relname IN ('spatial_ref_sys','fields','drawing_features');"
```
**الحلّ (أحد خيارين، حسب سياسة المنح على البيئة):**
```bash
# الأنظف: أعِد تشغيل الهجرات كـsahool_user (فيملك كلّ ما يُنشئه) — راجع pg16-staging-activation.md.
# أو المنح المُوجَّه الأدنى (least-grant) إن كان المالك مختلفاً بالفعل:
docker exec -i v22-sahool-postgres-1 psql -U <owner_superuser> -d sahool -c \
  "GRANT SELECT ON spatial_ref_sys, fields, drawing_features TO sahool_user;"
```
> **صدق:** لا تمنح `ALL` ولا على `public` كاملاً. `spatial_ref_sys` كافٍ لدوالّ `ST_GeomFromGeoJSON`/SRID.

---

## Finding 6 — تخزين الكائنات (MinIO) فارغ؛ COGs تُكتَب محلّيّاً (`file://`)

**التشخيص:** `object_store.upload_cog` ينحدر إلى `file:///data/rasters/*.tif` عند غياب/فشل تهيئة S3
(احتياطيّ مقصود للتطوير). حاويّتا `sahool-rasters`/`sahool-scout-ingest` فارغتان لأنّ تهيئة S3 غير مضبوطة.
يطابق بند خطّة object-store المؤجَّل — ليس عطلاً في التطوير.

**الحلّ التشغيليّ (إن أُريد تخزين قابل للخدمة عبر الشبكة):**
```bash
# احقن تهيئة S3/MinIO في بيئة raster-service (عبر مدير الأسرار، لا في ملفّ متعقَّب):
#   S3_ENDPOINT_URL=http://v22-sahool-minio-1:9000
#   S3_BUCKET=sahool-rasters   AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY=<من الأسرار>
# ثمّ أعِد المعالجة/backfill؛ العناوين تصبح s3:// بدل file://.
```
> بعد التفعيل الحقيقيّ لـS3، ميِّز فشل الرفع الحقيقيّ عن «غير مُهيّأ عمداً» (بند 2.E في خطّة الرستر المؤجَّلة).

---

## بعد المعالجة — تحقّق سلوكيّ

```bash
# 1) أعِد التشغيل لالتقاط كود #657
docker restart v22-sahool-raster-service-1 v22-sahool-scout-ingest-projection-1
# 2) لا مزيد من حلقة إعادة تشغيل العامل (Finding 4):
docker ps --filter name=v22-sahool-scout-ingest-projection-1 --format '{{.Status}}'  # Up مستقرّ، لا Restarting
# 3) لا مزيد من 'toordinal' في سجلّ raster (Finding 2):
docker logs --since 5m v22-sahool-raster-service-1 2>&1 | grep -c toordinal   # ⇒ 0
# 4) لحقل مُسجَّل فعليّاً بعد backfill: /available-dates يعيد التواريخ، والبلاطات ليست شفّافة.
```

**المصادر:** تقرير التشخيص (جلسة 2026-07-26) · PR #657 (`75b3ad5`) · `sahool-brain/runbooks/pg16-staging-activation.md`.

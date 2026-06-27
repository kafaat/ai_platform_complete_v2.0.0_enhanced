# إصلاح خطأ تعذّر تحميل الحقول — /fields 503

## السبب المباشر
من صورة Network كانت الطلبات التالية ترجع 503:

- `/api/v1/fields`
- `/api/v1/farms`
- `/api/v1/devices`
- `/api/v1/alerts`

بينما مسارات لا تعتمد على قاعدة الحقول مثل config/weather كانت تعمل. هذا يطابق حالة أن `sahool-platform` يعمل، لكن `DATABASE_URL` داخله فارغ/غير مضبوط، فيرجع كل endpoint معتمد على PostgreSQL بـ 503.

## الإصلاح المنفذ
تم تعديل ملفات Docker Compose حتى لا تبدأ `sahool-platform` بدون اتصال قاعدة صالح:

### docker-compose.v9.yml
- قبل الإصلاح:
  - `DATABASE_URL: ${DATABASE_URL:-}`
  - `JOBS_DATABASE_URL: ${JOBS_DATABASE_URL:-}`
- بعد الإصلاح:
  - `DATABASE_URL` يبنى افتراضياً من `sahool_app + APP_DB_PASSWORD`
  - `JOBS_DATABASE_URL` يبنى افتراضياً من `sahool_jobs + JOBS_DB_PASSWORD`

### docker-compose.fixed.yml
- أضيف default محلي لـ `DATABASE_URL` يستخدم `sahool_user + DB_PASSWORD` كما يتوافق مع وضع التطوير في fixed compose.

## اختبار الحماية
أضيف اختبار:

- `tests/test_platform_db_compose_contract.py`

ويمنع رجوع مشكلة `DATABASE_URL` الفارغ.

## بعد تنزيل النسخة المحدثة
شغّل:

```bash
docker compose -f docker-compose.v9.yml up -d --build sahool-migrate sahool-platform nginx
```

ثم تحقق:

```bash
curl -i http://127.0.0.1/api/v1/fields
curl -i http://127.0.0.1/readyz
```

إذا بقي 503، نفذ:

```bash
docker logs sahool-platform --tail 150
docker logs sahool-migrate --tail 150
```

السبب المتبقي حينها سيكون غالباً فشل هجرات أو قاعدة قديمة تحتاج إعادة تطبيق migrations.

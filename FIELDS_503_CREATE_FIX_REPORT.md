# إصلاح 503 عند حفظ الحقل

## السبب المحتمل
بعد إصلاح قراءة الحقول، بقي مسار إنشاء الحقل يفشل لأن إنشاء الحقل يستدعي إسقاطاً مشتقاً:
`recompute_field_state()` داخل نفس معاملة `POST /api/v1/fields`.

على قواعد موجودة جزئياً أو ترحيلات لم تكتمل، قد تغيب أعمدة مثل:
- `fields.planting_date`
- `field_state.agronomic`
- أعمدة الحقول الموسعة أو `geometry`

فيتحول إنشاء حقل صحيح إلى 503 رغم أن صف الحقل نفسه قابل للحفظ.

## ما تم إصلاحه
1. تأكيد وجود `asyncpg` في requirements.
2. إضافة `JOBS_DB_PASSWORD` و`JOBS_DATABASE_URL` إلى `.env`.
3. جعل تطبيق الترحيلات أكثر تحملاً لإعادة التشغيل على قاعدة موجودة: `ON_ERROR_STOP=0`.
4. إضافة ترحيل `v104_fields_create_contract.sql` لضمان أعمدة عقد إنشاء الحقل.
5. جعل `field_state` projection best-effort أثناء إنشاء الحقل، حتى لا يكسر إدخال الحقل.
6. جعل فحص التداخل يتدهور بأمان عند غياب عمود `geom` أو PostGIS.
7. إضافة اختبارات ثابتة تحرس هذه العقود.

## بعد التحديث
شغّل:

```bash
docker compose -f docker-compose.v9.yml up -d --build sahool-migrate sahool-platform nginx
```

ثم جرّب إنشاء الحقل مرة أخرى.

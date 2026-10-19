# قبول مسار الموافقة في مختبر معزول

يغطي هذا الدليل `F-GLOBAL-08` من تدقيق المالك: اختبار
`POST /v1/approve/{workflow_id}` دون الوصول إلى قاعدة تشغيل أو جهاز.
لا يوجد مسار sandbox جديد في خدمة الإنتاج، ولا راية تتجاوز المصادقة.

## تشغيل القبول المحلي

من جذر المستودع، بعد تثبيت `tests_v9/requirements-test.txt` في بيئة اختبار:

```bash
env -u DATABASE_URL -u TEST_DATABASE_URL python3 -m pytest -q \
  tests_v9/test_guardrails_contract.py \
  -k approval_http_sandbox_is_scoped_and_has_no_external_io
```

المتوقع **12 حالة ناجحة بلا تخطٍّ**. الاختبار ينشئ workflow في `Store`
داخل الذاكرة، ثم يستدعي راوتر الخدمة الحقيقي عبر ASGI وJWT الاختباري.
الحالات الست تُنفذ للموافقة والرفض: خبير مخول، مستأجر مختلف، تخصص غير مناسب،
workflow منتهي، معرف غير موجود، وتوكن مفقود. يؤكد الاختبار هوية صاحب القرار
وعدم تسجيل قرار في الحالات المرفوضة ومسح سياق المستأجر بعد المعاملة.

قبل إنشاء workflow يثبت الاختبار موانع لـ`asyncpg.create_pool` و`asyncpg.connect`
و`socket.socket.connect`: محاولة اتصال عبرها تفشل الاختبار. هذه حدود عزل الاختبار
المقيس وليست جدار حماية لنظام التشغيل. لا تمرر أسرار تشغيل لهذا الجناح.

النجاح يثبت عقد HTTP والهوية والمنطق مع مخزن بديل؛ **لا يثبت إدامة PostgreSQL
أو RLS أو تنفيذ أمر مادي**. لا تنفذ طلبات موافقة تجريبية على staging أو production
بمعرفات workflows قائمة.

## قبول الإدامة الموجود بالفعل

`tests_v9/test_db_wiring.py::TestHILGetStatus::test_create_then_get_status`
يشغّل إنشاء وقراءة وموافقتين ومنع التكرار والعزل تحت دور
`NOSUPERUSER NOBYPASSRLS`، على مخطط الهجرات القانوني. وظيفة `Integration Tests`
في `.github/workflows/ci.yml` توفر قاعدة PostgreSQL/PostGIS مؤقتة وتضبط
`HIL_CERTIFICATION_REQUIRED=1`: غياب القاعدة يفشل هذا الشاهد بدلاً من تخطيه.
الاختبار يغير مخطط الصلاحيات ويكتب بيانات اختبار؛ موضعه قاعدة مؤقتة فقط.

رُوجع شاهد ناجح سابق على الرأس `b21257edcc42c79d5dc03fa678facd8e2a603fcd`:
[Integration Tests / 117786415481](https://github.com/kafaat/ai_platform_complete_v2.0.0_enhanced/actions/runs/39165148122/job/117786415481)،
السطر المؤرخ `2026-10-18T20:53:32.5302352Z` يسجل الاختبار المحدد `PASSED`.
للجناح الأوسع تخطيات معلنة؛ نجاح هذا الاختبار لا يعني نجاح كل حالة في الجناح.
لم يُعد تشغيل PostgreSQL محلياً في مراجعة 19 أكتوبر؛ لا Docker أو PostgreSQL هنا.

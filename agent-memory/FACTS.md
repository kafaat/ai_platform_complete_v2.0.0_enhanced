# حقائق SAHOOL غير القابلة للجدل (FACTS.md)

> كلّ سطر هنا **مُتحقَّق منه مقابل كود هذا المستودع** (لا منقول من تقارير v05).
> آخر تحقّق: 2026-06-18. عند الشكّ: اكتشف من الكود، لا تفترض، ثمّ حدّث هذا الملفّ.

## المعماريّة
- **النواة النقيّة + الغلاف الرفيع:** منطق القرار الزراعيّ يعيش في وحدات نقيّة حتميّة (dataclasses، بلا I/O، بلا numpy، docstrings عربيّة) تحت `services/sahool-platform/core/`. الخدمات المصغّرة غلافٌ رفيع للإدخال/الإخراج فقط. اختبر النواة بلا docker.
- **قاعدة البيانات: asyncpg وليس SQLAlchemy.** الأنماط: `ANY($1::text[])` لقوائم IN، `CAST($1 AS jsonb)` (لا `::jsonb`)، `statement_cache_size=0`.
- **NATS:** كلّ المواضيع ببادئة `sahool.` (مثل `sahool.weather.forecast.updated`). موضوع بلا بادئة يكسر الـstream.
- **نمط Outbox:** النشر على NATS **بعد** إتمام معاملة القاعدة (نجاح القاعدة أوّلاً، ثمّ `js.publish`). فشل النشر لا يُفقِد الكتابة.

## أدوار قاعدة البيانات (RLS متعدّد المستأجرين)
- **`sahool_app`** — `NOSUPERUSER NOBYPASSRLS`. مسارات التطبيق/المستخدم. معزول بـRLS.
- **`sahool_jobs`** — `BYPASSRLS`. مهامّ الخلفيّة العابرة للمستأجرين فقط، عبر `JOBS_DATABASE_URL`.
- **`sahool_user`** — المالك/superuser. الهجرات فقط.
- **لا تستخدم أبداً postgres superuser DSN داخل الخدمات.** weather-polygon-worker و weather-signal-engine يتّصلان بـ`sahool_jobs` عبر `JOBS_DATABASE_URL`.
- حارس RLS فاشل-الإغلاق: `shared/db_role_guard.py` يرفض الإقلاع إن كان الدور يتجاوز RLS (إلّا `SAHOOL_ALLOW_RLS_BYPASS_ROLE=1` للتطوير).

## الشبكة/المنافذ (هذا المستودع — `docker-compose.v9.yml`)
- **الدخول العامّ الوحيد هو `sahool-nginx` على `443`.** معظم الخدمات **لا تكشف منفذ مضيف**؛ تتواصل داخليّاً عبر اسم الخدمة على منافذ الحاوية (`8000`/`8001`)، مثل `http://sahool-weather-service:8000`، `http://sahool-raster-service:8001`. التوجيه عبر nginx.
- المنصّة (`sahool-platform`) فحص صحّتها على `http://localhost:8000/readyz` داخل الحاوية.
- ⚠️ **لا يوجد في هذا المستودع خدمة `weather-map-api` ولا منفذ `8210`/`8084`.** هذه من بيئة v05 المحليّة فقط — لا «تصلحها» هنا.

## الهجرات (Migrations)
- الترقيم تصاعديّ بلا فجوات؛ `migrations/MANIFEST.txt` **مرتّب بالإلحاق** (لا تُعِد ترتيبه). الأحدث: `v75_work_orders.sql`.
- **هجرة الطقس الصحيحة هي `v74_weather_intelligence.sql`.** لا تُنشئ `migrations/002_weather_intelligence.sql` ولا أيّ ترقيم `00x` — يكسر التسلسل.
- جداول المستأجرين: `ENABLE` + **`FORCE ROW LEVEL SECURITY`**، وسياسة tenant تحتوي حرفيّاً `current_setting('app.current_tenant', true)` (يفرضه اختبار التكامل `test_tenant_policy_uses_current_setting`).

## المخطّط (انظر `SCHEMA_FACTS.md` للتفصيل)
- `fields.field_id` **`VARCHAR(50)`/TEXT وليس UUID** (راجع v18/v74). المفاتيح الخارجيّة للحقل نصّيّة.
- الحقل يستخدم العمود `geom` (geometry, 4326) للاستعلام المكانيّ (`ST_Within`) — أُضيف في `v43`. (يوجد أيضاً عمود `geometry` نصّيّ قديم للمصدر.)
- **لا تفترض أسماء أعمدة الطقس** — اكتشف المخطّط من `v74_weather_intelligence.sql` أوّلاً.

## المسارات
- تطبيق Flutter: **`mobile/sahool_app/`** (`mobile/sahool_app/pubspec.yaml`).
- نواة المنطق: `services/sahool-platform/core/`. اختباراتها: `services/sahool-platform/tests/`.
- اختبارات الوحدة المعلَّمة `unit`: `tests_v9/` (انظر `TEST_FACTS.md`).

## التبعيّات
- **افحص الثغرات قبل أيّ إضافة/ترقية** في `requirements*.txt`: `pip-audit -r <file>` محليّاً.
- المسار الحرج الذي يحجبه `pip-audit` في CI: `services/sahool-platform/api/requirements.txt`، `services/auth/requirements.txt`، `services/guardrails-engine/requirements.txt`، `requirements_real.txt`. (وليس `tests_v9/requirements-test.txt`.)
- `bandit -r services/ bots/ agents/ --severity-level high` يحجب على HIGH فقط.

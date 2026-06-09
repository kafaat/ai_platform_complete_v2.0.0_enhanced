# تقرير مراجعة الكود — منصة SAHOOL v9 الزراعية-المناخية

> مراجعة شاملة لـ 806 ملفًا (362 Python، microservices، Flutter، React، ESP32).
> كل النتائج مُتحقَّق منها بقراءة الكود الفعلي. المراجع بصيغة `file:line`.

## الخلاصة التنفيذية

المشروع **ناضج وموثّق بعناية**، ونظافة البنية التحتية جيدة (أسرار عبر
`${VAR:?required}`، منافذ مربوطة بـ`127.0.0.1`، JWT يفشل-مغلقًا في الإنتاج،
كلمات مرور bcrypt، استعلامات SQL مُعاملة بالكامل — **لا حقن SQL، ولا أسرار
مكشوفة، ولا `eval/exec/pickle`، ولا CORS عام**).

لكن توجد **5 مشاكل حرجة** تُبطل بعضًا من أهم ضمانات الأمان والصحة، أبرزها
تجاوز مصادقة كامل يلغي عزل المستأجرين، ومجموعة اختبارات 62% منها لا تفحص شيئًا.

| الفئة | حرج | عالٍ | متوسط | منخفض |
|------|:---:|:---:|:----:|:----:|
| العدد | 5 | 9 | 12 | 12 |

---

## 🔴 حرج (Critical)

### C1 — تجاوز مصادقة كامل: تسجيل الدخول يُصدر JWT بأي دور/مستأجر دون كلمة مرور
`services/sahool-platform/api/main.py:369-396` (`/api/v1/auth/login`) و`:435-457` (`/signup`)

تستقبل النقطة `LoginRequest(user_id, tenant_id, role, name_ar)` وتستدعي
`create_token(user)` مباشرة — **بلا كلمة مرور، بلا تحقق، بلا استعلام قاعدة
بيانات**. الـ`role` يُؤخذ من جسم الطلب ويُقبل أي قيمة من `UserRole` (بما فيها
`owner` الأعلى صلاحية)، و`tenant_id` يختاره المهاجم.

**الأثر:** أي شخص يصل للمنصة يرسل
`{"user_id":"x","tenant_id":"<any>","role":"owner"}` فيحصل على JWT صالح موقّع.
كل التفويض اللاحق و عزل المستأجرين عبر RLS (`tenant_connection` يبذر RLS من
`user.tenant_id`) يثق بهذه الادعاءات → **قراءة/كتابة بيانات أي مستأجر بصلاحية
مالك**. النقطة **غير محميّة بـ`SAHOOL_ENV`** (فحص البيئة يحكم قوة سر JWT فقط).

**الإصلاح:** استبدلها بتحقق فعلي من بيانات الاعتماد مقابل خدمة `services/auth`
(التي تنفّذ ذلك بشكل صحيح: bcrypt + DB + قفل الحساب). كحدّ أدنى: عطّل
`/login` و`/signup` تمامًا عند `SAHOOL_ENV=production`، ولا تقبل
`role`/`tenant_id` من العميل إطلاقًا — استنتجها من الهوية المُصادَقة.

### C2 — تمهيد قاعدة بيانات جديدة يتخطّى 7 ترحيلات بصمت، منها عزل المستأجرين (RLS)
`migrations/MANIFEST.txt` مقابل محتوى المجلد (18 ملف SQL)

يسرد `MANIFEST.txt` 11 ملفًا فقط، بينما المجلد يحوي 18. الناقص يشمل:
`v9_rls_tenant_isolation.sql` (عزل بيانات المستأجرين عبر RLS) و
`v9_append_only_enforcement.sql` (سلامة التدقيق/عدم القابلية للتعديل) و5 أخرى.
`bootstrap_postgres.sh` يطبّق الترحيلات بالتكرار على MANIFEST فقط ويتخطّى ما
ليس فيه بتحذير. ⇒ **قاعدة إنتاج جديدة تقوم دون عزل مستأجرين ودون فرض
append-only** — تسرّب بيانات متعدّد المستأجرين وانهيار سلامة التدقيق.

**الإصلاح:** أضف الـ7 ملفات الناقصة إلى MANIFEST بالترتيب الصحيح للاعتماديات،
واجعل `validate_migrations.py` يُرجع رمز خطأ غير صفري عند وجود ملفات "extra"
واربطه بالـCI.

### C3 — خدمة edge-inference لا تُستورد أصلًا (NameError)
`services/edge-inference/main.py:23`

```python
app = FastAPI(lifespan=lifespan, title="SAHOOL Edge Inference", ...)
```
`lifespan` معرّف لاحقًا (سطر 203). عند سطر 23 الاسم غير موجود ⇒
`NameError: name 'lifespan' is not defined` عند الاستيراد. **الخدمة لا تُقلع.**
**الإصلاح:** انقل تعريف `lifespan` فوق استدعاء `FastAPI(...)`.

### C4 — كل استدعاءات MCP عبر المشرف معطّلة (سوء استخدام retry_request)
`services/supervisor-agent/mcp_client.py:46,81` ⇐ `shared/helpers.py:294`

```python
resp = await retry_request(client.get("/mcp/v1/tools"))   # كائن coroutine لا callable
```
`retry_request(coro_fn, *args)` يتوقّع **دالة** ويفعل `await coro_fn(*args)` داخل
حلقة إعادة المحاولة. هنا يُمرَّر **كائن coroutine** ⇒ `TypeError: 'coroutine'
object is not callable`، ولو نجح لكانت إعادة المحاولة تعيد انتظار نفس الـ
coroutine (ممنوع). **كل أدوات المشرف معطّلة.**
**الإصلاح:** `retry_request(client.get, "/mcp/v1/tools")` (مرّر الدالة والوسائط منفصلة).

### C5 — 62% من الاختبارات لا تفحص شيئًا (لا يمكن أن تفشل)
`tests_v9/test_roadmap_phase23.py` (+9 ملفات)

183 من 293 دالة اختبار (62%) **بلا أي `assert`**. النمط:
```python
def test_x():
    r = []
    if cond: r.append(("✓", "..."))   # يُلحق عند النجاح فقط
    return r                           # pytest يتجاهل القيمة ⇒ نجاح دائم
```
عند الفشل لا يُلحَق شيء وتنجح الدالة. بوّابة `--cov-fail-under=50` تُرضى بتغطية
الاستيراد فقط ⇒ **ثقة زائفة**: انحدارات في إحصاء التجارب، توازن المياه، التسميد،
تشخيص الأمراض، RLS، append-only، idempotency لن تُكتشف.
**الإصلاح:** حوّل `if cond: r.append(...)` إلى `assert cond, "msg"`.
(ملاحظة: ~10 ملفات اختبار سليمة فعلًا: auth، security، rls_isolation، mcp، إلخ.)

---

## 🟠 عالٍ (High)

### H1 — نقاط أتمتة الطقس غير مُصادَقة + تسرّب كاش عبر المستأجرين
`api/main.py:2914` (`/automation/weather/register`)، و`:2929 /cached`، `:2941 /status`

`POST .../weather/register` بلا `Depends(get_current_user)`. يعدّل singleton عام
(`weather_automation.py:68`) ويكتب في جدول عام **بلا `tenant_id`**. أي مجهول
يسجّل إحداثيات ويقرأ كاش طقس أي مستأجر عبر `/cached` و`/status` غير المحميّتين.
**الإصلاح:** أضف اعتماد المستخدم واعزل السجل/الكاش بـ`tenant_id` (نظير الصور في
`:2956` يفعل ذلك صحيحًا — احتذِ به).

### H2 — الواجهة تُلفّق توصيات زراعية عند فشل الخادم
`frontend/src/services/api.ts:62-69` (`tryReal()`)

أي خطأ خادم (500/timeout/شبكة) يُرجع بصمت بيانات وهمية ثابتة لا تُميَّز عن
الحقيقية: `fetchNitrogenRecommendation` يُرجع `87.5 kg N/ha` ثابتة (سطر 228)،
وقراءات تربة/مؤشرات ملفّقة، و`MOCK_DASHBOARD`. لمنصة قرار زراعي، عرض توصيات
تسميد/ريّ مخترعة أثناء انقطاع **يسبّب ضررًا زراعيًا وماليًا حقيقيًا**.
**الإصلاح:** اقصر الـmock على `MOCK_MODE` فقط؛ أظهر حالة خطأ/قديمة بدل قيم ملفّقة.

### H3 — خطأ مجال رياضي في معادلة LAI (`math.log` لعدد سالب للمحاصيل السليمة)
`services/vegetation-analysis-service/main.py:264`
```python
lai = max(0, -math.log(max(0.001, (0.69 - ndvi) / 0.59)) / 0.5)
```
لأي NDVI > 0.69 (محاصيل ممتازة — الحالة الشائعة) يصبح البسط سالبًا فيُثبّت عند
0.001 ⇒ LAI يتشبّع عند ~13.8 لكل الغطاء السليم (بلا سقف واقعي ~8)، والعلاقة
مقلوبة. قارن التنفيذ الصحيح في `sentinel_hub/vegetation_real.py:397-410`.
**الإصلاح:** ثبّت NDVI دون 0.69 وضع سقفًا على المخرج.

### H4 — EVI/SAVI بلا حارس قسمة على صفر ⇒ inf/ZeroDivisionError
`services/vegetation-analysis-service/main.py:258-259`، `services/raster-service/main.py:909-911`

NDVI/NDWI وغيرها تضيف `eps=1e-10` لكن مقام EVI
(`B08 + 6*B04 - 7.5*B02 + 1`) قد يقترب من الصفر ⇒ `inf`/قيم ضخمة بلا حارس
(المسار العددي قد يرمي `ZeroDivisionError`؛ مسار numpy يُنتج `inf/nan` بصمت يتسرّب للإحصاءات).
**الإصلاح:** أضف `+eps`/ثبّت المقام.

### H5 — تعارض مخطّط في خدمة التربة: أعمدة NPK تُقرأ ولا تُكتب أبدًا
`services/soil-service/main.py:82` (SELECT) مقابل `:110-120` (INSERT) والنموذج `:91-100`

`get_readings` يقرأ `n_ppm, p_ppm, k_ppm` لكن `ingest_reading` لا يكتبها والنموذج
`SoilReading` لا يحوي هذه الحقول. NPK **غير قابل للإدخال**، وإن لم تكن الأعمدة
موجودة في الجدول فإن **كل قراءة ترمي** `UndefinedColumnError`.
**الإصلاح:** أضف الحقول للنموذج والـINSERT، أو أزلها من SELECT.

### H6 — تحليل استجابة Open-Meteo يفترض مصفوفات كاملة الطول ومتراصفة
`services/sahool-platform/api/connectors/openmeteo.py:192-205,239-252`؛ والأسوأ في `wofost_real/wofost_engine.py:110-117`

الحارس `[0]*len(dates)` يعمل فقط عند **غياب المفتاح كليًا**. إن وُجد المفتاح
أقصر من `dates` (Open-Meteo يُرجع مصفوفات مُسنّنة أو `null` في ذيل أرشيف ERA5
المتأخّر ~5 أيام) ⇒ `IndexError` أو تمرير `None` لحقل float. ونسخة WOFOST تستخدم
`d["..."][i]` بلا `.get` إطلاقًا ⇒ `KeyError/IndexError`.
**الإصلاح:** استخدم `zip_longest` أو احرس كل فهرسة؛ ولا تطلب أرشيفًا حتى `today`.

### H7 — توازن مياه الريّ في WOFOST غير متّسق فيزيائيًا (ETc لا يُطرح أبدًا)
`wofost_real/wofost_engine.py:261-266,315`
```python
w_demand = etc * (1000 / 1)        # محسوب ولا يُستخدم؛ "1000/1" عبثي
if irrigation:
    w_soil = max(w_wp, w_soil)     # يملأ الفجوة لكن لا يطرح ETc أبدًا
```
تحت `irrigation=True` تُملأ التربة بالمطر فقط وتُحدّ عند الذبول؛ **ETc لا يُطرح**
⇒ فرع إجهاد الماء لا يُفعَّل و`water_factor` يبقى 1.0 — سيناريوهات الريّ لا تُنمذِج
الاستنزاف. وسطر 315 فرعا الشرط متطابقان عدا ×1.1.
**الإصلاح:** استنزف `w_soil` بـETc وطبّق الريّ لإعادة الملء نحو السعة الحقلية.

### H8 — طرح datetime واعٍ من ساذج ⇒ 500 على مدخل ISO صالح
`api/main.py:989` (`ndvi_confidence`)، `:1090` (`temporal_check`)

`datetime.fromisoformat(s.replace("Z","+00:00"))` يُنتج datetime **ساذجًا** إذا
لم يرسل العميل إزاحة (مثل `"2026-02-01"`)، ثم يُطرح من `datetime.now(timezone.utc)`
(واعٍ) ⇒ `TypeError` غير معالَج = 500 على مدخل موثّق كصالح.
**الإصلاح:** `if obs.tzinfo is None: obs = obs.replace(tzinfo=timezone.utc)`؛ وأرجع 422 للمدخل غير القابل للتحليل.

### H9 — تثبيت asyncpg في agents/notification يكسر بناء Python 3.13
`agents/notification/requirements.txt:3` ⇒ `asyncpg>=0.29.0`

الملف الوحيد الذي فات توحيده وفق وثيقة المشروع نفسها
(`DEPENDENCY_CONSISTENCY_AUDIT.md`) إلى `>=0.30.0,<0.32.0`. الإصدار 0.29 **يفشل
بناؤه على 3.13**. يبني اليوم لأن Dockerfile على 3.11 فقط.
**الإصلاح:** `asyncpg>=0.30.0,<0.32.0`.

---

## 🟡 متوسط (Medium)

| # | الموقع | المشكلة | الإصلاح |
|---|--------|--------|---------|
| M1 | `api/prescriptions.py:228,285` | `total_n / sum(area_ha)` يقسم على صفر إذا كل المناطق `area_ha=0` ⇒ 500 | احرس `total_area>0` + `Field(gt=0)` |
| M2 | `api/main.py:3143` `field_intelligence_analyze` | endpoint مُتزامن `def` يستدعي `httpx.Client` 3 مرات تسلسليًا × 20s ⇒ يحتل عامل threadpool ~60s؛ تحت الحمل يُجمّد كل النقاط المتزامنة | اجعله `async` + `AsyncClient` + `asyncio.gather` |
| M3 | `confidence_engine.py:104-111` | ثقة التغطية متقطّعة عند 0.5 (0.49→0.245 مقابل 0.50→0.50) وتعاقب البيانات الصالحة | خريطة متّصلة رتيبة |
| M4 | `sentinel_hub/vegetation_real.py:58-81`، `vegetation-analysis-service/main.py:78-99` | كاش توكن Sentinel-Hub في متغيّر عام بلا قفل ⇒ تسابق وجلب توكن مكرّر تحت التزامن | قفل asyncio حول التحديث |
| M5 | `shared/helpers.py:225` | مفتاح كاش يستخدم `hash(str(args))` غير الحتمي عبر العمليات (PYTHONHASHSEED) ⇒ الكاش لا يُشارَك بين العمّال + تصادمات | `hashlib.sha256` |
| M6 | `sentinel_hub/vegetation_real.py:716` | ملخّص `/timeseries` يقسم على `len(series)` بلا حارس ⇒ `ZeroDivisionError` على `daily` فارغ | `max(1, len(series))` |
| M7 | `services/raster-service/main.py:247-250` | `_stac_search_radar` يفتح `httpx.AsyncClient` خام يتجاوز طبقة المرونة (retry/cache/fallback) بعكس أشقّائه | استخدم `_stac.search(...)` |
| M8 | `vegetation-analysis-service/main.py:399-400` | افتراضات `date_from/to` تُقيَّم عند الاستيراد ⇒ "اليوم" مُجمّد حتى إعادة التشغيل | افتراض `None` واحسب داخل المعالج |
| M9 | `frontend/src/services/api.ts:34,44-47` | JWT في `localStorage` (قابل للقراءة بـXSS) وبلا تدوير refresh | httpOnly cookie أو توكن بالذاكرة + refresh |
| M10 | `mobile/.../api_service.dart:141-151` | `_isTokenExpired` يفشل-مفتوحًا (يُرجع `false` عند خطأ التحليل) بعكس `auth_service.dart:79` | اجعله يفشل-مغلقًا |
| M11 | `frontend/src/sections/SettingsPage.tsx:38-41` | "حفظ" لا يحفظ شيئًا (مفتاح Claude/اللغة يُهمَل) + جمع مفتاح `sk-ant-` في المتصفح نمط خاطئ | احفظ خادميًا أو أزل النموذج |
| M12 | `.github/workflows/ci.yml` + requirements | `pip install -r requirements.txt` لملف غير موجود (الاسم `requirements_real.txt`)؛ و`alembic/sqlalchemy` غير معلنين رغم توثيق `alembic upgrade head` | صحّح الاسم + أضف alembic/SQLAlchemy لمتطلبات الأدوات |

---

## 🟢 منخفض (Low)

| # | الموقع | المشكلة |
|---|--------|--------|
| L1 | `event_replay.py:95,185` مقابل `event_upcasting.py:24` | تعارض تسمية الأحداث: `operation.fertilizer.applied` مقابل `operation.fertilization.completed` ⇒ عدّادات/مُحدّثات لا تُفعَّل |
| L2 | `event_upcasting.py:54,66-70` | مقارنة إصدارات نصية معجمية: `"1.10" < "1.2"` ⇒ سلسلة الترقية تختلّ بعد عشرات الإصدارات الفرعية |
| L3 | `api/zones_kmeans.py:116-125` | عند `n_zones≥4` تُكتب مراكز "medium" المتعدّدة فوق بعضها ⇒ ملخّص `zone_centers` مضلّل |
| L4 | `supervisor-agent/tool_contracts.py:332` | `record_complete` يكتب `tool_id=""` فلا يُملأ أبدًا ⇒ سجلّ تدقيق المُشغّلات يُسقط أحداث الإكمال |
| L5 | `services/guardrails-engine/main.py:300` | مقارنة توكن الخدمة بـ`!=` لا `hmac.compare_digest` (قناة توقيت نظرية) |
| L6 | `services/odoo-bridge/main.py:489-494` | مُحقّق HMAC ميّت (`pass`) يوحي بتحقّق توقيع غير موجود (النقطة الفعلية تتحقّق صحيحًا) |
| L7 | `docker-compose.v9.yml` (minio/ollama/titiler/prometheus/grafana/jaeger) | وسوم `:latest` في إنتاج ⇒ بناء غير قابل لإعادة الإنتاج |
| L8 | `docker-compose.unified.yml`/`.fixed.yml` | فجوات healthcheck (v9 مغطّاة) — يُفضّل حذف المتغيّرات القديمة |
| L9 | `.github/workflows/ci.yml` | mypy يفحص خدمتين فقط (auth، guardrails) من ~20 ⇒ أمان الأنواع غير مفروض عمليًا |
| L10 | `raster-service/main.py:436-438,691-692,712-713` | نص بعد أول تعبير تنفيذي ليس docstring ⇒ `__doc__=None` ووصف OpenAPI مفقود |
| L11 | `frontend/.env.local` | ملف بيئة مرفوع (قيم localhost فقط الآن) ⇒ خطر تسرّب سر مستقبلي؛ احرص على تجاهله git |
| L12 | `random_forest/agb_model.py:201` + `vegetation_real.py:370` | R²=0.89 محسوب على عيّنة التدريب (داخل-العيّنة، مبالَغ)؛ وتنفيذا AGB غير متّسقين عدديًا (قسمة ÷100 في أحدهما فقط) |

---

## ✅ نواحٍ مُتحقَّق أنها سليمة

- **حقن SQL:** لا شيء — استعلامات مُعاملة (`$1`/`?`) في كل المسارات؛ قوائم الأعمدة
  الديناميكية في `lite_store.py:422` من قائمة بيضاء داخلية ثابتة.
- **الأسرار:** لا اعتمادات/مفاتيح مكتوبة في الكود؛ كل `.env*.example` قيم نائبة.
- **JWT (خدمة auth):** RS256 مفضّل + HS256 احتياطي ≥32 محرفًا (يفشل-مغلقًا)،
  مع `aud/iss/nbf/exp` وإبطال `jti`، بلا خوارزمية `none`.
- **CORS:** لا `["*"]`؛ افتراضي `localhost:3000`.
- **الدوال الخطرة:** لا `eval/exec/pickle/yaml.load` غير آمن (`yaml.safe_load` مُستخدم).
- **nginx:** TLS1.2/1.3، HSTS، X-Frame-Options، `server_tokens off`، rate-limit.
- **بوت تيليجرام:** توكن من البيئة، لا سكّ توكن، حذف رسالة كلمة المرور، throttling.
- **`tenant_connection`:** يضبط RLS GUCs عبر `set_config(...,true)` داخل المعاملة (آمن للـpool).

---

## أولويات الإصلاح المقترحة

1. **C1** (تجاوز المصادقة) — يُبطل كل ضوابط الأمان؛ أصلحه قبل أي تعريض إنتاجي.
2. **C2** (ترحيلات RLS الناقصة) — تسرّب متعدّد المستأجرين على نشر جديد.
3. **C3 + C4** — فشل صلب: خدمتان معطّلتان كليًا (إصلاح سطر واحد لكل منهما).
4. **C5** — مجموعة الاختبارات تُعطي أمانًا زائفًا؛ بدونها لا تُكتشف الانحدارات.
5. **H1–H8** — أخطاء صامتة تُنتج أرقامًا/توصيات خاطئة دون أن ترمي خطأً.

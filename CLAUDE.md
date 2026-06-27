# دليل المساهمة للوكلاء (Agent / Contributor Guidance)

إرشادات تشغيليّة دائمة لجلسات التطوير المستقبليّة. تُتّبع تلقائيّاً. الهدف: أن يفهم أيّ وكيل
بنية المستودع وسير العمل والاتّفاقات في دقائق، ويُنتج تغييراً يجتاز بوّابات CI من أوّل دفعة.

> **مرجع حيّ:** الدماغ المعرفيّ في [`sahool-brain/`](sahool-brain/index.md) أحدث وأدقّ من أيّ ملخّص.
> ابدأ كلّ جلسة بقراءة `sahool-brain/hot.md` + `sahool-brain/index.md` + الفجوات الحرجة المفتوحة.

---

## ١. ما هذا المشروع؟ (SAHOOL v9)

منصّة زراعة ذكيّة (precision agriculture) لليمن — **معماريّة خدمات مصغّرة (microservices)**
مبنيّة على بيانات حقيقيّة لا محاكاة: صور Sentinel-2/1، طقس Open-Meteo/ERA5، نماذج محاصيل
WOFOST-RUE، ومؤشّرات FAO-56. تفاصيل التحوّل من المحاكاة إلى الحقيقيّ في [`README.md`](README.md).

- **Backend:** Python 3.12 / FastAPI — كلّ خدمة في `services/<name>/` تستمع على المنفذ الداخليّ `8000` (إلّا ما نُصّ عليه).
- **Frontend:** React + TypeScript + Vite + MapLibre/Leaflet (`frontend/`).
- **Mobile:** Flutter / Dart (`mobile/sahool_app/`).
- **البنية التحتيّة:** PostgreSQL + **PostGIS**، Redis، NATS JetStream، MinIO (S3)، Qdrant (متّجهات)، Ollama (LLM محليّ)، MQTT (mosquitto)، nginx (بوّابة عكسيّة).
- **اللغة:** التوثيق والتعليقات ورسائل الـcommit بالعربيّة (مع مصطلحات تقنيّة إنجليزيّة). حافظ على هذا الأسلوب.

---

## ٢. خريطة المستودع

| المسار | المحتوى |
|---|---|
| `services/` | ٢٢ خدمة مصغّرة. الأهمّ: `sahool-platform` (النواة، `/api/v1/*`)، `auth`، `guardrails-engine`، `supervisor-agent`، `mcp_servers`. |
| `services/sahool-platform/` | النواة. `api/` (FastAPI، نمط Hexagonal)، `api/routers/` (نقاط `/api/v1/*` مفكَّكة)، `core/` (منطق المجال)، `tests/` (~١٢٨٢ اختبار منطق صرف). |
| `frontend/` | واجهة React/Vite + e2e (Playwright) + `vitest`. |
| `mobile/sahool_app/` | تطبيق Flutter. |
| `bots/`, `agents/` | بوت تيليجرام، وكيل الإشعارات (NATS + WebSocket). |
| `migrations/` | ترحيلات SQL خام بترتيب `MANIFEST.txt` (~١٠٤ ترحيلاً). **هذا مصدر الحقيقة للمخطّط** (لا alembic للمنصّة). |
| `tests_v9/` | حزمة اختبارات الجذر (~٢٤١ ملفّاً)؛ `testpaths` في `pytest.ini`. |
| `docs/` | الوثيقة المعماريّة + ADRs + التدقيقات + التاريخ + openapi. |
| `sahool-brain/` | الدماغ المعرفيّ الذي يصونه الوكيل (انظر §٦). |
| `docker-compose.v9.yml` | **ملفّ الإنتاج القانونيّ (canonical).** ملفّات compose أخرى للاختبار/الخفيف/ERP. |
| `nginx/nginx.v9.conf` | توجيه البوّابة (route → upstream). انظر [`docs/NGINX_ROUTING.md`](docs/NGINX_ROUTING.md). |
| `Makefile` | خطّ أنابيب التحقّق المرحليّ (offline → live). |

كتالوج الخدمات الكامل (منافذ، متغيّرات، تبعيّات، خريطة nginx):
[`sahool-brain/architecture/service-map.md`](sahool-brain/architecture/service-map.md).

---

## ٣. الاختبارات — ابدأ بـ`pytest -m unit`

- **الافتراضيّ للتغذية الراجعة السريعة محليّاً:** `pytest -m unit`. اختبارات منطق صرف بلا خدمات، وعليها تُبنى بوّابة CI (وظيفة *Unit Tests*: `pytest -v -m unit --cov=services` + أرضيّة تغطية `--cov-fail-under=20`).
- **العلامات (markers) في `pytest.ini`:** `unit` / `integration` / `security` / `slow` / `mcp`، و`testpaths = tests_v9`، و`asyncio_mode = auto`.
- **اختبارات المنصّة منفصلة:** تقع في `services/sahool-platform/tests/` (خارج `testpaths`) وتُشغَّل من جذر المنصّة: `cd services/sahool-platform && PYTHONPATH=. pytest tests -q` (بوّابة CI *Platform Unit Tests* مع راتشِت تغطية في `.coveragerc`).
- **احتفظ بـ`-m integration` لِما بعد رفع الخدمات/PostGIS** (تتطلّب Postgres+PostGIS وRedis قيد التشغيل + تطبيق الترحيلات). لا تُشغّلها كافتراضيّ.
- **حارس تفكيك الراوترات:** `services/sahool-platform/tests/test_router_decomposition_guard.py` (مُعلَّم `unit`) يمنع انحدار تفكيك `main.py` إلى `api/routers/`: (١) لا نقطة `/api/v1/*` بـ`@app` في `main.py`، (٢) لا router يتيم، (٣) لا تكرار (مسار، طريقة). **أبقِه أخضر عند تعديل نقاط `/api/v1/*`.**
- **الواجهة:** `cd frontend && npm run typecheck && npm run test` (vitest) و`npm run e2e` (Playwright، هرمسيّ — يعترض الشبكة).
- **الموبايل:** `cd mobile/sahool_app && flutter analyze --no-fatal-infos --no-fatal-warnings && flutter test`.

---

## ٤. الاتّفاقات الأساسيّة (Conventions)

### تنسيق ولينت Python — موحّد على ruff
- `ruff.toml`: `target py311`، `line-length 100`، قواعد `E/F/I/UP/B/W`. CI يثبّت **`ruff==0.15.8`** (الإصدار مثبَّت عمداً — انجراف الإصدار يكسر التنسيق في CI).
- شغّل قبل الدفع: `ruff check services/ bots/ agents/ tests_v9/` و`ruff format --check ...`.
- `mypy` إرشاديّ فقط (أسماء مجلّدات الخدمات مُشرطَنة، ليست حزم بايثون صالحة).

### نمط النواة (sahool-platform)
- **Hexagonal:** `HTTP route → ApiRequest dict → api_adapter.handle_*() → ApiResponse → HTTP`. المنطق محايد عن الإطار في `core/`؛ FastAPI طبقة رقيقة في `api/`.
- **نقاط `/api/v1/*` تذهب إلى `api/routers/<domain>.py`** وتُضمَّن عبر `app.include_router`. تبقى في `main.py` فقط نقاط البنية: `/healthz`, `/readyz`, `/internal/*`, الجذر.

### قاعدة البيانات والعزل (Multi-tenant)
- المخطّط عبر ترحيلات SQL خام في `migrations/` بترتيب `MANIFEST.txt` — **عدّل بإضافة ترحيل جديد، لا بتعديل قديم**، وحدّث `MANIFEST.txt`.
- **عزل المستأجرين بـRLS:** الجداول مفلترة بـ`tenant_id` عبر `app.current_tenant`. شغّل DB كـ`sahool_app` (non-superuser) وإلّا يُتجاوَز RLS. عمّال الخلفيّة (worker) يستخدمون دور `BYPASSRLS` منفصل عمداً.
- جداول جيومكانيّة (PostGIS): `field_boundaries`، `ndvi_timeseries`، إلخ.

### الأمان
- المصادقة JWT عبر خدمة `auth`. أسرار عبر متغيّرات بيئة (`JWT_SECRET`/`SAHOOL_JWT_SECRET`/`SAHOOL_AGENT_TOKEN`) — **لا تُضمِّن أسراراً في الكود**. انظر `.env.example`.
- `guardrails-engine` يطبّق سياسة **fail-closed** (التحقّق/الحوكمة).

---

## ٥. التبعيّات — افحص الثغرات قبل أيّ إضافة أو ترقية

- **قبل** إضافة أو ترقية أيّ شيء في `requirements*.txt`، شغّل `pip-audit -r <file>` محليّاً. الفشل المتأخّر في CI مكلِف.
- **بوّابة CI (*Security Scan*):**
  - `pip-audit` يحجب الدمج على المسار الحرج (يغطّي الآن معظم خدمات `services/*/requirements.txt` + `requirements_real.txt`). يُستثنى `services/local-ai-rag/requirements.txt` عمداً (ثغرة out-of-range ضمن سقوف langchain — تحت المسح الإرشاديّ).
  - `bandit -r services/ bots/ agents/ --severity-level high` يحجب على HIGH (الباقي إرشاديّ).
- **مثال واقعيّ:** `python-multipart` 0.0.27 حمل CVE حجبت CI حتى رُفِع إلى `0.0.31`. افحص أوّلاً تتجنّب التكرار.

---

## ٦. الدماغ المعرفيّ (Knowledge Brain)

قاعدة معرفة Markdown يصونها الوكيل ذاتيّاً في `sahool-brain/` — هُب **رابط لا مكرّر** يربط المصادر
القائمة (docs/adr · MANIFEST · compose · تقرير الفجوات · decision_record) ويضيف الناقص (كتالوج خدمات،
سجلّ فجوات حيّ، لقطة تركيز، سجلّ جلسات، بروتوكول صيانة).

- **بداية الجلسة:** اقرأ `sahool-brain/hot.md` + `sahool-brain/index.md` + الفجوات الحرجة المفتوحة في `sahool-brain/gaps/registry.md`.
- **نهاية الجلسة:** حدّث `hot.md`؛ ألحِق `log.md`؛ حدّث حالات `gaps/registry.md`؛ أضف قرارات الجلسة (SHA + سبب) إلى `decisions/ledger.md`.
- **القواعد الصارمة:** لا معلومة بلا مصدر (`path:line`/`#PR`) · لا فجوة بلا مصدر + حالة · لا قرار بلا سبب + PR/SHA · لا تحديث بلا سطر في `log.md`.

نقطة الدخول: [`sahool-brain/index.md`](sahool-brain/index.md) · المقدّمة والقواعد: [`sahool-brain/README.md`](sahool-brain/README.md).

---

## ٧. التشغيل والبناء (Build / Run)

```bash
# التحقّق الثابت offline (الافتراضيّ) — صياغة + اختبارات منطق + chaos
make                      # = make verify-static
make verify-tests         # اختبارات بنيويّة/منطقيّة فقط

# رفع المنظومة كاملةً (يحتاج Docker)
docker compose -f docker-compose.v9.yml up -d     # canonical
docker compose -f docker-compose.light.yml up -d  # نسخة خفيفة للتطوير

# الواجهة
cd frontend && npm ci && npm run dev              # تطوير
npm run build                                      # إنتاج

# الموبايل
cd mobile/sahool_app && flutter pub get && flutter run
```

دليل التشغيل الكامل: [`RUNBOOK.md`](RUNBOOK.md). الإعداد الموحّد: [`docs/UNIFIED_SETUP.md`](docs/UNIFIED_SETUP.md).

---

## ٨. بوّابات CI (`.github/workflows/ci.yml`)

كلّ دفعة/PR تُشغّل هذه الوظائف. اجعلها خضراء قبل الدمج:

| الوظيفة | تحجب على |
|---|---|
| Repository Structural Lint | بقايا glob (`{a,b}`) + تحذير المجلّدات الفارغة |
| Platform Structure Inspector | `python3 tools/sahool_inspector.py` (سلامة بنية المنصّة) |
| Validate Docker Compose | صحّة YAML + schema لكلّ `docker-compose*.yml` |
| Lint & Format | `ruff check` + `ruff format --check` (mypy إرشاديّ) |
| Frontend Typecheck | `tsc --noEmit` |
| Frontend E2E | Playwright (MapLibre/WebGL على Chromium) |
| Unit Tests | `pytest -m unit` + تغطية `--cov-fail-under=20` |
| Platform Unit Tests | اختبارات المنصّة + راتشِت تغطية (`.coveragerc`) |
| Integration Tests | `pytest -m integration` (Postgres+PostGIS+Redis + ترحيلات) |
| Security Scan | `bandit` HIGH + `pip-audit` (المسار الحرج) + `pytest -m security` |
| Flutter Analyze & Test | `flutter analyze` (errors) + `flutter test` |

> ١١ وظيفة CI — اجعلها كلّها خضراء قبل الدمج.

---

## ٩. ملاحظات عمليّة سريعة

- اقرأ ترتيب الترحيلات من `migrations/MANIFEST.txt`، لا من ترتيب أبجديّ للملفّات.
- عند لمس توجيه nginx، حدّث جدول [`service-map.md`](sahool-brain/architecture/service-map.md) المُشتقّ منه.
- ملفّات compose المتعدّدة مقصودة: `v9` (إنتاج)، `light` (تطوير)، `test`، `erpnext`/`odoo` (ERP اختياريّ بـprofiles).
- لا تُشغّل `playwright install` لتنزيل المتصفّح في البيئة البعيدة — Chromium مثبَّت مسبقاً.
</content>
</invoke>

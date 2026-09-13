# مراجعة بنيويّة عميقة لكامل المكوّنات — 2026-09-13

> **الأساس المقيس:** `main` عند `9613db9a` (بعد دمج #993 و#994). كلُّ رقمٍ هنا **مشتقٌّ من الشجرة**
> بأمرٍ قابلٍ للإعادة أو من مصنوعةٍ مولَّدةٍ يحرسها `verify_all_generated --check` — لا من تقريرٍ
> سابق ولا من ذاكرة. **حدُّ الصدق:** مراجعةٌ ساكنة كاملة؛ لا مكدّسَ حيّاً ولا PostgreSQL ولا nginx
> ولا NATS شُغِّل. ما يحتاج تشغيلاً حيّاً موسومٌ **[حيّ]**. ولا تُغيّر هذه الوثيقة حالةَ أيّ
> فجوةٍ أو قدرة: `runtime_verified=0` و`production_certified=false` على القدرات الـ٨١ كلِّها،
> وهذا صادقٌ لا عيب.

---

## ٠ · الخلاصة في عشرة أسطر

| # | الحكم | الدليل المقيس |
|---|---|---|
| ١ | **المنصّة هي المستودع.** خدمةٌ واحدة من ٣٢ تحمل ٦٤٪ من شيفرة الخدمات و٦٣٨ مساراً من ~١٠٥٠ | `service_inventory.generated.json`: `sahool-platform` 164,626 سطراً من 256,943 · `risk=critical-core-concentration` |
| ٢ | تفكيك `main.py` **نجح شكلاً وانتقل الثقلُ إلى الراوترات** | `main.py` 2,553 سطراً بلا مسارات (بالعقد) · `routers/` **١٦٨ ملفّاً** · `routers/fields.py` **4,241** سطراً · `routers/weather.py` **3,022** |
| ٣ | **الأمان بنيويّاً صحيح، وتوزيعُه غيرُ موحَّد**: RS256 إلزاميّ في الإنتاج، لكنّ التحقّق من JWT مكتوبٌ ١٥ مرّة | `services/auth/main.py:67,159-162` · `jwt.decode(` في ١٥ ملفّاً خارج `shared/security/` بينما ١٢ خدمة تستورد `shared.security` |
| ٤ | **العزلُ متعدّد المستأجرين واسعٌ ومتشقّق الاسم**: ٢٠٥ جداول تحت RLS بخمسة أسماء GUC | `app.current_tenant` ٣٩٣ · `app.tenant_id` ٦٩ · `app.current_tenant_id` ٦ · `app.current_role` ١٥ · `app.current_user_id` ٨ (فجوة مسجَّلة `TENANT-GUC-NAME-DIVERGES-…-01`) |
| ٥ | **الحوكمة أكبر من المنتج**: ٥٨ workflow · ٧٨ وظيفة على كلّ PR · ٢٧٢ حارساً يحجب — **٤٩ فقط مُثبَتة بالتكذيب** | `GUARD_CATALOGUE.md` (مولَّد): «٢٢٣ حارساً يحجب الدمج ولم يُثبَت قطّ أنّه يفشل حين يوجد العطل» |
| ٦ | **الواجهة تحمل نفسَ مرض المنصّة**: ثلاثة ملفّات بأكثر من ٣٬٠٠٠ سطر — و**تصحيح**: `fetch` خارج طبقة الـAPI ٨ مواضع في ٣ ملفّات لا ٦٢ (العدُّ الأوّل التقط `refetch`/`prefetch`) | `services/api.ts` 3,782 · `hooks/useApi.ts` 3,373 · `sections/MapHub.tsx` 3,234 · `AddFieldWithMap.tsx` 1,810 · `grep -rnE '\bfetch\('` |
| ٧ | **التبعيّات منقسمة نصفَين**: ٣٦ ملفّ متطلّبات، ١٩ فقط تحت `pip-audit` الحاجب، وإصداران من FastAPI/Pydantic يعيشان معاً | `fastapi ∈ {0.115.6, 0.136.3}` · `pydantic ∈ {2.10.4, 2.13.4}` · `httpx`/`uvicorn`/`redis` كذلك · ١٨٣ سطراً بـ`>=` بلا تثبيت |
| ٨ | **النشرُ قانونيٌّ واحد ومحاطٌ بأربعة عشر بديلاً**: `docker-compose.v9.yml` (٦٨ خدمة) وحدَه محروسٌ من الانحراف | ١٥ ملفّ compose · `env_compose_drift_guard` يقرأ v9 فقط · `unified`/`light` بأسماء خدمات **غير متوافقة** (`auth-service` مقابل `sahool-auth`) · Helm: ٤ نشرات مقابل ٦٨ |
| ٩ | **الذاكرة المؤسّسيّة مزدوجة**: `sahool-brain/` (القانونيّ) و`agent-memory/` (سابق، آخر تحقّق 2026-06-18)، و٢٧٧ ملفّ Markdown على جذر المستودع | `agent-memory/FACTS.md` · `ls *.md \| wc -l` = 277 · `docs/history` 131 · `docs/audits` 141 |
| ١٠ | **أخطرُ ما هو مفتوح ليس بنيويّاً بل فيزيائيّ/زراعيّ**: NATS بلا مصادقة على أوامر المشغّلات، والريُّ غيرُ المسجَّل يُقرأ صفراً | `NATS-BROKER-HAS-NO-AUTHENTICATION-…` (open · physical-effect) · `UNRECORDED-IRRIGATION-READ-AS-ZERO-…-01` (open · محجوب بـGATE-01) · `PRODUCTION-CERTIFICATION-VERDICT-…-01` (open · P0) |

**ما يعنيه ذلك بجملة:** المستودع **صادقٌ عن نفسه إلى حدٍّ نادر** (كلُّ ما أعلاه قابلٌ لإعادة القياس من مصنوعاتٍ مولَّدة يحرسها CI)، لكنّ **مركزَ ثقله في مكانٍ واحد** (خدمة واحدة · ملفّات راوتر عملاقة · ملفّات واجهة عملاقة)، و**حوكمتَه تنمو أسرعَ من قدرتها على إثبات نفسها** (٢٢٣ حارساً بلا تكذيب). لا واحدةَ من العشر تُحلّ بسطر؛ وسبعٌ منها قراراتُ اتّجاه لا رِقاع.

---

## ١ · الهيكل العامّ — الأرقام

| المكوّن | المقيس | مصدر القياس |
|---|---|---|
| ملفّات متتبَّعة | 5,798 | `git ls-files` |
| Python / TS+TSX / Dart / SQL | 3,261 / 621 / 61 / 271 | `git ls-files` بالامتداد |
| خدمات (`services/`) | 32 | `ls -d services/*/` |
| خدمات compose القانونيّ (v9) | 68 (٢٠ منها صورٌ جاهزة بلا بناء) | `docker-compose.v9.yml` |
| عقد الرسم المعماريّ | 153 عقدة · 971 حافّة (117 استيراد · 854 تبعيّة compose) · **٥ أيتام** · صفر دورات | `architecture/generated/ARCHITECTURE_GRAPH_REPORT.md` |
| معالجات المسارات | 1,050 (المنصّة 638 · raster 82 · decision 70 · soil 60) | `execution_audit_summary.json` · `service_inventory` |
| ميزانيّة مسارات المنصّة | خام 632 · بنية 4 · نطاق 628 / سقف 629 (**هامش ١**) | `platform_route_budget_inventory.json` · #993 |
| ترحيلات SQL | 231 ملفّاً / 229 في `MANIFEST.txt` (الملفّان الغائبان `.down.sql` بالسياسة) · آخرها `v230` | `migrations/` |
| جداول (CREATE TABLE فريدة) / تحت RLS | 340 / 205 | `grep` على `migrations/*.sql` |
| ملفّات اختبار | `tests_v9` 803 · `services/sahool-platform/tests` 458 · `tests` 130 · محلّيّة للخدمات 239 · frontend 210 · Dart 9 | `git ls-files` |
| أرضيّة التغطية / المقيس | 43٪ / ~51٪ (`--cov=services`, راتشِت صاعد 20→40→42→43) | `ci.yml` · `docs/testing/coverage_ratchet.md` · run 34704333703 |
| workflows / وظائف تعمل على كلّ PR / سياقات مطلوبة في الـRuleset | 58 / 78 / **15** | `.github/workflows` · `required_status_checks_contract.json` |
| حرّاس تحجب / مُثبَتة بالتكذيب / طفرات مسجَّلة | 272 / 49 / 368 (منها 320 سلوكيّة على 116 مصدراً) | `GUARD_CATALOGUE.md` |
| قدرات مسجَّلة | 81 · `maturity=3` على 75 · `runtime_verified=0` · `production_certified=false` على الكلّ | `capabilities/registry/capabilities.json` |
| سجلّ الفجوات | 272 صفّ جدول + 290 قسم `## ` · **41 open** · 79 fixed · 2 verified · 49 بحالةٍ غيرِ قياسيّة | `sahool-brain/gaps/registry.md` |
| مرشّحو الشيفرة الميّتة / مجموعات التكرار | 629 / 60 (صفر حذف تلقائيّ) | `execution_audit_summary.json` |
| Markdown | 851 ملفّاً — **277 على الجذر** · 75 ملفّاً غير-Markdown سائباً على الجذر | `ls` |

---

## ٢ · الخدمات (`services/`)

### ٢.١ التركّز
`sahool-platform` = **164,626** سطر Python (٦٤٪ من 256,943) · 432 ملفّاً في `api/` وحدَه · 638 مساراً · 458 اختباراً. الخدمة التالية (`raster-service`) 23,822 — أي أنّ **الفارق سبعة أضعاف** بين الأولى والثانية. جردُ الخدمات المولَّد يُصنّفها `critical-core-concentration` — التصنيفُ صحيح ومُعلَن، والسؤال ليس «هل» بل «ماذا يُستخرَج أوّلاً». الشجرة تحمل خطّةً واحدةً مقيسة (`docs/architecture/raster_service_route_migration_plan.md`) ولا خطّةً للبقيّة.

### ٢.٢ التفكيك: نجح في `main.py` وانتقل الثقل
- `api/main.py` 2,553 سطراً **بلا مُزخرِف مسار** — يفرضه `p1_main_decomposition_guard` ✓.
- لكنّ `api/routers/` **168 ملفّاً**، وأكبرها: `fields.py` **4,241** · `weather.py` **3,022** · وفي raster: `routers/fields.py` 1,712. وفي decision-service: `persistence.py` **4,767** · `main.py` 2,863.
- **الملاحظة:** حارسُ تفكيك `main.py` يحدّ الملفَّ الذي سُمّي، ولا حارسَ يحدّ حجمَ راوتر. فالانحدارُ انتقل إلى حيث لا قياس — الصنفُ نفسُه الذي يطارده هذا المستودع في مواضع أخرى (`COVERAGE-MASKED-BY-A-NEIGHBOURING-GUARD-01`).

### ٢.٣ الخدمات الرفيعة والأيتام
- **صفرُ اختبارات:** `raster-tiler-service` · `sam2-inference` · `weather-polygon-worker` · `weather-signal-engine` (من الجرد المولَّد).
- **أيتامُ الرسم المعماريّ (لا استيرادَ ولا تبعيّةَ compose تصل إليها):** `field-segmentation` · `guardrails-engine` · `sam2-inference` · `weather-polygon-worker` · `weather-signal-engine` — ثلاثةٌ منها في القائمة السابقة أيضاً.
- **بلا Dockerfile:** `gis-workflow-service` (٤ ملفّات، لا يبنيه compose v9 إطلاقاً) · `edge-inference` (`Dockerfile.arm64` فقط، هدفٌ حافّيّ مقصود).
- خدماتٌ باختبارٍ واحدٍ أو اثنين مع عشرات المسارات: `ai_agronomist` (13 مساراً/1) · `mcp_servers` (34/1) · `guardrails-engine` (8/1) · `auth` (29/2) · `odoo-bridge` (11/2).

### ٢.٤ الوحدات المشتركة (`shared/`)
- `shared/security/` ناضج: `jwt_key_validation` · `tenant_context` · `trusted_tenant` · `decision_service_auth` · `tls_policy` · `cors_policy` · `secret_guard`. **١٢ خدمة** تستورده.
- لكنّ **`jwt.decode(` يظهر في ١٦ ملفّاً خارجه** (`actuator_runtime` · `guardrails-engine/main` · `local-ai-rag/main` · `mcp_servers` ×٢ · `odoo-bridge/main` · `supervisor-agent/main` · `tts-service/main` · `vegetation_runtime` · `video-processor/main` · `agents/notification/agent` · وثلاثةٌ في المنصّة · واثنان في `auth` وهو المُصدِر) — بأسماء مستعارة (`_jwt` · `_jjwt` · `_v_jwt`) تُخفيها عن `grep` الساذج. بعضُها يستورد `shared.security` **ويفكّ التوكن بنفسه أيضاً** — ازدواجٌ لا غياب. كلُّ موضعٍ منها سطحٌ يمكن أن ينحرف عن سياسة المفاتيح المركزيّة (`jwt_key_validation`) بلا أن يحمرّ شيء. **مجمَّدٌ الآن بأعداده** في `tests/architecture/test_jwt_decode_outside_shared_security_ratchet.py` (يتقلّص ولا ينمو).
- **أربعةُ «أطوار» أحاديّة الملفّ بمستورِدٍ واحد** (اختبارُها غالباً): `autonomous_farm_os_phase9` (730 سطراً) · `continuous_learning_phase10` (870) · `federated_agents_phase11` (769) · `marketplace_ecosystem_phase12` (642). تعيش كوحداتٍ نقيّة بلا مسارِ تشغيلٍ يبلغها — شيفرةٌ مُختبَرة لا مُشغَّلة، وهي مادّةُ ٦٢٩ مرشّحاً للشيفرة الميّتة.
- ملفّاتُ اختبار (`shared/test_*.py`) على جذر `shared/` بجوار الشيفرة لا في `tests/`.

### ٢.٥ الشيفرة الميّتة والتكرار (مولَّد، ساكن)
629 مرشّحاً · 60 مجموعةَ تكرار (أكبرها ١٠ نسخٍ لبصمةٍ واحدة). أبرزُ ما في القائمة عالية الثقة **ليس هامشيّاً**: `workflow_definitions.py` تحمل **١٣ دالّةَ ريّ** (`_irrigation_real_execute` · `_irrigation_real_approval_gate` …) لا يستدعيها أحد — أي أنّ تعريفَ سير عمل الريّ «الحقيقيّ» موجودٌ ومكتوبٌ **وغيرُ موصول**. وكذلك `_apply_tenant_guc` في `main.py:649`: ثلاثةُ ملفّات تذكرها في تعليقاتها بوصفها **ما يجب استدعاؤه** قبل الاستعلامات المُنطّقة (`internal_service.py:29` · `field_lifecycle.py:113` · `trueup.py:305`) ولا يستدعيها **أحد**. **وتصحيحٌ لِما ورد أوّلاً:** `_tenant_context_mw` في `soil-service/main.py:107` **ليست ميّتة** — مسجَّلةٌ بـ`@app.middleware("http")` (السطر ١٠٦)، والمُدقّقُ الساكن لا يرى المُزخرِفات؛ فهي إيجابٌ كاذب لا عطل. هذه تحتاج قراراً لكلّ واحدة: وصلٌ أو حذف، لا بقاءً.

---

## ٣ · طبقة البيانات

- **٢٣١ ترحيلاً** بترتيبٍ قانونيّ في `MANIFEST.txt` (229 + ملفّا `.down` بالسياسة) — نظامٌ واحد ناضج، يحرسه `migration_graph_guard` واختبارُ أعمدة الفهارس (`test_migration_index_columns_exist`).
- **لكنّ ثلاثة أنظمة ترحيل تتعايش:** (١) `migrations/*.sql` القانونيّ · (٢) `alembic/` بنسختين (`0001_baseline` · `0002_ai_recommendation_runtime`) لا يذكرهما `MANIFEST` · (٣) `services/decision-service/migrations/00[1-5]_*.sql` بمُشغِّلها الخاصّ (`migration_runner.py`) — مقصودٌ لمخطّط SoR المستقلّ. الأوّلُ والثالث موثَّقان؛ **الثاني يتيم**: من يُطبّقه ومتى غيرُ مُعلَن.
- **RLS:** 205 جداول · 130 ملفّاً يُفعّلها · أدوارٌ ثلاثة صحيحة (`sahool_app` NOBYPASSRLS · `sahool_jobs` BYPASSRLS · `sahool_user` للهجرات). **الشقّ:** خمسةُ أسماء GUC للمستأجر/الدور (الجدول في §٠/٤). الفجوةُ مسجَّلة ومحروسةٌ من النموّ (`tenant_guc_scope_baseline.json`) — أي أنّها **مجمَّدة لا مُعالَجة**، وكلُّ سياسةٍ على `app.tenant_id` تُقرأ بمنطقٍ يختلف عن `app.current_tenant` في نفس القاعدة.
- **ملكيّةُ الكتابة:** `OWNERSHIP-CONTRACT-DECLARED-BUT-NEVER-MEASURED-01` (open) — ٧٥ كتابةً لم يأذن بها عقدُ الملكيّة موزّعةً على عشر خدمات؛ الحارسُ `db_writer_ownership_guard` يجمّد الأساس ولا يُقلّصه.
- **[حيّ]** `WORKER-CLAIM-NOT-PINNED-BY-A-TRANSACTION-01` مُثبَتٌ على PostgreSQL 16 حقيقيّ (عاملان متزامنان) وما يزال open — عطلُ تزامنٍ مقيسٌ لا مُقدَّر.

---

## ٤ · النشر والبوّابة

### ٤.١ compose
- **v9 (القانونيّ):** 68 خدمة · صحّة 60/68 · `restart` 67/68 · حدودُ موارد 61/68 · **صفرُ أسرارٍ مكتوبة** في البيئة · كلُّ المنافذ الحسّاسة مقيَّدة بـ`127.0.0.1` (Postgres · MinIO · Grafana · Jaeger · Odoo …) وnginx وحدَه على 80/443. **هذا مستوىً جيّد.**
- **بلا `healthcheck:` في compose (٨)، وبعد القياس الأدقّ:** `minio-init` · `migrate` · `qdrant-seed` · `zlmediakit-config` مهامُّ مرّةٍ واحدة (مقبول) · `sahool-qdrant` **قرارٌ موثَّق** (الصورةُ بلا أداة HTTP داخلها، `docker-compose.unified.yml:421` — يُغطّى بمرحلةِ انتظارٍ لا بفحص) · `model-lifecycle-adapter` يحمل `HEALTHCHECK` في Dockerfile الخاصّ به (`/readyz`) فهو مفحوص · **وعاملا الريّ** (`irrigation-reservation-lifecycle-worker` · `reservation-dispatch-relay-worker`) **أسوأ من «بلا فحص»**: يرثان `HEALTHCHECK curl :8000/healthz` من صورة المنصّة ولا يخدمان HTTP ⇒ **unhealthy دائماً** وأيُّ `depends_on: service_healthy` عليهما يعلّق إلى الأبد. *(عُولِج: نبضةٌ بنمط `phase_runtime_workers` + مسبارُ `worker_heartbeat` في compose.)*
- **بلا حدود موارد (٧):** منها `raster-tiler-service` و`weather-signal-engine` و`soil-service` — والأوّلُ يخدم بلاطاتٍ للمتصفّح، أي أنّ ضغطاً خارجيّاً يستهلك ذاكرةَ المضيف بلا سقف.
- **١٤ ملفّ compose آخر.** `production.yml` (٤ خدمات) و`unified.yml` (٢٦) و`light.yml` (١٩) و`fixed.yml` (٣٧) — والاثنان الأوسطان **بأسماء خدماتٍ لا تطابق v9** (`auth-service`/`frontend`/`guardrails` مقابل `sahool-auth`/`sahool-frontend`/`sahool-guardrails-engine`)، فأيُّ `depends_on` أو nginx upstream مكتوبٌ لأحدهما لا يعمل مع الآخر. `env_compose_drift_guard` يقرأ **v9 فقط**؛ الباقي بلا حارس، و٤ منها لا يذكرها أيُّ workflow. **القرار المطلوب:** أيُّها يبقى، وأيُّها يُنقل إلى `docs/history/` بوصفه أثراً.

### ٤.٢ nginx
- `nginx.v9.conf`: 40 موقعاً · 18 upstream · ٤ ترويسات أمنيّة · ثلاثُ مناطق `limit_req` · `auth_request` + حقنُ `X-Tenant-Id` في المواقع المصادَقة (٩ مواقع مصادَقة بوّابيّاً · ٩ مربوطةٌ بالمستأجر) — والجردُ الساكن `gateway_reachability.json` **بلا upstream معلَّق**.
- **أربعةُ إعدادات** (`v9` · `fixed` · `light` · `unified`) تعكس انقسامَ compose نفسَه.
- **[حيّ]** مُثبَتٌ بـ`crossplane` أنّ الصياغة صالحة وأنّ `proxy_pass` في المواقع النمطيّة بلا مقطع URI (#993)؛ **غيرُ مُثبَت** أنّ nginx يُقلع بها أو أنّ جسرَ الكوكي يُعطي 200 في متصفّح.

### ٤.٣ Kubernetes/Helm
`helm/` 12 قالباً · ٤ نشرات مسمّاة · `k8s/` ملفٌّ واحد. مقابل ٦٨ خدمةً في compose. **ليس هدفَ نشرٍ قابلاً للاستعمال اليوم**؛ إمّا يُعلَن هدفاً مستقبليّاً صراحةً في `README`، أو يُنقل.

### ٤.٤ المراقبة
Prometheus + Alertmanager + Grafana + OTel collector + Jaeger في v9 ✓ · **٢٠ قاعدةَ تنبيه** · **لوحتان** فقط لـ٦٨ خدمة. `CORRELATION-ID-ABSENT-FROM-THE-THREE-TABLES-…` (open، مقيسٌ حيّاً) يعني أنّ تتبّعَ قرارٍ من الطلب إلى التنفيذ **غيرُ ممكنٍ بالبيانات** حتّى لو كانت اللوحاتُ كاملة.

---

## ٥ · الواجهة والموبايل

- **Frontend:** React + Vite + TypeScript `strict` ✓ · ESLint ✓ · صفرُ `: any` في `api.ts` ✓ · 254 مكوّناً · 210 ملفّ اختبار · Playwright e2e (smoke · gis-timeline · weather · visual) ✓ · ميزانيّةُ حزمة (`verify:bundle-budget`) ✓ · DuckDB-WASM + Leaflet/Geoman + Turf.
- **العطل البنيويّ:** `services/api.ts` **3,782** سطراً بـ١٤٧ تصديراً · `hooks/useApi.ts` **3,373** بـ٢٠٦ خطّافات · `MapHub.tsx` **3,234** · `AddFieldWithMap.tsx` 1,810 · `SettingsPage.tsx` 1,044. **وتصحيحُ قياس:** الرقمُ الأوّل «٦٢ ملفّاً تستدعي `fetch(`» كان خطأً — `grep 'fetch\('` يلتقط `refetch(`/`prefetch(` من TanStack Query؛ بحدّ الكلمة المقيسُ **٨ مواضع في ٣ ملفّات** (`maphub/weather/WeatherProbePopup.ts` ×٦ · `WeatherTileLayer.ts` · `WeatherHoverReadout.ts`)، وكلُّها تمرّر `weatherFetchHeaders()`. أي أنّ طبقةَ الـAPI **حدٌّ فعليّ** باستثناءٍ واحدٍ محصور في وحدة الطقس — مجمَّدٌ في `test_frontend_fetch_boundary_ratchet.py`. `MAPHUB-WEBGL-VISUAL-DEBT-01` مسجَّلةٌ ومحروسة.
- **Mobile (Flutter):** 46 ملفّاً في `lib/` · **٩ اختبارات** · Dart ≥3.6 · CI يشغّل `flutter analyze` + test ✓. رفيعٌ مقارنةً بالواجهة، والفجوةُ `C4/M1` في تقرير الإنتاج (WebSocket · push · timeline) ما تزال «تتطلّب بيئة Flutter».

---

## ٦ · الحوكمة وCI — الحجم مقابل الإثبات

- **٥٨ workflow · ٧٨ وظيفةً على كلّ PR · ١٥ سياقاً مطلوباً فقط في الـRuleset** (`required_status_checks_contract.json`، مُتحقَّقٌ في الاتّجاهين). أي أنّ **~٦٣ وظيفةً تحمرّ ولا تحجب** ما لم تكن داخل وظيفةٍ مطلوبة — ومنها `Mutation Sweep 1..5/5` (مقيسٌ في #993 أنّ أسماءها غائبة).
- **٢٧٢ حارساً يحجب · ٤٩ مُثبَتة بالتكذيب · ٢٢٣ لم يُثبَت قطّ أنّها تفشل حين يوجد العطل** — الكتالوجُ نفسُه يقولها. هذا أكبرُ دَينٍ في المستودع من حيث **نسبةُ الادّعاء إلى الدليل**، وهو ما دفع حزمةَ الماء إلى ٧٥٧ طفرة فوق السقف: النشاطُ الصحيح (التكذيب) يستهلك ميزانيّةً صُمِّمت لحمايته. القرارُ مسجَّل (`Mutation Budget Audit` كوظيفةٍ مستقلّة بتوقيعها) وما يزال بيد المالك.
- **١٩٢ دالّةَ اختبار في ١٣ ملفّاً تُسجّل خاصّيّةً ولا تفرضها** (`test_unenforced_report_list_tests.py`، راتشِت) — ١٢٩ منها في `test_roadmap_phase23.py` (6,634 سطراً، أكبرُ ملفّ Python في الشجرة). شرطُ إغلاقها قرارُ مالك.
- **الدروس المفتوحة كفجوات** (`LESSON-…-01` ×٣، `GUARD-RUN-WITHOUT-THE-ARGUMENTS-…`، `SWEEP-SELF-CHECK-…`) صادقةٌ لكنّها تُضخّم عدّادَ «open» بأصنافٍ منهجيّة لا عيوب منتج — يُستحسن فصلُها في عمود «نوع».

---

## ٧ · التبعيّات والأمان

- **٣٦ ملفّ متطلّبات · ١٩ تحت `pip-audit` الحاجب · ١٧ خارجه.** `bandit` على `services/ bots/ agents/` فقط — `shared/` و`scripts/` (٢٠٠+ حارس بصلاحيّة git/subprocess) **خارج المسح**.
- **تشعّبُ الإصدارات:** `fastapi` {0.115.6, 0.136.3} · `pydantic` {2.10.4, 2.13.4} · `httpx` {0.27.0, 0.28.1} · `uvicorn` {0.30.6, 0.34.0} · `redis` {5.2.1, 5.3.1}. مقيسٌ في #993 أنّ الفرقَ بين FastAPI 0.136 و0.141 يجعل `app.routes` معتماً فتحمرّ ٣٢ حالة — فالتشعّبُ **يكلّف** لا يُزعج فقط. و١٨٣ سطراً بـ`>=` غيرُ مثبَّت (تُغطّيه `transitive-lock-certification` بجدولةٍ، لا حجباً).
- **المصادقة:** RS256 إلزاميّ في الإنتاج بمهربِ ترحيلٍ صريح (`SAHOOL_ALLOW_HS256_IN_PROD=1`) ✓ · bcrypt ✓ · MFA/OTP ✓ · `.env.example` بـ٦٨ متغيّراً باسمٍ سرّيّ: كلُّ ما يحمل قيمةً سرّيّة فعلاً `*_change_me`، والسبعةُ الباقية معرّفاتٌ لا أسرار (عناوين · `KEY_ID=current/previous` · اسمُ مستخدم MinIO) ✓ · `DECISION_REQUIRE_AUTH_TOKEN=false` في المثال علَمٌ مرحليّ **يُلغيه** كشفُ الإنتاج (`decision-service/main.py:470` — `_is_production() or …`) فلا يفتح شيئاً ✓ · compose بلا أسرارٍ حرفيّة ✓.
- **المفتوح الخطِر:** **`NATS-BROKER-HAS-NO-AUTHENTICATION-SO-ACTUATOR-COMMANDS-ARE-UNGUARDED`** (open · physical-effect) — أوامرُ المشغّلات على وسيطٍ بلا هويّة؛ و`CONN-03` (هويّات NATS/TLS) من #993 في الاتّجاه نفسه. هذا ليس دَينَ حوكمة بل **سطحَ هجومٍ على أثرٍ فيزيائيّ**، ويسبق في الأولويّة كلَّ ما في §٦.
- `H1` من تقرير الإنتاج (96/319 نقطة بلا تفويض fail-closed عالميّ، «غالبها GET مرجعيّ») ما يزال «يحتاج قراراً» منذ 2026-06-19.

---

## ٨ · الوثائق والذاكرة المؤسّسيّة

- **`sahool-brain/`** هو الأصلُ القانونيّ وخمسةُ حرّاس يحمونه (append-only · انتقال الحالة · ادّعاء الالتزام · التأجيل · ازدواج الهويّة) ✓.
- **`agent-memory/`** ذاكرةٌ موازية (`FACTS.md` · `CORRECTIONS.md` · `JOURNAL.jsonl` بـ١٢٤ سطراً، آخر تحقّق **2026-06-18**) بلا حارسٍ ولا رابطٍ من `index.md`. ذاكرتان لوكيلٍ واحد تفترقان بصمت.
- **سجلُّ الفجوات بصيغتين:** 272 صفَّ جدول **و**290 قسمَ `## ` — وحارسُ ادّعاء الالتزام يقبل الأقسامَ فقط، وحارسُ التأجيل يقبل الاثنين. ٤٩ صفّاً بحالةٍ غيرِ قياسيّة (`CLOSED_IN_CODE + PG16_PROVEN / OPEN` · `implemented / pending final CI` · `OPEN — targeted code repairs only`). القاعدةُ في رأس الملفّ تقول `open/fixed/verified` فقط.
- **٢٧٧ ملفّ Markdown و٧٥ ملفّاً سائباً على الجذر** (25 `RASTER_*` · 15 `WEATHER_*` · 10 `GIS_*` · 9 `GOVERNANCE_*` …) — `REPORT_INDEX.md` يفهرس `*_REPORT*.md` منها فقط. الجذرُ صار أرشيفاً؛ `docs/history/` (131) هو مكانُه المُعلَن.
- **ADRs:** ١٢ فقط لمنظومةٍ بهذا الحجم؛ القراراتُ الفعليّة تعيش في `decisions/ledger.md` (جيّد) وفي رسائل الالتزام (غيرُ قابلٍ للبحث).

---

## ٩ · الترتيب المقترَح للمعالجة — بلا تنفيذ

مرتّبٌ بأثر العطل لا بسهولة الرقعة. **لم يُنفَّذ منه شيء؛** كلُّ بندٍ يحتاج قرارَك، وأكثرُها يمسّ ملفّاتٍ محروسة.

| الأولويّة | البند | لماذا هنا | ما يلزم |
|---|---|---|---|
| **P0** | مصادقةُ NATS + TLS على مسار المشغّلات (`NATS-BROKER-…` · CONN-03) | أثرٌ فيزيائيّ بلا هويّة | قرارُ آليّة الهويّة (nkeys/creds) · تعديلُ compose/nats · **[حيّ]** |
| **P0** | تحكيمُ GATE-01 لعطلَي الرياح والريّ غير المسجَّل (`phase_runtime_workers.py`) | التوصيةُ المائيّة تُعلن إجهاداً أقصى بثقةٍ على حقلٍ يُروى | تفويضٌ مقيَّد واحد لعطلَين · ثمّ استبيانُ الحقل/الموسم المُصادَق عليه |
| **P0** | `PRODUCTION-CERTIFICATION-VERDICT-…` النصفُ الثاني (تعذّرُ النجاح) | بوّابةٌ لا يمكن أن تخضرّ تُدرّب قارئَها على تجاهلها | قرارُ ما يُعدّ دليلاً كافياً لكلّ حاجب |
| **P1** | خطّةُ استخراج من `sahool-platform` — تبدأ بـ`routers/fields.py` و`weather.py`؛ **حارسُ الحجم نُفِّذ** (`test_router_size_ratchet.py`، سقف ٨٠٠، ستّةٌ مجمَّدة) | ٦٤٪ تركّز · انحدارٌ انتقل حيث لا قياس — **ولم يعد يستطيع** | خطّة كخطّة raster |
| **P1** | توحيدُ فكّ JWT على `shared/security` وإزالةُ الـ١٦ موضعاً — **الراتشِت نُفِّذ** (`test_jwt_decode_outside_shared_security_ratchet.py`)، والنقلُ خدمةً خدمةً يبقى | كلُّ موضعٍ سطحُ انحرافٍ عن سياسة المفاتيح | رقعة لكلّ خدمة تُخفِّض الأساس |
| **P1** | اسمُ GUC واحد (`app.current_tenant`) وترحيلٌ للـ٦٩+٦ سياسةً الأخرى | نفسُ القاعدة، منطقان للعزل | ترحيلٌ + خفضُ الأساس المجمَّد |
| **P1** | توحيدُ إصدارات FastAPI/Pydantic/httpx وإدخالُ الـ١٧ ملفّاً في `pip-audit` — **وما قاسه تشغيلُ `pip-audit` عليها فعلاً:** ٤ من ١٧ حمراء: `decision-service` (starlette 0.41.3 · ٦ ثغرات — **نُفِّذت الترقية**) · `bots/telegram` (aiohttp 3.13.5 · ٢٨ ثغرة عبر `aiogram==3.28.2` الذي **يرفض** aiohttp ≥3.14؛ العلاجُ aiogram 3.31.0 والبوت بلا اختبارات تُثبته) · `requirements-dev.txt` (nltk عبر `safety` بلا إصلاح منشور) · `requirements-irr-f01-test.txt` (pytest 8.4.2 → ≥9.0.3) | التشعّبُ مقيسُ الكلفة، والثغراتُ الأربع كانت غيرَ مرئيّة لأنّ الملفّات خارج البوّابة | قرارُ الإصدار الهدف · ترقياتٌ مفحوصة |
| **P1** | وصلُ أو حذفُ `_irrigation_real_*` في `workflow_definitions.py` و`_apply_tenant_guc`/`_tenant_context_mw` | أسماءٌ أمنيّة/تنفيذيّة لا تُنفَّذ | قرارٌ لكلّ دالّة؛ لا حذفَ جماعيّاً |
| **P1** | `Mutation Budget Audit` وظيفةً مستقلّة + إدراجُ `Mutation Sweep 1..5/5` في الـRuleset | ٢٢٣ حارساً بلا تكذيب، وميزانيّةٌ تعاقب التكذيب | قرارُ Ruleset (لا يُحلّ بشيفرة) |
| **P2** | حسمُ compose/nginx: v9 وحدَه + نقلُ `unified`/`light`/`fixed` إلى `docs/history/` | أسماءٌ غيرُ متوافقة بلا حارس | قرارٌ + `git mv` |
| **P2** | حدودُ ذاكرة على `raster-tiler-service` والستّة الأخرى · ~~فحصُ صحّة على عاملَي الريّ~~ (**نُفِّذ**: نبضة + مسبار) · `qdrant` قرارٌ موثَّق لا يُلمَس | `depends_on` لا يستطيع انتظارها · العاملان كانا يرثان فحصاً HTTP لا يجيبانه | تعديلُ compose |
| **P2** | تقسيمُ ملفّات الواجهة الثلاثة (>٣٬٠٠٠ سطر) | الحجم لا الحدّ: حارسُ `fetch` قائمٌ الآن على ٨ مواضع/٣ ملفّات | تقسيمٌ تدريجيّ |
| **P2** | إغلاقُ `alembic/` أو توثيقُ مُشغِّله | نظامُ ترحيلٍ يتيم | قرار |
| **P2** | دمجُ `agent-memory/` في `sahool-brain/` أو أرشفتُه · توحيدُ صيغة سجلّ الفجوات (جدول **أو** أقسام) · ترحيلُ الـ٢٧٧ ملفّاً من الجذر | ذاكرتان تفترقان · حارسان يقرآن صيغتين | قرارُ صيغة + `git mv` بلا كسرِ الروابط |
| **P3** | `sdk/` · `developer-portal/` · `sam2-models/` · `random_forest/` · `sentinel_hub/` · `vegetation_real/` · `firmware/` — إمّا مشروعاتٌ حقيقيّة بـREADME وحارس، أو أرشيف | مجلّداتٌ بملفٍّ أو ملفّين على الجذر | قرار |

---

## ١٠ · ما لم يُقَس هنا (صراحةً)

- لا تشغيلَ حيّاً: صحّةُ الحاويات · إقلاعُ nginx · RLS على قاعدةٍ حقيقيّة · NATS · TiTiler · Flutter build. كلُّ ما وُسِم **[حيّ]** يبقى في دَين التحقّق.
- لم تُقرأ الـ٦٢٩ مرشّحاً واحداً واحداً؛ الحكمُ على ما ورد في جدول «أعلى ثقة» فقط.
- لم تُحلَّل جودةُ الاختبارات نفسِها (ما عدا الـ١٩٢ المقيسة بنيويّاً) ولا التغطيةُ لكلّ خدمة.
- لم تُراجَع `docs/adr/` الاثنا عشر موضوعاً موضوعاً، ولا `SAHOOL_v9_Technical_Architecture.md` مقابل الواقع سطراً سطراً.
- أرقامُ الواجهة (`fetch` ×٦٢) من `grep` لا من رسمِ استدعاءات؛ بعضُها قد يكون شرعيّاً (رفعُ ملفّات · تدفّق).

**أمرُ إعادة القياس** لكلّ جدول موجودٌ في عمود «مصدر القياس»؛ ما لا يُعاد قياسُه لا يُصدَّق.

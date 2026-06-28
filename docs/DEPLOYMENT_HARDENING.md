# SAHOOL — Container / Deployment Hardening

دليل تقوية الحاويات للإنتاج واسع النطاق. يفصل ما **طُبِّق في الكود** عمّا يحتاج
**بناء Docker حقيقيّاً أو بيئة تشغيل** على جهازك (لا يُتحقَّق منه في بيئة CI الحاليّة
لأنّ سياسة الشبكة تمنع apt/pip أثناء البناء).

## 0) ملفّ الـcompose المعتمد
يوجد عدّة ملفّات compose في الجذر. **المعتمد للإنتاج هو `docker-compose.v9.yml`**
(مُشار إليه في `scripts_v9/setup.sh` و`run_all.sh` والوثائق). البقيّة متغيّرات/تجارب:
- `docker-compose.unified.yml`, `docker-compose.light.yml`, `docker-compose.fixed.yml`,
  `docker-compose.erpnext.yml`, `docker-compose.odoo-snippet.yml`, `docker-compose.test.yml`.

**توصية:** أبقِ `v9` مصدراً وحيداً للحقيقة، وأرشِف/احذف الباقي أو وثّق غرض كلّ منها
صراحةً لتفادي الانحراف.

### 0.1) مقارنة `v9` ↔ `fixed` (مُتحقَّقة بالملفّ، 2026-06-28)

| البُعد | `docker-compose.v9.yml` (إنتاج) | `docker-compose.fixed.yml` (تطوير) |
|---|---|---|
| المُستخدِم | `Makefile` (`COMPOSE`)، سكربتات النشر | تشغيل تطويريّ مباشر |
| TLS | نعم (80+443، `nginx.v9.conf` بـenvsubst) | لا (HTTP فقط، `nginx.fixed.conf`) |
| فرض RLS | مُفعَّل (لا تجاوز) | مُتجاوَز للتطوير (`SAHOOL_ALLOW_RLS_BYPASS_ROLE=1`) |
| `mem_limit` / `no-new-privileges` | **أغلب الخدمات لا كلّها** (~٣٦ من ~٣٩) | ~خدمة واحدة |
| تدوير السجلّات (`*default_logging`) | نعم (json-file، 10m/5) | لا |
| `ODOO_PASSWORD` (odoo-bridge) | اختياريّ (`:-`، سطر 1013) | **إلزاميّ** (`:?`، سطر 796؛ البريدج بلا profile) |
| `TELEGRAM_BOT_TOKEN` | اختياريّ (`:-`) | إلزاميّ (`:?`) |
| `APP_DB_PASSWORD` (migrate) | إلزاميّ (`:?`) | افتراضيّ (`:-sahool_app_pw`) |
| منافذ auth/platform | خلف nginx فقط | مكشوفة `127.0.0.1:8120/8000` للمتصفّح |
| Ollama GPU | مُفعَّل (`nvidia`/`gpu`) | غائب/معلّق (آمن بلا GPU) |
| إصدارات المراقبة | Prometheus **2.53.0** · Grafana **10.4.5** | Prometheus **2.55.1** · Grafana **11.6.0** (أحدث) |

**خدمات معرّفة في `v9` فقط:** `sahool-weather-polygon-worker` · `sahool-weather-signal-engine`
· `sahool-titiler` (خادم بلاطات COG ديناميكيّ) · `sahool-fastbee` (MQTT) · `sahool-field-segmentation`.

**ملاحظات تصحيح (شائعة الخطأ):**
- `sahool-sam2-inference` **ليس** خاصّاً بـ`v9` — مُعرَّف في `fixed` أيضاً تحت `profiles: ["gpu"]`
  (`fixed:1062`). فهو مشترك، لا v9-only.
- `mem_limit`/`security_opt` **ليست على «كلّ» الخدمات** في `v9` — على أغلبها فقط (القياس المباشر:
  ~٣٦ سطر `mem_limit` مقابل ~٣٩ خدمة؛ تختلف الأرقام بطريقة العدّ، لكنّ الخلاصة: ليست الكلّ).
- `ODOO_PASSWORD` في `fixed` **إلزاميّ** (`:?`) لا اختياريّ؛ الاختياريّ هو `v9` (`:-`).
- `fixed` يحمل إصدارات مراقبة **أحدث** من `v9` (تباين مقصود/انجراف — يُوحَّد عند الرغبة).

**أيّهما تستخدم؟** `v9` للإنتاج (TLS + RLS + حدود موارد + الخدمة الكاملة). `fixed` لتطوير محلّيّ
أبسط بلا TLS مع وصول مباشر لـauth/platform من المتصفّح وبلا الخدمات الثقيلة (worker الطقس/التجزئة/TiTiler).

## 1) طُبِّق في الكود (هذه الدفعة)
- ✅ **دوران السجلّات:** `x-logging` موحّد (`max-size: 10m`, `max-file: 5`) على كلّ
  الخدمات في `v9` (كان غائباً — يمنع امتلاء القرص).
- ✅ **تثبيت الصور الأساسيّة:** كلّ Dockerfiles لبايثون → `python:3.{11,12}-slim-bookworm`
  (Debian صريح، أكثر قابليّة لإعادة الإنتاج)، و`nginx:alpine` → `nginx:1.27-alpine`.
- ✅ **تثبيت صور compose المؤكَّدة:** prometheus `v2.53.0`، alertmanager `v0.27.0`،
  grafana `10.4.5`، jaeger `1.57` (إضافةً لـredis/nats/postgis/qdrant المثبّتة أصلاً).
- ✅ **صور قابلة للتجاوز:** `minio/ollama/titiler` صارت `${X_IMAGE:-default}` — ثبّت
  إصداراً/digest في الإنتاج عبر `.env` دون تعديل الملفّ.

## 2) يحتاج تنفيذاً على جهازك (بناء Docker / بيئة تشغيل)
### أ. تثبيت بالـdigest (أقوى من الوسم)
للإنتاج، ثبّت بالـdigest غير القابل للتغيير (يتطلّب وصولاً للـregistry):
```dockerfile
FROM python:3.11-slim-bookworm@sha256:<digest>
```
وفي compose: `image: minio/minio@sha256:<digest>`. احصل على الـdigest بـ
`docker buildx imagetools inspect <image:tag>`.

### ب. تثبيت إصدارات apt (إعادة إنتاج كاملة)
حاليّاً `apt-get install -y gcc libpq-dev curl` بلا إصدارات. للإنتاج:
```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends \
      gcc=4:12.2.0-3 libpq-dev=15.* curl=7.88.* \
    && rm -rf /var/lib/apt/lists/*
```
> ملاحظة: إصدارات Debian تتغيّر؛ يُفضَّل تثبيت snapshot لمستودع apt أو استخدام صورة
> أساس مثبّتة بالـdigest بدل تثبيت كلّ حزمة (أبسط وأمتن).

### ج. بناء Python متعدّد المراحل (صورة أصغر، CVEs أقلّ)
معظم خدمات بايثون أحاديّة المرحلة فيبقى `gcc`/`libpq-dev` في الصورة النهائيّة.
النمط المُطبَّق فعلاً في المستودع — `services/edge-inference/Dockerfile.arm64` يستخدم
`pip install --user` ثمّ ينسخ `/root/.local` (لا `--prefix=/install`):
```dockerfile
FROM python:3.11-slim-bookworm AS builder
RUN apt-get update && apt-get install -y --no-install-recommends gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

FROM python:3.11-slim-bookworm           # runtime — بلا أدوات بناء
RUN apt-get update && apt-get install -y --no-install-recommends libpq5 curl \
    && rm -rf /var/lib/apt/lists/*
COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH \
    PYTHONPATH=/root/.local/lib/python3.11/site-packages:/app
COPY services/<svc>/ /app/
USER sahool
```
> أو استخدم `pip install --prefix=/install` + `COPY --from=builder /install /usr/local`
> كنمط بديل — المهمّ هو فصل أدوات البناء عن صورة التشغيل.
> ⚠ تتطلّب معرفة تبعيّات وقت التشغيل لكلّ خدمة (مثلاً `libpq5` لخدمات القاعدة،
> `libgl1/libglib2.0-0` للرؤية). طبّقها لكلّ خدمة وابنِ محليّاً للتحقّق
> (`docker build`) قبل النشر — لا تُطبَّق عمياء.

### د. الأسرار خارج environment
`JWT_SECRET`/`SAHOOL_AGENT_TOKEN`/`SH_CLIENT_SECRET`… تُمرَّر عبر `environment:`.
للإنتاج استخدم Docker/K8s secrets:
```yaml
# docker-compose (swarm) أو K8s
secrets:
  jwt_secret: { external: true }
services:
  sahool-auth:
    secrets: [jwt_secret]
    environment:
      JWT_SECRET_FILE: /run/secrets/jwt_secret   # اقرأ الملفّ في التطبيق
```
أو External Secrets Operator / Vault في Kubernetes.

### هـ. تقسيم الشبكة (public / service / data)
حاليّاً كلّ شيء على `sahool-internal` (مسطّح) — الواجهة وأيّ خدمة ترى القاعدة مباشرةً.
الهدف: عزل طبقة البيانات.
```yaml
networks:
  sahool-public:   {}                 # nginx فقط (+ منافذ 80/443)
  sahool-internal: {}                 # الخدمات ↔ الخدمات
  sahool-data:     { internal: true } # مخازن البيانات (بلا خروج)
```
- مخازن البيانات (`postgres/redis/nats/minio/qdrant`): `[sahool-data]` فقط.
- خدمات التطبيق: `[sahool-internal, sahool-data]`.
- `nginx`: `[sahool-public, sahool-internal]` — **لا** `sahool-data`.
- `frontend`: `[sahool-internal]` فقط.
> ⚠ يلزم اختبار اتّصال فعليّ بعد التطبيق (يُكشف فقط وقت التشغيل، لا عبر
> `docker compose config`) — لذا لم يُطبَّق عمياء هنا.

### و. حدود CPU
الذاكرة محكومة (`mem_limit` على ٣٣ خدمة، مُطبَّق فعليّاً في compose v2)، لكن **CPU
غير محدود**. أضِف لكلّ خدمة (قيمة تُضبَط حسب الحمل، لا قيمة واحدة عمياء):
```yaml
    cpus: "1.5"     # مثال — ضعها على الخدمات الثقيلة (ollama/video) بقيم أعلى
```
> لا تضع قيمة واحدة منخفضة للجميع (تُسبّب throttling) — اضبط لكلّ خدمة.

### ز. تفعيل قيود v47 رجعيّاً
قيود v47 أُضيفت `NOT VALID` (تُفرض على الصفوف الجديدة). بعد تدقيق البيانات:
```sql
ALTER TABLE seasons    VALIDATE CONSTRAINT fk_seasons_field_tenant;
ALTER TABLE activities VALIDATE CONSTRAINT fk_activities_field_tenant;
ALTER TABLE seasons    VALIDATE CONSTRAINT chk_seasons_dates;
ALTER TABLE fields     VALIDATE CONSTRAINT fk_fields_manager_user;
```

## 3) Kubernetes (لاحقاً)
- `requests/limits` (CPU/ذاكرة) لكلّ حاوية، `readiness/liveness probes` (موجودة
  أصلاً كـHEALTHCHECK)، `NetworkPolicy` للعزل، Secrets/ConfigMaps، PodSecurity
  (non-root موجود)، HPA على المنصّة/الواجهة.

## نقاط القوّة القائمة (تأكَّدت بالمراجعة)
تشغيل non-root (`USER sahool`/`nginx`)، HEALTHCHECK + `depends_on: condition:
service_healthy`، بناء الواجهة متعدّد المراحل، ربط المنافذ الداخليّة بـ`127.0.0.1`
(لا انكشاف عامّ — فقط `80/443` عبر nginx)، و`mem_limit` مُطبَّق.

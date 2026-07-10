# Docker Build Checklist — P-CERT Critical Services

قائمة تحقّق تشغيليّة (runbook) لبناء وإقلاع الحاويات الأربع الحرجة قبل اعتماد
Production Certification. النسخة المؤتمتة منها: وظيفة CI
[`docker-build-matrix.yml`](../../.github/workflows/docker-build-matrix.yml)
(`workflow_dispatch` + PR على مسارات الخدمات الأربع).

تغلق هذه القائمة الجزء الأوّل من **P-CERT-1** (مصفوفة Docker build) وتبدأ إثبات
**P-CERT-4** (تجهيز نماذج ONNX/SAM2) — **بلا ادّعاء إغلاقهما قبل تشغيل CI الحقيقيّ**
(حالة العوائق: `python scripts/ci/production_certification_blockers_status.py`).

## 0) الهدف

إثبات أنّ الحاويات الأربع لا "تبني فقط"، بل:

- تبني من الـDockerfile الصحيح وبسياق بناء = جذر المشروع.
- تقلع بلا أخطاء استيراد (`ModuleNotFoundError` / `ImportError` / `Traceback`).
- تملك `/healthz` صالحاً (liveness).
- تملك `/readyz` **صادقاً**: degraded/غير-جاهز مسموح، الكذب ممنوع.
- لا تستخدم mocks للإنتاج ولا تختلق مخرجات (`fabricated_* = false` دائماً).
- تفشل **fail-closed** عند غياب التبعيّات الاختياريّة (نماذج/DEM/Redis).

| الخدمة | السبب |
| --- | --- |
| raster-service | قلب الرستر والمؤشّرات، Raw QA، Cloud Strategy، Topographic/DEM QA |
| weather-service | Raw Weather QA، كاش Redis، نوافذ العمليّات |
| edge-inference | تشغيل نماذج ONNX |
| sam2-inference | نموذج القصّ (segmentation) وأوزانه |

## 1) حُرّاس ما قبل البناء

قبل أيّ `docker build` (كلّها stdlib — لا تثبيت تبعيّات):

```bash
python scripts/ci/raw_data_processing_contract_guard.py
python scripts/ci/raw_weather_processing_contract_guard.py
python scripts/ci/raster_pixel_qa_indicator_guard.py
python scripts/ci/raster_validated_product_guard.py
python scripts/ci/raster_topographic_qa_guard.py
python scripts/ci/container_fleet_contract_guard.py
python scripts/ci/vegetation_container_contract_guard.py
python scripts/ci/runtime_container_deep_contract_guard.py
python scripts/ci/ai_container_contract_guard.py --check
python scripts/ci/pip_audit_resolution_guard.py
python scripts/ci/service_dependency_conflict_guard.py --check
python scripts/ci/edge_model_contract_guard.py
python scripts/ci/edge_production_readiness_guard.py
```

النجاح المتوقّع: `*_guard_ok` / `*_check_ok` لكلّ سطر. **إذا فشل أيّ حارس هنا، لا
تبدأ البناء.**

## 2) أوامر البناء

سياق البناء دائماً جذر المشروع (`COPY services/... shared/...` تتطلّبه):

```bash
docker build -f services/raster-service/Dockerfile      -t sahool/raster-service:ci .
docker build -f services/weather-service/Dockerfile     -t sahool/weather-service:ci .
docker build -f services/edge-inference/Dockerfile.arm64 -t sahool/edge-inference:ci .
docker build -f services/sam2-inference/Dockerfile      -t sahool/sam2-inference:ci .
```

ملاحظتا صدق:

- **edge-inference لا يملك `Dockerfile` عاديّاً** — الملف الوحيد هو
  `Dockerfile.arm64`، وقاعدته `python:3.12-slim-bookworm` متعدّدة المعماريّات
  فتُبنى على amd64 أيضاً (`onnxruntime` عجلة عامّة).
- **sam2-inference صورة CUDA موجَّهة لـGPU** (RTX 4090/5090). على runner بلا GPU:
  البناء والإقلاع يثبتان سلامة الاستيراد وصدق `/readyz` فقط؛ الاستدلال الفعليّ
  يتطلّب مضيفاً بـNVIDIA Container Toolkit.

## 3) معايير قبول البناء

مرفوض مباشرةً أيّ من: `ModuleNotFoundError` · `ImportError` · `ResolutionImpossible`
· `No such file or directory` أثناء COPY · تعارض تبعيّات pip · فشل بناء wheel لحزمة
أساسيّة · **HEALTHCHECK يستخدم `/readyz` بدل `/healthz`**.

## 4) إقلاع كلّ حاوية منفردة

المنافذ أدناه من الـDockerfiles الفعليّة (منافذ compose على المضيف تختلف — مثلاً
weather يُنشر على 8092 في compose لكن منفذ الحاوية 8000).

### 4.1 raster-service (منفذ الحاوية 8001)

```bash
docker run --rm -d --name sahool-raster-ci -p 18001:8001 \
  -e FIELD_DEM_PATH= \
  sahool/raster-service:ci
curl -fsS http://localhost:18001/healthz          # يجب 200
curl -sS  http://localhost:18001/readyz || true   # degraded صادق مسموح
docker logs sahool-raster-ci --tail=100           # ممنوع: Traceback/ImportError
docker stop sahool-raster-ci
```

`FIELD_DEM_PATH=` فارغ صراحةً = DEM غائب بصدق؛ topographic QA يعلن
`dem_not_configured_for_topographic_qa` بدل اختلاق قناع.

### 4.2 weather-service (منفذ الحاوية 8000)

```bash
docker run --rm -d --name sahool-weather-ci -p 18000:8000 \
  -e WEATHER_REDIS_URL= \
  sahool/weather-service:ci
curl -fsS http://localhost:18000/healthz
curl -sS  http://localhost:18000/readyz || true   # يعلن خلفيّة الكاش بصدق
curl -sS  http://localhost:18000/contract || true # raw_weather_processing مُعلَن
docker logs sahool-weather-ci --tail=100
docker stop sahool-weather-ci
```

بلا Redis يسقط الكاش إلى الذاكرة (`cache.py`) — سقوط مُعلَن لا صامت.

### 4.3 edge-inference — وضع fail-closed أوّلاً (منفذ الحاوية 8100)

أوّل إقلاع **بدون نماذج عمداً** لإثبات عدم الاختلاق:

```bash
docker run --rm -d --name sahool-edge-ci -p 18100:8100 \
  -e EDGE_PRODUCTION_REQUIRED=true \
  -e EDGE_READINESS_MODE=strict \
  sahool/edge-inference:ci
curl -fsS http://localhost:18100/healthz          # 200 رغم غياب النماذج
curl -sS  http://localhost:18100/readyz || true   # يجب: غير جاهز + سبب النموذج الغائب
curl -sS  http://localhost:18100/capabilities || true
docker logs sahool-edge-ci --tail=100
docker stop sahool-edge-ci
```

ثمّ الاختبار الثاني **مع النماذج** (تجهيزها:
[`EDGE_MODEL_PROVISIONING_CHECKLIST.md`](EDGE_MODEL_PROVISIONING_CHECKLIST.md)):
`-v "$PWD/artifacts/edge-models:/models:ro"` ⇒ المتوقّع `ready=true` واكتشاف
النماذج بلا وضع mock.

### 4.4 sam2-inference — وضع fail-closed (منفذ الحاوية 8080)

```bash
docker run --rm -d --name sahool-sam2-ci -p 18080:8080 \
  sahool/sam2-inference:ci
curl -fsS http://localhost:18080/healthz
curl -sS  http://localhost:18080/readyz || true
docker logs sahool-sam2-ci --tail=100
docker stop sahool-sam2-ci
```

عقد صدق sam2 الحقيقيّ: `/readyz` يعيد `model_loaded=false` و`checkpoint_expected`
عند غياب الأوزان — **لا توجد رايات باسم `SAM2_PRODUCTION_REQUIRED`/
`SAM2_READINESS_MODE`** في الكود؛ الأوزان تُمرَّر عبر `SAM2_CHECKPOINT` +
`SAM2_MODEL_CFG` (mount للأوزان ثمّ إعادة فحص `/readyz` ⇒ `model_loaded=true`).
ممنوع: قصّ وهميّ أو مضلّعات مُختلَقة.

## 5) متطلّبات Docker HEALTHCHECK (الحاويات الأربع)

| الفحص | المطلوب |
| --- | --- |
| Docker HEALTHCHECK | يستخدم `/healthz` **فقط** |
| `/readyz` | لا يُستخدم كـliveness أبداً |
| تبعيّة اختياريّة غائبة | لا تقتل العمليّة؛ تُفشِل readiness لا healthz |
| سجلّات الإقلاع | بلا Traceback |

الحالة الراهنة مُتحقَّق منها: الأربعة تستخدم `/healthz` في HEALTHCHECK
(raster عبر httpx، weather عبر curl، edge/sam2 عبر urllib).

## 6) تعريف النجاح/الفشل

**Pass**: البناء ينجح · الحاوية تبدأ · `/healthz` = 200 · `/readyz` صادق ولو
degraded · سجلّات بلا أخطاء استيراد · حُرّاس الخدمة تمرّ · لا mock/اختلاق.

**Fail**: فشل بناء · خروج فوريّ للحاوية · فشل `/healthz` · Traceback في الإقلاع ·
`/readyz` يدّعي الجاهزيّة رغم غياب model/DEM/Redis في الوضع الصارم · أيّ
`fabricated_* = true`.

## 7) ترتيب التنفيذ المقترح

1. raster-service ⟵ يكشف مشاكل Docker/الاستيراد/التبعيّات بسرعة
2. weather-service
3. edge-inference بدون نماذج (fail-closed)
4. sam2-inference بدون أوزان (fail-closed)
5. edge-inference مع النماذج
6. sam2-inference مع الأوزان (يتطلّب مضيف GPU للاستدلال الفعليّ)

## 8) تكييفات عن المواصفة الأصليّة (صدق التوثيق)

المواصفة المقترحة وصلت بمنافذ/رايات افتراضيّة؛ عُدِّلت إلى الواقع المُتحقَّق منه:

| في المواصفة | الواقع في الشجرة |
| --- | --- |
| weather على 8092 | منفذ الحاوية 8000 (8092 منفذ مضيف compose فقط) |
| edge على 8180 / sam2 على 8150 | edge 8100 · sam2 8080 |
| `services/edge-inference/Dockerfile` | الموجود `Dockerfile.arm64` (قاعدة متعدّدة المعماريّات) |
| `RASTER_RUNTIME_MODE` / `WEATHER_CACHE_BACKEND` / `EDGE_MODEL_DIR` / `SAM2_PRODUCTION_REQUIRED` / `SAM2_READINESS_MODE` / `SAM2_MODEL_DIR` | غير موجودة في الكود؛ الرايات الحقيقيّة: `FIELD_DEM_PATH` · `WEATHER_REDIS_URL` · `EDGE_PRODUCTION_REQUIRED` · `EDGE_READINESS_MODE` · `SAM2_CHECKPOINT` · `SAM2_MODEL_CFG` |
| `raster_container_contract_guard.py` | غير موجود؛ يغطّيه `container_fleet_contract_guard.py` + `runtime_container_deep_contract_guard.py` |
| `dependency_inventory_guard.py --check` | غير موجود؛ يغطّيه `service_dependency_conflict_guard.py --check` + `pip_audit_resolution_guard.py` |

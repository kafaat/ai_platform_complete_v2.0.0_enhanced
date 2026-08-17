# تشغيل المنصّة في البيئة المحليّة — Runbook قابل للنسخ

مرجعه شجرة main بعد دمج ARCH-S3 (#864). كلّ كتلة أوامر هنا **قابلة للّصق كما هي**
من جذر المستودع. المرجع القانونيّ للطوبولوجيا `docker-compose.v9.yml`
(67 خدمة: 48 وحدة بناء + 19 بنية تحتيّة) — هذا الدليل لا يكرّره بل يرتّب
إقلاعه مرحليّاً ويسمّي نقاط التحقّق.

> **قاعدة أمن غير قابلة للتفاوض**: ملفّ `.env` الحقيقيّ لا يُلتزم أبداً
> (`.gitignore` يمنعه ويستثني `.env.example` وحده). لا تطبع قيمه في سجلّات
> ولا تلصقه في محادثات. عند الشكّ افحص **المفاتيح فقط**.

---

## ٠) المتطلّبات

- Docker Engine + Docker Compose v2 (`docker compose version`).
- ≥ 8 GB RAM للنواة (المراحل أ+ب)، و≥ 16 GB لجناح RAG والأجنحة الاختياريّة.
- منافذ حرّة محليّاً: `80` و`443` (nginx) و`127.0.0.1:5432` (postgres)
  و`127.0.0.1:9000/9001` (MinIO).

```bash
docker compose version
git rev-parse --short HEAD   # وثّق الشجرة التي تشغّلها
```

## ١) تهيئة البيئة

```bash
cp .env.example .env
# عدّل الأسرار المحليّة على الأقلّ:
#   POSTGRES_PASSWORD / DB_PASSWORD / APP_DB_PASSWORD / JWT_SECRET
#   MINIO_ROOT_USER / MINIO_ROOT_PASSWORD
# مفاتيح الأقمار (SH_*/CDSE_*) اختياريّة محليّاً — غيابها يعطّل جلب الصور لا الإقلاع.
```

ملاحظتان مقيستان من عقد compose↔env:

- `RAG_RETRIEVAL_SHADOW` افتراضيّه `false` — **أبقِه كذلك محليّاً**؛ حارس
  التقارب (`scripts/architecture/rag_authority_convergence_guard.py`) يفرض
  أنّ الظلّ معطَّل افتراضيّاً في مرحلة parity، وفشل القناة القانونيّة تسجيل
  صريح لا سقوط صامت.
- كلّ متغيّر يستهلكه compose مُعلَن في `.env.example` — بوّابة
  `compose_env_contract_gate` تحجب أيّ متغيّر غير مُعلَن.

## ٢) المرحلة أ — نواة البنية التحتيّة + الهجرات

```bash
docker compose -f docker-compose.v9.yml up -d \
  sahool-postgres sahool-redis sahool-redis-state sahool-nats \
  sahool-minio sahool-minio-init
docker compose -f docker-compose.v9.yml up sahool-migrate   # يخرج 0 عند اكتمال الهجرات
```

تحقّق:

```bash
docker compose -f docker-compose.v9.yml ps --format 'table {{.Name}}\t{{.Status}}'
docker compose -f docker-compose.v9.yml exec sahool-postgres \
  psql -U "${POSTGRES_USER:-sahool}" -d "${POSTGRES_DB:-sahool}" -c 'SELECT postgis_version();'
```

## ٣) المرحلة ب — المنصّة والبوّابة

`sahool-platform` يعتمد على `sahool-field-segmentation` (بناء ثقيل أوّل مرّة —
انتظر اكتمال البناء قبل الحكم على الصحّة):

```bash
docker compose -f docker-compose.v9.yml up -d --build sahool-platform sahool-nginx
```

تحقّق (مسارات البنية القانونيّة عبر البوّابة):

```bash
curl -fsS http://localhost/healthz && echo OK-liveness
curl -fsS http://localhost/readyz  && echo OK-readiness
curl -fsS http://localhost/runtime-identity   # git_sha/build_id — طابق git rev-parse
```

## ٤) المرحلة ج — جناح RAG (دلالات S3: تكافؤ لا قطع)

الخدمتان `sahool-rag-retrieval` و`sahool-local-ai-rag` تعتمدان على
`sahool-qdrant` و`sahool-ollama`، وعقد التضمين الواحد
(`docs/architecture/rag_embedding_contract.json`) يفرض `nomic-embed-text`
عبر Ollama — **البُعد يُقرأ من الاستجابة الحيّة لا من ثابت**:

```bash
docker compose -f docker-compose.v9.yml up -d sahool-qdrant sahool-ollama
docker compose -f docker-compose.v9.yml exec sahool-ollama ollama pull nomic-embed-text
docker compose -f docker-compose.v9.yml up -d --build sahool-rag-retrieval sahool-local-ai-rag
# بذر مجموعة المعرفة (اختياريّ — يملأ sahool_agri_kb):
docker compose -f docker-compose.v9.yml up sahool-qdrant-seed
```

تحقّق من موقف السلطة الصادق (يطبع `stage=parity · NOT_YET_AUTHORITATIVE`):

```bash
python scripts/architecture/rag_authority_convergence_guard.py
```

## ٥) الأجنحة الاختياريّة (profiles)

لا تعمل إلّا عند طلبها صراحةً:

| profile | الخدمة | متى تحتاجه |
|---|---|---|
| `gpu` | `sahool-sam2-inference` | استدلال تجزئة الحقول على GPU (مع `docker-compose.v9.gpu.yml`) |
| `odoo` | `sahool-odoo` | تكامل ERP |
| `model-lifecycle` | `sahool-model-lifecycle-adapter` | دورة حياة النماذج |
| `irrigation-runtime` | عامل حجوزات الريّ | تشغيل الريّ الحيّ |
| `relay` | عامل ترحيل الحجوزات | نفسه |

```bash
docker compose -f docker-compose.v9.yml --profile odoo up -d sahool-odoo
# GPU (يتطلّب nvidia-container-toolkit):
docker compose -f docker-compose.v9.yml -f docker-compose.v9.gpu.yml --profile gpu up -d sahool-sam2-inference
```

والمراقبة عند الحاجة:

```bash
docker compose -f docker-compose.v9.yml up -d \
  sahool-prometheus sahool-grafana sahool-jaeger sahool-alertmanager
```

## ٦) الاختبارات محليّاً

```bash
python -m pip install -r requirements.txt
python -m pip install -r requirements-dev.txt
pytest -m unit                      # الافتراضيّ السريع — بلا خدمات
pytest -m integration               # فقط بعد المرحلتين أ+ب (يتطلّب Postgres+PostGIS وRedis)
bash scripts/ci/preflight.sh --fast # ~٣٠ث · 14 حارساً قبل أيّ دفع
```

## ٧) الإيقاف والتنظيف

```bash
docker compose -f docker-compose.v9.yml down            # يوقف ويبقي البيانات
docker compose -f docker-compose.v9.yml down --volumes  # ⚠ يمحو قواعد البيانات والمجموعات
```

## ٨) أعطال شائعة مقيسة

| العرض | السبب المقيس | العلاج |
|---|---|---|
| `readyz` أحمر بعد الإقلاع مباشرة | الاعتماديّات ما تزال تُبنى/تُهاجَر | انتظر `sahool-migrate` يخرج 0 ثمّ أعد الفحص |
| `local-ai-rag`/`rag-retrieval` لا تجهز | نموذج التضمين غير مسحوب في ollama | `ollama pull nomic-embed-text` (خطوة المرحلة ج) |
| رفض بُعد المتّجهات عند البذر/الاستعلام | مجموعة Qdrant قديمة ببُعد مختلف | العقد يقرأ البُعد حيّاً — أعد إنشاء المجموعة أو أعد البذر |
| منفذ 80/5432 مشغول | خدمة مضيف محليّة | حرّر المنفذ أو عدّل النشر في compose موضعيّاً (لا تلتزم التعديل) |
| تفعيل `RAG_RETRIEVAL_SHADOW=true` محليّاً ثمّ فشل بوّابة | مخالفة عقد مرحلة parity | أرجعه `false`؛ الظلّ يُقاس لا يُشغَّل افتراضيّاً |

---

**حدود هذا الدليل**: تشغيل محليّ للتطوير والقياس فقط — لا يمنح أيّ ادّعاء
production (ذاك مساره `docs/runbooks/PRODUCTION_CERTIFICATION_CHECKLIST.md`
وسلسلة التصديق L5). وقبل أيّ دفع: بروتوكول
[`CI_GATES_AND_PRE_PUSH_PROTOCOL.md`](CI_GATES_AND_PRE_PUSH_PROTOCOL.md).

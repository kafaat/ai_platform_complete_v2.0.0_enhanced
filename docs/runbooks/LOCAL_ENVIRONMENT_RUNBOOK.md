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
- Python **3.12** لاختبارات المضيف. لا تستعمل Python 3.13 مع
  `tests_v9/requirements-test.txt`: الحزمة المثبّتة `scipy==1.13.1` لها عجلة
  Windows لـ3.12 ولا تملك عجلة لـ3.13، فيحاول `pip` البناء عبر Meson ويفشل إن لم
  توجد سلسلة C/C++؛ هذا عدم توافق إصدار، لا عطل PostgreSQL.
- ≥ 8 GB RAM للنواة (المراحل أ+ب)، و≥ 16 GB لجناح RAG والأجنحة الاختياريّة.
- منافذ حرّة محليّاً: `80` و`443` (nginx) و`127.0.0.1:5432` (postgres)
  و`127.0.0.1:9000/9001` (MinIO).

```bash
docker compose version
git rev-parse --short HEAD   # وثّق الشجرة التي تشغّلها
```

### Windows/PowerShell — تثبيت Python الصحيح جنباً إلى جنب

PostgreSQL المثبّت على Windows **ليس** قاعدة هذا التشغيل. الصورة القانونية في
`docker-compose.v9.yml` هي `postgis/postgis:15-3.4`، وكل الخدمات تتصل باسم
`sahool-postgres:5432` داخل شبكة Compose. لا تحدّث PostgreSQL المضيف ولا تمرّر
مساره إلى الاختبارات؛ تحقّق فقط أنه لا يحتجز المنفذ المضيف `5432`.

نفّذ الكتلة التالية من PowerShell في جذر المستودع. هي تُبقي Python 3.13 كما هو
وتنشئ بيئة مستقلة بـ3.12، ولا تعتمد على `py` launcher:

```powershell
$ErrorActionPreference = 'Stop'

winget install --exact --id Python.Python.3.12 --scope user

$Py312 = Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe'
if (-not (Test-Path $Py312)) {
  throw "Python 3.12 was not found at $Py312. Reopen PowerShell after winget finishes."
}

& $Py312 -c "import sys; assert sys.version_info[:2] == (3,12), sys.version; print(sys.executable, sys.version)"
& $Py312 -m venv .venv-py312
$VenvPython = Join-Path $PWD '.venv-py312\Scripts\python.exe'

& $VenvPython -m pip install --upgrade pip setuptools wheel
# حاجب مبكر: يجب تنزيل wheel، ولا يجوز السقوط إلى Meson/source build.
& $VenvPython -m pip install --only-binary=:all: scipy==1.13.1
& $VenvPython -m pip install -r requirements-dev.txt -r tests_v9/requirements-test.txt
& $VenvPython -c "import sys, scipy; assert sys.version_info[:2] == (3,12); assert scipy.__version__ == '1.13.1'; print('host-test-runtime=OK', sys.version, scipy.__version__)"
```

تحقّق من ملكيّة المنفذ قبل تشغيل الحاوية:

```powershell
Get-NetTCPConnection -LocalPort 5432 -State Listen -ErrorAction SilentlyContinue |
  Select-Object LocalAddress,LocalPort,OwningProcess
docker compose -f docker-compose.v9.yml config --quiet
docker compose -f docker-compose.v9.yml up -d sahool-postgres
docker compose -f docker-compose.v9.yml ps sahool-postgres
docker compose -f docker-compose.v9.yml exec -T sahool-postgres `
  psql -U sahool_user -d sahool -c "SELECT version(), postgis_version();"
```

إذا كشف الأمر الأول خدمة PostgreSQL مضيفة على `5432`، أوقف **تلك الخدمة مؤقتاً**
أو حرّر المنفذ قبل `compose up`. لا تغيّر صورة PostgreSQL ولا تثبّت خادماً جديداً
على Windows لمعالجة هذا التعارض.

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
  psql -U sahool_user -d sahool -c 'SELECT postgis_version();'
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

Linux/macOS مع Python 3.12:

```bash
python3.12 -m venv .venv-py312
. .venv-py312/bin/activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install --only-binary=:all: scipy==1.13.1
python -m pip install -r requirements-dev.txt -r tests_v9/requirements-test.txt
python -m pytest -m unit             # الافتراضيّ السريع — بلا خدمات
python -m pytest -m integration      # فقط بعد المرحلتين أ+ب (يتطلّب Postgres+PostGIS وRedis)
PATH="$PWD/.venv-py312/bin:$PATH" bash scripts/ci/preflight.sh --fast
```

Windows/PowerShell بعد كتلة 3.12 أعلاه:

```powershell
$VenvPython = Join-Path $PWD '.venv-py312\Scripts\python.exe'
& $VenvPython -m pytest -m unit
& $VenvPython -m pytest -m integration
# preflight.sh يحتاج Git Bash؛ مرّر venv في PATH ولا تدعه يعود إلى Python 3.13.
$env:PATH = "$(Join-Path $PWD '.venv-py312\Scripts');$env:PATH"
bash scripts/ci/preflight.sh --fast
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
| منفذ 80/5432/8554 مشغول (`ports are not available`) | خدمة مضيف محليّة، أو نطاقٌ محجوز على Windows | `python scripts/check_compose_host_ports.py` يسمّي المنفذ ومتغيّر نقله؛ انقله في `.env` (القسم ٨أ) — لا تعدّل compose |
| تفعيل `RAG_RETRIEVAL_SHADOW=true` محليّاً ثمّ فشل بوّابة | مخالفة عقد مرحلة parity | أرجعه `false`؛ الظلّ يُقاس لا يُشغَّل افتراضيّاً |

### ٨أ) Windows: `ports are not available … Only one usage of each socket address`

العرض كما أبلغ عنه المالك (2026-11-03) عند `docker compose -f docker-compose.v9.yml up`:

```text
Error response from daemon: ports are not available: exposing port TCP 127.0.0.1:8554 -> 127.0.0.1:0:
listen tcp4 127.0.0.1:8554: bind: Only one usage of each socket address (protocol/network address/port) is normally permitted.
```

`8554` هو منفذ RTSP على المضيف لـ`sahool-zlmediakit` (خادم الوسائط، بلا profile ⇒ يُقلِع افتراضيّاً).
سببان شائعان: (١) عمليّةٌ أخرى تستمع عليه (خادم RTSP/كاميرا/VLC، أو حاوية SAHOOL قديمة ما زالت
تعمل)، (٢) المنفذ داخل **نطاقٍ يحجزه winnat** لـHyper-V/WSL2/Docker Desktop — فلا تجد له عمليّة.

**١. الفحص المسبق (بلا bash، يعمل في PowerShell/cmd):**

```powershell
py scripts\check_compose_host_ports.py            # أو: python scripts\check_compose_host_ports.py
py scripts\check_compose_host_ports.py -f docker-compose.v9.yml -f docker-compose.v9.gpu.yml
```

يقرأ كلّ `ports:` ويستوفي `${VAR:-default}` كما يفعل Compose (البيئة أوّلاً ثمّ `.env`)، ثمّ يجرّب
ربط كلّ منفذ ويطبع المشغول (`BUSY`) أو المرفوض (`DENIED`، نطاق winnat غالباً) أو المنشور مرّتين
(`CONFLICT`) مع الخدمة و`الملفّ:السطر` و**المتغيّر الذي ينقله** ومنفذاً حرّاً مقترحاً. يخرج بـ1 إن
وُجد ما سيُفشِل `up`. وحدوده مذكورة في رأسه (منفذٌ تحمله حاويات المكدّس نفسه وهي تعمل يُعَدّ مشغولاً).

**٢. من يحمل المنفذ:**

```powershell
netstat -ano | findstr :8554                       # آخر عمود = PID
tasklist /FI "PID eq <PID>"                        # اسم العمليّة
docker ps --filter publish=8554                    # حاوية (من هذا المكدّس أو غيره)؟
netsh interface ipv4 show excludedportrange protocol=tcp   # هل 8554 داخل نطاقٍ محجوز؟
```

**٣. العلاج — بالترتيب:**

- **انقل المنفذ (الأسلم، لا يمسّ النظام):** أضِف إلى `.env` ثمّ أعِد `up`:

  ```dotenv
  ZLM_RTSP_HOST_PORT=18554
  ```

  كلّ منفذ مضيف في `docker-compose*.yml` صار قابلاً للنقل بمتغيّر (الافتراضيّ = القيمة السابقة،
  والربط يبقى `127.0.0.1` عدا بوّابة nginx): `ZLM_HTTP_HOST_PORT` · `ZLM_RTSP_HOST_PORT` ·
  `ZLM_RTMP_HOST_PORT` · `ZLM_RTP_HOST_PORT` · `POSTGRES_HOST_PORT` · `MINIO_API_HOST_PORT` ·
  `MINIO_CONSOLE_HOST_PORT` · `NGINX_HTTP_HOST_PORT` · `NGINX_HTTPS_HOST_PORT` … والقائمة الكاملة
  بتعليقها في `.env.example` تحت «منافذ المضيف المنشورة». **تنبيه:** `ZLM_RTP_HOST_PORT` (WebRTC/UDP)
  يغيّر منفذ المضيف فقط ومرشّحو ICE يعلنون 10000 — نقلُه يكسر WebRTC ما لم يُضبط `rtc.port` معه.
- **أوقف الحائز** إن كان حاوية قديمة (`docker compose -f docker-compose.v9.yml down`) أو عمليّة لا تلزمك.
- **نطاق winnat المحجوز** (لا عمليّة في `netstat` والمنفذ داخل `excludedportrange`) — في PowerShell
  **كمسؤول**، وهو يقطع الشبكة لحظيّاً عن WSL/Hyper-V:

  ```powershell
  net stop winnat
  docker compose -f docker-compose.v9.yml up -d     # يحجز Docker منافذه قبل أن يعيد winnat حجز النطاقات
  net start winnat
  ```

  وإن تكرّر بعد كلّ إقلاع فنقلُ المنفذ بالمتغيّر أعلاه هو الحلّ الدائم (لا تعدّل نطاقات النظام لأجل منفذ واحد).

---

**حدود هذا الدليل**: تشغيل محليّ للتطوير والقياس فقط — لا يمنح أيّ ادّعاء
production (ذاك مساره `docs/runbooks/PRODUCTION_CERTIFICATION_CHECKLIST.md`
وسلسلة التصديق L5). وقبل أيّ دفع: بروتوكول
[`CI_GATES_AND_PRE_PUSH_PROTOCOL.md`](CI_GATES_AND_PRE_PUSH_PROTOCOL.md).

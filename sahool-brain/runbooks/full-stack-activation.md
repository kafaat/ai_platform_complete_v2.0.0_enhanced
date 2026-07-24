# رَنبوك التشغيل — Full-Stack Activation (رفع الـstack الكامل + البراهين الحيّة)

> **قابل للنسخ من الشاشة.** كتل الأوامر للّصق المباشر في صدفة المُشغّل على staging.
> **رَنبوك تنسيق (hub) لا تكرار:** يرفع الـmesh الكامل (خدمات + nginx + Redis + MinIO) ويشغّل
> البراهين التي تحتاجه، ثمّ **يُحيل** للرَّنبوكات القائمة لما هو مغطّى.
>
> **يبني على:** [`pg16-staging-activation.md`](pg16-staging-activation.md) — نفّذ **G1+G2** منه أوّلاً
> (PG16+PostGIS + 219 هجرة + RLS) قبل هذا الرَّنبوك. هنا نضيف بقيّة الـmesh والبراهين فوق تلك الأرضيّة.
>
> **عقد الصدق:** الأسرار عبر البيئة فقط (لا في المحادثة/ملفّ مُتعقَّب) · `production_certified` يبقى
> `false` حتى الشهادة الحيّة · «مؤشّر ≠ إثبات» (لا ترقية `verified` بلا برهان curl/psql/مسبار) ·
> لا TLS معطَّل. الـstack القانونيّ: **`docker-compose.v9.yml`** (67 خدمة).

---

## 0. أسرار الـmesh (البيئة فقط)

```bash
# قاعدة البيانات (من رَنبوك PG16):
export APP_DB_PASSWORD="…"   JOBS_DB_PASSWORD="…"
# Redis (نسختان: sahool-redis + sahool-redis-state):
export REDIS_PASSWORD="$(openssl rand -hex 24)"
# MinIO (S3): root + مفاتيح لكلّ خدمة:
export MINIO_ROOT_USER="sahool-admin"
export MINIO_ROOT_PASSWORD="$(openssl rand -hex 24)"
export RASTER_S3_ACCESS_KEY="…"        RASTER_S3_SECRET_KEY="…"
export SCOUT_INGEST_S3_ACCESS_KEY="…"  SCOUT_INGEST_S3_SECRET_KEY="…"
# (compose يفشل-مغلق إن غاب أيّ سرّ مُعلَّم :?required — لا قبول صامت)
export COMPOSE="docker compose -f docker-compose.v9.yml"   # + -f pg16 override إن لزم PG16
```

---

## 1. رفع البنية التحتيّة (Postgres · Redis · MinIO)

```bash
# القاعدة + الهجرات: من pg16-staging-activation.md §1–§2 (لا تُكرَّر هنا).
$COMPOSE up -d sahool-postgres sahool-redis sahool-redis-state sahool-minio
$COMPOSE up --no-deps --exit-code-from sahool-minio-init sahool-minio-init   # يُنشئ الدلاء + مفاتيح الخدمات

# صحّة حقيقيّة (لا افتراض):
until $COMPOSE exec -T sahool-postgres pg_isready -U postgres >/dev/null 2>&1; do sleep 2; done
$COMPOSE exec -T sahool-redis       redis-cli -a "$REDIS_PASSWORD" ping   # PONG
$COMPOSE exec -T sahool-redis-state redis-cli -a "$REDIS_PASSWORD" ping   # PONG
curl -fsS http://localhost:9000/minio/health/ready && echo " minio-ready"
```
**بوّابة G-INFRA:** أيّ فشل صحّة ⇒ **أوقِف**؛ لا ترفع الخدمات فوق بنية غير جاهزة.

---

## 2. رفع الخدمات + بوّابة nginx

```bash
$COMPOSE up -d sahool-platform sahool-raster-service sahool-nginx \
              sahool-sentinel-hub-mcp sahool-weather-mcp sahool-wofost-mcp
# (أضِف ما تحتاجه البراهين: decision-service/scout-ingest/auth/weather-service …)

# صحّة/جاهزيّة عبر البوّابة:
curl -fsS http://localhost:8000/health  && echo " platform-health"
curl -fsS http://localhost/healthz      && echo " nginx-edge"       # عبر nginx
```
**بوّابة G-SVC:** health غير 200 ⇒ افحص `$COMPOSE logs <svc>` قبل أيّ برهان.

---

## 3. البراهين التكامليّة (`-m integration`)

تتطلّب Postgres+PostGIS+Redis مرفوعة (لا تُشغَّل بدونها — تُتخطّى بصمت في CI):
```bash
export DATABASE_URL="postgresql://sahool_app:${APP_DB_PASSWORD}@localhost:5432/sahool"
pytest -m integration -q            # سلسلة القرار/الطقس/الأقمار/العزل عبر القاعدة الحيّة
```
> ملاحظة صدق مُسجَّلة: بعض «إخفاقات» الجناح تكامليّة-harness (تظليل حزمة `routers`/`shared` عبر
> الخدمات في عمليّة واحدة — عائلة SHARED-PACKAGE المقبولة)؛ شغّل الملفّ المعنيّ منفرداً للتأكيد.

---

## 4. إثبات Track 1 الحيّ (MCP `analyze_field_change` فوق CDSE)

الكود مُغلَق @ `762dd61`؛ الإثبات = **sentinel-hub-mcp + raster-service مرفوعان** ونداء حقيقيّ.
الأداة قراءة-فقط (`satellite:read`)، تقرأ النقطة القانونيّة `GET /v1/fields/{id}/timeseries` من
raster-service (`services/mcp_servers/sentinel_hub_server.py:439`)، **fail-closed 424** عند قلّة المشاهدات.

```bash
# 1) توكن نطاق satellite:read (من auth؛ لا يُلصَق في المحادثة):
TOKEN="…"   # bearer بنطاق satellite:read

# 2) نداء الأداة عبر خادم MCP (POST /mcp/v1/tools/call):
curl -fsS -X POST http://localhost:8000/mcp/v1/tools/call \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"name":"analyze_field_change","arguments":{"field_id":"<FID>","index":"ndvi","since":"2026-03-01"}}'
```
**المتوقّع (صدق):**
- حقل بمشاهدتين مؤهَّلتين+ ⇒ ملخّص `{from,to,delta,direction,observations_used,source:"raster-service",real_data:true}`.
- مشاهدات < 2 (أو سحاب>30%/غير مقيس) ⇒ **424** `insufficient authoritative observations` (لا مقارنة مُلفَّقة).
- بلا `satellite:read` ⇒ 403 · بلا توكن ⇒ 401.

> لا حساب طيفيّ ولا تفسير زراعيّ داخل MCP (التفسير في decision-service). سجّل النتيجة في `log.md`.

---

## 5. SEASON-EDGE-LIVE-PROOF (#225)

مسبار بوّابة nginx الحيّ (X-Canonical مزوَّرة ⇒ 401 · مُراجِع owner/expert ⇒ 200 · إعادة قبول ⇒ 409):
→ **نفّذه في** [`season-record-entry.md §3`](season-record-entry.md) (لا يُكرَّر هنا).
المسار المحميّ: `nginx/nginx.v9.conf:403` (`/api/v1/seasons/{id}/accept` — توقيع الحافّة + حقن توكن الخدمة).

---

## 6. الخدمات الثلاث بلا مستهلك (رفع + تحقّق صحّة — لا اختراع مستهلك)

> **صدق حاكم:** هذه UNCONSUMED-INTENTIONAL / INTERNAL-FUTURE (سجلّ `gaps/registry.md#CODE-CLOSABLE-DEFERRED-SWEEP`).
> رفعها يُثبت **صحّة الخدمة** لا وجود مستهلك؛ لا نصنع مستهلكاً مُختلَقاً.

| الخدمة | حالة compose/nginx | ما يُثبَت حيّاً | ما يبقى (محفّز) |
|---|---|---|---|
| `sahool-agriai-engine` (`:149`) | في compose · nginx `/api/agriai/` **شبكات خاصّة فقط** (`nginx.v9.conf:469` deny-public) | health + وصول داخليّ من شبكة الحاويات (curl من حاوية داخل الشبكة) | مستهلك فعليّ (صفر مُنادٍ في `services/`/`frontend/`) — محفّز SIM-GOLDEN/تكامل مقصود |
| `sahool-remote-sensing-workspace-bff` (`:1019`) | في compose · **بلا مسار nginx** | health مباشر داخل الشبكة | مسار بوّابة + واجهة مستهلِكة (BFF مستقبليّ) |
| `gis-workflow-service` | **غير موجود في compose** (INTERNAL/FUTURE) | — | إضافته إلى compose+nginx أوّلاً (خارج نطاق هذا الرفع) — أداة حدود إداريّة/خرائط طباعة |

```bash
# رفع المنشورتين (agriai + rs-bff) والتحقّق داخل الشبكة (لا تعريض عامّ):
$COMPOSE up -d sahool-agriai-engine sahool-remote-sensing-workspace-bff
$COMPOSE exec -T sahool-nginx sh -c 'wget -qO- http://sahool-agriai-engine:8000/health || true'
$COMPOSE exec -T sahool-nginx sh -c 'wget -qO- http://sahool-remote-sensing-workspace-bff:8000/health || true'
# التأكيد أنّ /api/agriai/ محجوب عامّاً (يجب 403 من خارج الشبكات الخاصّة):
curl -s -o /dev/null -w '%{http_code}\n' http://localhost/api/agriai/   # متوقّع 403
```
**لا تُرقَّ أيّ منها إلى «مُستهلَك» في السجلّ** — تبقى UNCONSUMED-INTENTIONAL حتى يظهر مُنادٍ حقيقيّ.

---

## 7. الإحالات (المغطّى مسبقاً — لا تُكرَّر)

- **الفئة 3 (أقمار CDSE/Sentinel-2 + MinIO):** [`docs/runbooks/SATELLITE_IMAGERY_RUNBOOK.md`](../../docs/runbooks/SATELLITE_IMAGERY_RUNBOOK.md)
  (backfill · خنق 429 · عامل السحب · `raster_assets` · الخطّ الزمنيّ · تمييز demo/حقيقيّ).
- **التحقّق الحيّ الكامل (بيانات + mesh):** [`docs/runbooks/REAL_ENV_VERIFICATION_RUNBOOK.md`](../../docs/runbooks/REAL_ENV_VERIFICATION_RUNBOOK.md).
- **فهرس الترتيب الرئيسيّ (①-1..①-4):** [`docs/runbooks/OPERATOR_DISPATCH_BACKLOG_LIVE_EXECUTION.md`](../../docs/runbooks/OPERATOR_DISPATCH_BACKLOG_LIVE_EXECUTION.md).
- **تحويل DECISION-SoR:** [`pg16-staging-activation.md §5.1`](pg16-staging-activation.md) → `docs/runbooks/DECISION_SERVICE_SOR_*`.

---

## 8. التفكيك ونظافة الأسرار

```bash
$COMPOSE down                     # يُبقي volumes (القاعدة/MinIO) — استخدم -v للحذف الكامل
```
- أيّ سرّ ظهر في سجلّ/رسالة خطأ ⇒ **يُدوَّر فوراً** (سابقة APP_PW في جلسة سابقة).
- لا تترك أسراراً في `.env` مُتعقَّب؛ استخدم مدير أسرار/`.env` غير مُتعقَّب.
- سجّل نتائج البراهين في `log.md` + رقِّ حالات `gaps/registry.md` (`fixed`→`verified`) **فقط ببرهان حيّ ملموس**.

---

### فهرس الاعتماديّة (مختصر)
```
pg16 G1+G2 (قاعدة+هجرات+RLS) ─▶ §1 بنية (redis+minio) ─▶ §2 خدمات+nginx
                                                          ├─▶ §3 -m integration
                                                          ├─▶ §4 Track1 MCP (sentinel-hub-mcp+raster)
                                                          ├─▶ §5 SEASON-EDGE #225 (→ season-record §3)
                                                          └─▶ §6 الخدمات الثلاث (صحّة لا مستهلك)
الفئة 3 (أقمار) ────────────────────────────────────────▶ SATELLITE_IMAGERY_RUNBOOK (مغطّى)
```

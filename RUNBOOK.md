# RUNBOOK — تشغيل منصّة سهول محليّاً/حيّاً

دليل تشغيل موجز للتحقّق الحيّ (E2E، الطقس، Edge، WebSocket، MFA). كلّ الكود مدموج في
`main`؛ هذا الملفّ يوثّق **كيف تُشغّله بنفسك** (لا يمكن تشغيله داخل بيئة CI المعزولة).

## أيّ compose؟

| الملفّ | الغرض | يشمل |
|--------|-------|------|
| **`docker-compose.v9.yml`** | **القانونيّ/الكامل (موصى به للتشغيل الفعليّ)** | مسار **Edge** الآمن (`/api/edge/`)، أدوار RLS الحقيقيّة (`sahool_app`)، قولبة nginx (envsubst)، كلّ الخدمات |
| `docker-compose.fixed.yml` | بداية تطوير سريعة مُختزَلة | **بلا** مسار Edge (بوّابة غير مُقولَبة)، **تجاوز RLS مُفعَّل** (dev فقط)، soil مُعطَّل، depends_on مُقلَّم |

> للتحقّق الحيّ الكامل (خصوصاً Edge pest-detect وعزل RLS) استخدم **`docker-compose.v9.yml`**.
> `fixed.yml` للتجربة السريعة فقط؛ تجاوز RLS فيه افتراضيّ (1) ولا يُستخدَم خارج المحلّيّ
> (حارس CI `tests_v9/test_compose_rls_bypass_guard.py` يمنع تسرّبه لأيّ compose إنتاجيّ).

## 1) الإعداد

```bash
cp .env.example .env
```
املأ المتغيّرات **الإلزاميّة** (وإلّا يرفض compose الإقلاع):
`JWT_SECRET · DATABASE_URL · DB_PASSWORD · REDIS_PASSWORD · MINIO_ROOT_PASSWORD ·
QDRANT_API_KEY · ADMIN_PASSWORD · GRAFANA_PASSWORD · SH_CLIENT_ID · SH_CLIENT_SECRET ·
TELEGRAM_BOT_TOKEN · TELEGRAM_WEBHOOK_SECRET · ODOO_PASSWORD · SAHOOL_AGENT_TOKEN`

- **`SAHOOL_AGENT_TOKEN`** مهمّ: تحقنه بوّابة v9 في رأس `X-Agent-Token` لمسار `/api/edge/`
  (Edge pest-detect)؛ بدونه يردّ Edge ‏401 بصدق.

## 2) أعلام الميزات المتقدّمة (FEATURE_* / VITE_ENABLE_*)

الراوترات المتقدّمة مُطفأة افتراضاً ⇒ الـbackend يردّ 404، والواجهة تعرض حالة **«ميزة
غير مُفعَّلة»** صادقة (لا شاشة مكسورة). لتفعيلها:

- **Backend (وقت التشغيل):** اضبط `FEATURE_*=1` في `.env` (مُمرَّرة الآن في `v9.yml`
  و`fixed.yml` بقيم `${...:-0}`). المصدر: `services/sahool-platform/api/feature_registry.py`.
- **Frontend (وقت البناء):** اضبط `VITE_ENABLE_*=true` **قبل** بناء صورة الواجهة (متغيّرات
  Vite تُحقَن وقت البناء لا التشغيل). الخريطة في `frontend/src/lib/featureFlags.ts`.

| الصفحة | Backend `FEATURE_*` | Frontend `VITE_ENABLE_*` |
|--------|----------------------|---------------------------|
| nl-gis | `FEATURE_NATURAL_LANGUAGE_GIS` | `VITE_ENABLE_NL_GIS` |
| decision-studio | `FEATURE_DECISION_STUDIO` | `VITE_ENABLE_DECISION_STUDIO` |
| decision-confidence | `FEATURE_DECISION_CONFIDENCE` | `VITE_ENABLE_DECISION_CONFIDENCE` |
| execution-feedback | `FEATURE_EXECUTION_FEEDBACK` | `VITE_ENABLE_EXECUTION_FEEDBACK` |
| lineage | `FEATURE_UNIFIED_LINEAGE` | `VITE_ENABLE_UNIFIED_LINEAGE` |
| learning-dashboard | `FEATURE_LEARNING_DASHBOARD` | `VITE_ENABLE_LEARNING_DASHBOARD` |
| evidence-map | `FEATURE_EVIDENCE_MAP` | `VITE_ENABLE_EVIDENCE_MAP` |
| replay-map | `FEATURE_REPLAY_MAP` | `VITE_ENABLE_REPLAY_MAP` |
| operations-wall | `FEATURE_OPERATIONS_WALL` | `VITE_ENABLE_OPERATIONS_WALL` |
| irrigation-network | `FEATURE_IRRIGATION_NETWORK` | `VITE_ENABLE_IRRIGATION_NETWORK` |
| portfolio-command | `FEATURE_PORTFOLIO_COMMAND` | `VITE_ENABLE_PORTFOLIO_COMMAND` |
| device-twin | `FEATURE_DEVICE_TWIN` | `VITE_ENABLE_DEVICE_TWIN` |

(`FEATURE_DELTA_SYNC` و`FEATURE_GIS_KERNEL` خلفيّان بلا صفحة مخصّصة.)

## 3) الإقلاع

```bash
docker compose -f docker-compose.v9.yml up -d --build      # أوّل مرّة بطيء (يبني ~15 صورة)
docker compose -f docker-compose.v9.yml ps                 # انتظر healthy
docker compose -f docker-compose.v9.yml logs -f sahool-platform sahool-auth sahool-nginx
```
nginx يستمع على `80/443`.

## 4) فحص الدخان الجاهز (register → login → field → workspace)

```bash
BASE_URL=http://localhost python scripts/smoke_e2e.py
```

## 5) الفحوص الحيّة المتبقّية

- **الطقس:** `GET /api/v1/weather/current?lat=..&lon=..` ⇒ بيانات Open-Meteo حقيقيّة.
- **الدردشة:** الواجهة تستدعي `/api/agent/query` (supervisor، JWT) ⇒ ردّ `response_ar`.
- **Edge pest-detect (v9):** `POST /api/edge/inference/pest-detect` بـJWT صالح + صورة
  (البوّابة تحقن `X-Agent-Token`؛ يلزم ضبط `SAHOOL_AGENT_TOKEN`).
- **Agent health:** `GET /api/agent/health` ⇒ 200.
- **WebSocket:** اتّصل بـ`/ws/notifications` وأرسل أوّل إطار `{"type":"auth","token":"<JWT>"}`
  ⇒ قبول؛ توكن خاطئ ⇒ إغلاق 1008.
- **MFA:** `POST /auth/mfa/setup` → امسح QR في تطبيق TOTP → `POST /auth/mfa/activate`
  بالرمز، ثمّ سجّل دخولاً برمز MFA.
- **Push (FCM):** يتطلّب مشروع Firebase + `google-services.json`/APNs + جهاز حقيقيّ.

## ملاحظات تطوير

- **تجاوز RLS:** `SAHOOL_ALLOW_RLS_BYPASS_ROLE=1` افتراضيّ في `fixed.yml` فقط (لا يُنشئ
  `sahool_app`). **لا تستخدم `fixed.yml` في الإنتاج.** v9 يستعمل `sahool_app` ويُبقي
  الحارس مُفعَّلاً.
- **إقلاع أسرع للتطوير:** في `fixed.yml` بوّابة nginx لم تعد تنتظر صحّة الخدمات الثقيلة
  الاختياريّة (market/odoo/rag) — `service_started` بدل `service_healthy`.

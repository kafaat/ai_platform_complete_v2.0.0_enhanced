# PRODUCTION_WEATHER_DEPLOYMENT_CHECKLIST

قائمة نشر مختصرة لمحرّك الطقس (SAHOOL Weather Engine) — تُنفَّذ على **مضيف به Docker**.
ملاحظة: تشغيل `docker compose` والفحص البصريّ وPlaywright الحقيقيّ **تتطلّب مضيفاً به
Docker daemon ومتصفّح** (لا يمكن إثباتها داخل صندوق CI/الوكيل بلا daemon).

> آخر تحديث: محرّك الطقس عبر v28 (طبقة `soil_temperature_10_40cm` + تفضيلات المستخدم
> + Redis-ready cache + حدّ معدّل + جسر المهام/التوصيات). الحالة: اختبارات Python/Frontend
> build خضراء؛ هذا الملفّ يغطّي إثبات التشغيل الكامل المتبقّي.

---

## 1) متغيّرات البيئة (env vars)

| المتغيّر | القيمة الموصى بها | ملاحظة |
|---|---|---|
| `SAHOOL_ENV` | `production` | يُفعّل المسارات الصارمة |
| `JWT_SECRET` | ≥ 32 حرفاً | إلزاميّ (auth) |
| `DATABASE_URL` | دور مقيّد `sahool_app` (NOSUPERUSER NOBYPASSRLS) | لا تتّصل كـ`postgres`/مالك الجداول |
| `REDIS_URL` أو `SAHOOL_WEATHER_REDIS_URL` | `redis://redis:6379/0` | لتفعيل كاش/حدّ المعدّل على Redis |
| `SAHOOL_WEATHER_CACHE_BACKEND` | `redis` | وإلّا `memory` (تطوير) |
| `SAHOOL_WEATHER_RATE_LIMIT_BACKEND` | `redis` | حدّ معدّل موزَّع عبر الحاويات |
| `SAHOOL_AGENT_TOKEN` | سرّ قويّ | يحرس النقاط الإداريّة (انظر §5) |
| `RASTER_PUBLIC_PREFIX` | حسب النشر | بادئة tilejson العامّة |

> الكاش/الحدّ يسقطان تلقائيّاً للذاكرة إن غاب Redis (مقبول للتطوير، غير مثاليّ للإنتاج متعدّد الحاويات).

---

## 2) أوامر Docker Compose

```bash
docker compose build
docker compose up -d
docker compose ps        # تأكّد أنّ nginx/gateway · frontend · sahool-platform · redis · db: healthy
docker compose logs -f sahool-platform   # راقب الإقلاع (lifespan/الهجرات)
```

إن فشل `sahool-auth` بـ`unhealthy`: راجع `docker logs <project>-sahool-auth-1` — غالباً
`.env` (دور DB يتجاوز RLS، أو `JWT_SECRET` قصير) لا كود.

---

## 3) فحوص الصحّة (health checks) — runtime

```bash
# عامّة (لا تحتاج توكن):
curl -fsS http://localhost:<port>/api/v1/weather/readyz        # 200 {"status":"ready"...}
curl -fsS http://localhost:<port>/api/v1/weather/self-test     # 200 فحص جافّ
curl -fsS http://localhost:<port>/api/v1/weather/layers        # قائمة الطبقات (شامل soil_temperature_10_40cm)

# بلاطة الطبقة الجديدة (عمق حرارة التربة):
curl -fsS "http://localhost:<port>/api/v1/weather/tile-data/8/155/108?layer=soil_temperature_10_40cm&time=now&model=best_match"
# توقّع 200 مع value/sample وحقل soil_temperature_10_40cm_c (مشتقّ من 6/18/54 سم).

# محميّة بـService Token (X-Agent-Token) — انظر §5:
curl -fsS -H "X-Agent-Token: $SAHOOL_AGENT_TOKEN" http://localhost:<port>/api/v1/weather/env-doctor
curl -fsS -H "X-Agent-Token: $SAHOOL_AGENT_TOKEN" http://localhost:<port>/api/v1/weather/runtime-contract
```

---

## 4) فحوص المتصفّح (browser checks) — يدويّ في MapHub

افتح `/fields/map-center?...&weather=1` وتأكّد بصريّاً من:
- [ ] طبقة الحرارة + طبقة `soil_temperature_10_40cm` (10-40 سم) تُصيَّران.
- [ ] wind animation overlay + legend ظاهران.
- [ ] probe popup عند النقر (طقس زراعيّ + نوافذ العمليّات).
- [ ] أزرار «إنشاء مهمّة» و«حفظ توصية» تعملان (تتطلّب تسجيل دخول + صلاحيّة).
- [ ] تفضيلات المستخدم تبقى بعد إعادة فتح الخريطة (الطبقة/الزمن/الشفافيّة…).
- [ ] لا تعارض بين الطقس وNDVI/CDSE؛ لوحة الطقس لا تغطّي أدوات الرسم.

---

## 5) سياسة وصول النقاط (access policy)

| النقطة | السياسة | الحارس |
|---|---|---|
| `readyz` · `self-test` · `layers` | عامّة (أو داخليّة حسب النشر) | — |
| `tile-data` · `operation-*` · `probe` · `current/forecast/historical` · `action-recommendation` | عامّة (بإحداثيّات، لا بيانات مستأجِر) | rate-limit |
| `observability` · `rate-limit/backend` · `tile-cache/backend` · `tile-cache/stats` · `runtime-smoke-plan` | عامّة للقراءة (بنية تحتيّة) | — |
| **`metrics.prom`** | داخليّ (Prometheus) | `X-Agent-Token` |
| **`env-doctor` · `runtime-contract`** | internal/admin | `X-Agent-Token` |
| **`tile-cache/prune`** (POST مُتلِف) | admin/service-token | `X-Agent-Token` |
| `tasks/from-operation-plan` · `recommendations/from-operation-plan` (POST) | مستخدِم مُصرَّح | `require_permission` (FIELD_EDIT / RECOMMENDATION_REQUEST) |

> في الإنتاج خلف بوّابة nginx، نقاط `/api/v1/` كلّها خلف `auth_request` ما لم تُستثنَ صراحةً؛
> الحارس أعلاه دفاع عمق على مستوى التطبيق (يفرضه `tests_v9/test_endpoint_auth_coverage.py`).

---

## 6) فحوص Redis (إنتاج متعدّد الحاويات)

```bash
docker compose exec redis redis-cli ping        # PONG
curl -fsS -H "X-Agent-Token: $SAHOOL_AGENT_TOKEN" .../weather/env-doctor | jq '.checks'   # cache/rate backend=redis
curl -fsS .../weather/tile-cache/stats          # بعد عدّة طلبات بلاطات: items>0
curl -fsS -X POST -H "X-Agent-Token: $SAHOOL_AGENT_TOKEN" ".../weather/tile-cache/prune?expired_only=true"
docker compose exec redis redis-cli --scan --pattern 'sahool:weather:*' | head
```

---

## 7) فحوص Prometheus (مقاييس الكاش/المحرّك)

```bash
curl -fsS -H "X-Agent-Token: $SAHOOL_AGENT_TOKEN" .../weather/metrics.prom | grep sahool_weather_
# توقّع: sahool_weather_cache_items · _requests_total · _cache_states_total · _upstream_total …
```
اربط بـPrometheus scrape مع رأس `X-Agent-Token` (نقطة داخليّة).

---

## 8) Playwright E2E (واجهة، بلا خلفيّة)

```bash
cd frontend
npx playwright install chromium
npm run e2e:weather-smoke -- --project=chromium
```
الاختبار يُحاكي نقاط `/api/v1/weather/*` ويسجّل دخولاً تجريبيّاً ثمّ يفتح MapHub ويتأكّد من
عقد الطقس + أزرار الإجراءات + الاستيفاء، بلا انهيار تطبيق.

---

## 9) Rollback

```bash
docker compose down                      # إيقاف
git checkout <previous-green-sha>        # العودة لـSHA أخضر سابق
docker compose build && docker compose up -d
```
الكاش في الذاكرة يُفقَد عند إعادة التشغيل (يُعاد بناؤه من Open-Meteo)؛ كاش Redis يبقى.

---

## 10) حدود معروفة (known limitations)

- `soil_temperature_10_40cm` **مشتقّ** من أعماق Open-Meteo (6/18/54 سم) لا بلاطة Meteoblue
  أصليّة (`provider_native=false` في المانيفست) — تقريب بصريّ مطابق لوضع «10-40 cm down».
- بلا Redis: الكاش وحدّ المعدّل **لكلّ حاوية** (غير موزَّع) — مقبول تطويريّاً فقط.
- الاستيفاء (interpolation) تحسين بصريّ؛ القيم الدقيقة من نقطة `probe`.
- النقاط الإداريّة تعتمد `SAHOOL_AGENT_TOKEN`؛ بلا ضبطه تُرفَض بـ403 (سلوك آمن مقصود).

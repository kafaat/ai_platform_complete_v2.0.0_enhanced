# 🌾 مزوّدو البيانات (Data Providers)

> كلّ مزوّد بمصدره + **ملاحظة الصدق** (مبدأ النظام: لا تلفيق — إن غاب المصدر يُرَدّ 503/قيمة
> `available=false` صريحة لا رقم مُختلَق).

## ① Element84 Earth Search — STAC (صور Sentinel-2/1 مجّاناً)

- **الخدمة:** `sahool-raster-service` (المنفذ الداخليّ **8001**) —
  [`services/raster-service/main.py`](../../services/raster-service/main.py).
- **المصدر:** `EARTH_SEARCH_URL = https://earth-search.aws.element84.com/v1`
  (`services/raster-service/main.py:69`). Sentinel-2 L2A مجّانيّ (AWS Open Data)، إعادة زيارة ٥
  أيّام (`main.py:26-27`). رادار Sentinel-1 يخترق الغيوم (`main.py:14`).
- **مرونة STAC:** إعادة محاولة + كاش TTL + بديل (Planetary Computer / DEAfrica) عبر
  `STAC_MAX_RETRIES`/`STAC_CACHE_TTL`/`STAC_FALLBACK_ENABLED` (`docker-compose.v9.yml:695-700`).
- **ملاحظة الصدق:** raster-service هو **مصدر الحقيقة البكسليّة**؛ `vegetation-analysis` يُفضّله
  ويُعلِّم التقديرات التركيبيّة كـfallback (لا حقائق متنافسة) —
  [`SAHOOL_PRODUCTION_GAP_REPORT_v1.md`](../../SAHOOL_PRODUCTION_GAP_REPORT_v1.md):56-57.

## ② Open-Meteo — الطقس (منطق حقيقيّ في المنصّة)

- **الموصِّل:** [`services/sahool-platform/api/connectors/openmeteo.py`](../../services/sahool-platform/api/connectors/openmeteo.py).
- **المصدر:** `FORECAST_URL = https://api.open-meteo.com/v1/forecast` و
  `HISTORICAL_URL = https://archive-api.open-meteo.com/v1/archive`
  (`api/connectors/openmeteo.py:124-125`)، مع قاطع دائرة (`openmeteo_breaker_state`، `:59`).
- **ملاحظة الصدق:** مسار «الطقس-للتوصية» النشط يعمل عبر `weather_automation` + `openmeteo` (لا عبر
  أنبوب الطقس الشبكيّ الخامد `weather_grid` — انظر فجوة H2 في
  [`../gaps/registry.md`](../gaps/registry.md) و`SAHOOL_PRODUCTION_GAP_REPORT_v1.md`:58-61).

## ③ SAM2 — تقطيع الحقل (GPU، opt-in)

- **الخدمة:** `sahool-sam2-inference` (المنفذ 8080) — **opt-in خلف `profile=gpu`** فقط
  (`docker-compose.v9.yml:1351-1356`) — [`services/sam2-inference/main.py`](../../services/sam2-inference/main.py).
  يفعّل `auto/hybrid` في `sahool-field-segmentation`
  ([`services/field-segmentation/main.py`](../../services/field-segmentation/main.py)).
- **ملاحظة الصدق (503 صادقة):** بلا نموذج محمّل ⇒ `_PREDICTOR=None` ⇒ `/predict` يردّ 503 صادقاً
  لا نتيجة مُختلَقة (`services/sam2-inference/main.py:74,101,196`). والمسار اليدويّ في
  field-segmentation حقيقيّ؛ `auto/hybrid` بلا خطّاف ⇒ 503 صادق (`field-segmentation/main.py:12,40`).
  التشغيل الكامل: [`docs/SAM2_DEPLOYMENT.md`](../../docs/SAM2_DEPLOYMENT.md).

## ④ التربة (Soil) — مُعلَّق (stub)

- **الحالة:** خدمة `soil-service` **مُعلَّقة** في الـcompose (ملفّ غير مكتمل،
  `docker-compose.v9.yml:1289-1302`). الوصول الحاليّ يُمرَّر عبر المنصّة (`/api/soil/` →
  `platform_backend/api/soil/`، `nginx.v9.conf:218`).
- **ملاحظة الصدق:** لا تُولَّد قيم تربة مُلفَّقة من خدمة غير منشورة؛ مؤشّرات التربة المتاحة فعليّاً
  تأتي من Sentinel-2 عبر raster-service (`services/raster-service/main.py:122`).

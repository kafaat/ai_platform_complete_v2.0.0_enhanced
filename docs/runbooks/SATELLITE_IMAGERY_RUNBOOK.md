# RUNBOOK — صور الأقمار (CDSE/Sentinel‑2) والخطّ الزمنيّ

دليل تشغيليّ لمسار صور الأقمار: تشغيل الـbackfill التاريخيّ، التعامل مع خنق CDSE (429)،
عامل السحب، التحقّق من حفظ `raster_assets`، التحقّق من الخطّ الزمنيّ، وتمييز البيانات
التجريبيّة عن الحقيقيّة. كلّ الأوامر تُنفَّذ على مكدّس **`docker-compose.v9.yml`** (القانونيّ).

> مصادر الحقيقة (كود، لا تخمين): `services/raster-service/` · `services/sahool-platform/api/routers/fields.py` ·
> `docker-compose.v9.yml`. الترحيلات في `migrations/MANIFEST.txt` + `scripts_v9/run_migrations.sql`.

---

## 0) الأعلام والـenv ذات الصلة (raster-service + backfill worker)

| المتغيّر | الافتراض | الأثر |
|---|---|---|
| `RASTER_ASYNC_BACKFILL_ENABLED` | `true` | يُفعّل عامل السحب المستقلّ (`sahool-raster-backfill-scan-worker`). |
| `RASTER_CACHE_INVALIDATION_ENABLED` | `true` | يُفعّل عامل إبطال الكاش (يستهلك `raster_cache_invalidations`). |
| `RASTER_LAYER_EVICT_ENABLED` | `true` | إخلاء طبقات الذاكرة عبر العمليّات (Redis pub/sub، قناة `raster:layer_evict`). |
| `CDSE_PROCESS_MIN_INTERVAL_SECONDS` | `2.0` | أدنى تباعُد بين نداءات CDSE Process API (بوّابة على مستوى العمليّة). |
| `CDSE_PROCESS_MAX_RETRIES` | `5` | حدّ إعادة المحاولة عند 429. |
| `CDSE_PROCESS_RETRY_BASE_SECONDS` / `_MAX_SECONDS` | `5` / `120` | تراجع أُسّيّ محدود، يحترم `Retry-After`. |
| `HISTORICAL_SEARCH_PROVIDER` | `cdse` | مصدر البحث التاريخيّ (CDSE حصراً؛ fail‑closed 503 بلا اعتمادات). |
| `FIELD_DEM_PATH` | `` (فارغ) | مسار DEM لإحصاءات التضاريس؛ فارغ ⇒ `computed=false` صادق. |

---

## 1) تشغيل backfill تاريخيّ لحقل

عبر المنصّة (tenant‑verified، لا يتسرّب `X-Agent-Token` للمتصفّح):

```
POST /api/v1/fields/{field_id}/imagery/backfill
{ "months": 24, "indices": ["ndvi","ndmi"], "max_cloud_pct": 60 }
```

- المنصّة تتحقّق من ملكيّة الحقل، تستنتج `geometry_revision`، وتُمرّر لـraster‑service.
- المعالجة عبر **CDSE Process API** (لا VRT). المشاهد تُرتَّب بالجودة (`_rank_scenes`).
- **حالة التشغيل** (نقطة داخليّة في raster‑service، بتوكن الخدمة عبر البوّابة):
  `GET /api/raster/v1/fields/{field_id}/imagery/backfill/{run_id}` (رأس `X-Agent-Token`) ⇒
  `completed` / `completed_with_errors` + عدّادات `items_persisted/failed/skipped`.
  أو مباشرةً من القاعدة:

```sql
SELECT status, items_persisted, items_failed, items_skipped, updated_at
FROM backfill_runs WHERE id = '<run_id>';
```

الوضع غير المتزامن (موصى به للمدى الطويل): يُدرِج صفوف `backfill_run_items` ويلتقطها عامل
السحب (`FOR UPDATE SKIP LOCKED`) — لا يحجب الطلب.

---

## 2) خنق CDSE (429) — التشخيص والضبط

الأعراض: سجلّ raster يُظهر `CDSE Process API rate limited status=429 attempt=n/5 sleeping=…`.

آليّة الحماية (مبنيّة): بوّابة تباعُد `_throttle_process_api` (قفل عبر الخيوط) + حلقة إعادة
محاولة في `process_index` تحترم `Retry-After` (`_retry_after_seconds`).

الضبط عند استمرار 429:
1. **ارفع** `CDSE_PROCESS_MIN_INTERVAL_SECONDS` (مثلاً 3.0–5.0).
2. **أبقِ نسخة عامل واحدة لكلّ حساب CDSE** (لا تُوسّع أفقيّاً على نفس الحساب).
3. راقب `CDSE_PROCESS_MAX_RETRIES` — الاستنفاد يرفع الخطأ (لا يُخفيه)، فيُحتسَب العنصر `failed`.

```
docker compose -f docker-compose.v9.yml logs -f sahool-raster-backfill-scan-worker | grep -i "429\|rate"
```

---

## 3) عامل السحب — إعادة التشغيل والاستشفاء

```
docker compose -f docker-compose.v9.yml restart sahool-raster-backfill-scan-worker
docker compose -f docker-compose.v9.yml logs --tail=100 sahool-raster-backfill-scan-worker
```

- **استرداد الحجز (lease reclaim):** العناصر العالقة في `searching/queued/processing` تُستعاد بعد
  مهلة (`make_interval(secs => …)`) فلا تضيع عند تعطّل مؤقّت.
- **صدق إعادة المحاولة التزايُديّة:** عند تصادم `ON CONFLICT (tenant_id, idempotency_key) DO NOTHING`
  لا يُسقَط العنصر بصمت — إن كان الأصل `ready` يُخطَّى، وإلّا يُعاد إلى `queued` ليُعاد سحبه؛
  التصادم غير القابل للاستعادة يُحتسَب `failed` لا نجاحاً كاذباً.

---

## 4) التحقّق أنّ `raster_assets` حُفِظت فعلاً

```sql
-- داخل postgres (دور القراءة): آخر الأصول الجاهزة لحقل
SELECT field_id, index_name, acquisition_date, asset_status, cog_uri, cloud_pct, geometry_revision
FROM raster_assets
WHERE field_id = '<field_id>' AND asset_status = 'ready'
ORDER BY acquisition_date DESC
LIMIT 20;
```

- **القرّاء يقرؤون `asset_status = 'ready'` حصراً** (لا يعرضون `pending/stale/failed`).
- التكرار على مستوى المنتَج (بلا `cog_uri` في مفتاح الهويّة، v145) ⇒ لا صفوف مكرّرة للتاريخ×المؤشّر.
- إن كان `cog_uri` يبدأ بـ`file://` ولم يُرفع لـS3: راجع تهيئة S3 (`object_store.py`) — الانحدار المحلّيّ يُعلَن لا يُخفى.

---

## 5) التحقّق من الخطّ الزمنيّ (المنتَج للواجهة)

```
# تواريخ COG المتوفّرة (خام):
GET /api/v1/fields/{field_id}/available-dates?limit=240
# الخطّ الزمنيّ الجاهز (محدود بالأشهر + thumbnail_url لكل تاريخ):
GET /api/v1/fields/{field_id}/imagery/timeline?months=24
```

- كلّ عنصر: `{date, has_cog, cloud_pct, indices, thumbnail_url}`؛ `thumbnail_url` يعرض **True Color**
  (`/api/raster/.../cdse-thumbnail.png?index=truecolor&date=…&tid=…`)، مقصوصاً على هندسة الحقل.
- **لا تاريخ بلا COG حقيقيّ.** الواجهة تُحمّل المصغّرات كسولاً عبر هذه الروابط (لا تجلب 24 شهراً دفعةً).
- إن كان الخطّ فارغاً رغم backfill ناجح: تأكّد أنّ العامل مُفعّل، وأنّ الأصول `asset_status='ready'` (القسم 4).

---

## 6) الحالة الموحّدة للحقل (مصدر حقيقة واحد للشاشات)

```
GET /api/v1/fields/{field_id}/state       # الحالة القانونيّة (NDVI/تربة/طقس/ماء/حدود/جاهزيّة)
GET /api/v1/fields/{field_id}/state/full  # تجميعة كاملة (field/geometry/season/soil/irrigation/alerts…)
```

كلّ قسم في `state/full` best‑effort: تعذّره ⇒ `{"available": false, "reason": …}` صادق (لا 503 للكلّ).
المصادر بلا خزن حقيقيّ لكل حقل (عينات ماء مخبريّة، اقتصاد لكل حقل) تُعلَن `available:false` + مؤشّر endpoint.

---

## 7) تمييز البيانات التجريبيّة (demo) عن الحقيقيّة

القاعدة: **الصفّ حقيقيّ ما لم يُعلَن صراحةً `real_data === false`.** مصدر واحد في الواجهة:
`frontend/src/lib/realData.ts` (`isRealData` / `filterRealData` / `hasDemoData`) + مكوّن `DemoBadge`.

| الإشارة | المعنى |
|---|---|
| `real_data: false` | صفّ تجريبيّ (كتلة DEMO في `services/api.ts`؛ معرّفات `demo-field-*`). |
| `status: 'demo-only'` / `source: 'demo-only'` | لوحة/بيانات mock (تحت `VITE_MOCK_MODE` فقط). |
| `dem_auto_fill.available: false` | لا DEM مُهيّأ ⇒ تضاريس غير محسوبة (لا رقم مفبرك). |
| `computed: false` (terrain) | لا DEM/لا bbox ⇒ مظروف صادق. |

الشاشات القراريّة (ترتيب الحقول، حقول المشكلات، …) **تستبعد** الصفوف التجريبيّة من الحساب،
وتُظهر `DemoBadge` حين استُبعِد ديمو — فالاستبعاد مرئيّ لا صامت.

---

## 8) إبطال الكاش عند تعديل هندسة الحقل

- تعديل الهندسة يُنتِج صفّ `raster_cache_invalidations` (status `pending`) عبر `mark_raster_cache_stale`.
- عامل الإبطال (`RASTER_CACHE_INVALIDATION_ENABLED`) يستهلكه: يحذف/يعلّم بلاطات `tile_cache/<tenant>/<field>/…`،
  يعلّم `raster_assets.asset_status='stale'`، ثمّ `processed`.
- إخلاء طبقات الذاكرة عبر العمليّات مُفعَّل بـ`RASTER_LAYER_EVICT_ENABLED` (Redis pub/sub).

```sql
SELECT status, count(*) FROM raster_cache_invalidations GROUP BY status;  -- راقب تصريف pending
```

---

## 9) فحوص سريعة (health)

```
docker compose -f docker-compose.v9.yml ps                      # الخدمات صحّيّة؟
curl -s http://localhost:8001/readyz                            # raster-service جاهز؟
docker compose -f docker-compose.v9.yml logs --tail=50 sahool-raster-service
```

> ملاحظة صدق: هذا الملفّ يوثّق التشغيل الحيّ الذي يتعذّر داخل CI المعزول. بوّابة CI تُغطّي
> **Integration على PostGIS حيّ** + **Playwright E2E** على كلّ دفعة؛ أمّا تفعيل العمّال كخدمات
> compose في الإنتاج + تزويد DEM حقيقيّ فتحقّق تشغيليّ/نشريّ يتبع هذا الـRunbook.


---

## 10) بذر مزرعة الجوف/السنيدار التشغيليّة (اختياريّ، من بيانات مرجعيّة حقيقيّة)

لإظهار مزرعة الجوف الحقيقيّة (6 مناطق) في الشاشات بدل الاعتماد على إنشاء يدويّ:

```bash
psql "$DATABASE_URL" -v tenant_id="'<TENANT-UUID>'" \
     -f scripts/seed/aljawf_sunaydar_farm.sql
```

- يُدخِل **6 حقول** (من `farm_map.yaml`) + **6 مواسم** (Z1 قمح ×3 من `yield_history.csv`: 2.6→4.5→6.17 طن/هـ؛ Z2 قمح · Z3 برسيم · Z6 أشجار — نشطة، محاصيلها من `farm_map`) + **فحص تربة مرجعيّ** (من `sunaydar_soil_reference.yaml`: pH 8.2 · CaCO3 31% · ...).
- **idempotent** (ON CONFLICT DO UPDATE) — آمن للتكرار. مُثبَت على Postgres حيّ (6/6/1، بلا تكرار).
- **صدق:** الإحداثيّات على مستوى المديريّة (16.15N)؛ حدود الحقل وGPS الحقليّ الدقيق **معلّقان** (يرسمها المشغّل لاحقاً؛ 7 عيّنات تنتظر تحقّق GPS). لا مضلّع مفبرك.
- بعدها: شغّل backfill (القسم 1) لهذه الحقول لتظهر صورها الفعليّة، وقاعدة معرفة السنيدار (RAG) تُبذَر عبر خدمة `sahool-qdrant-seed` في compose.

## 11. طبقات التضاريس (Hillshade / Slope / Contours) — تفعيلها بتزويد DEM

الطبقات الثلاث (بلاطتا Hillshade وSlope + كنتور Vector) جاهزة كوديّاً وتعمل fail-closed
**صادقاً بلا DEM**: بلاطة شفّافة / `features:[]` مع `available:false`/`computed:false`. لا تُصيَّر
أيّ تضاريس مُلفَّقة. لتفعيلها بمنطقة حقيقيّة:

1. **زوّد DEM** (يُنصَح Copernicus GLO‑30، ~30م، مجّانيّ، رخصة مفتوحة). حمّل بلاطات المنطقة
   وادمِجها (`gdalbuildvrt`/`gdal_merge`) إلى ملفّ واحد (GeoTIFF/COG، EPSG:4326، nodata مضبوط).
2. **اضبط المسار** في بيئة `raster-service` (و`raster-backfill-scan-worker` إن لزم):
   `FIELD_DEM_PATH=/data/dem/aljawf_glo30.tif` (mount الملفّ في الحاوية).
3. أعِد تشغيل `raster-service`. تحقّق:
   - `GET /api/raster/v1/terrain/tilejson?layer=slope` ⇒ `available:true` + `legend`.
   - `GET /api/raster/v1/fields/<id>/contours.geojson?bbox=…` ⇒ `computed:true` + `features[]`.
4. في الواجهة: مبدّلات «التضاريس/الانحدار/خطوط الكنتور» فوق الخريطة تعرض الطبقات؛ قبل التزويد
   تُظهر رسالة «التضاريس غير مُهيّأة» الصادقة.

**تحقّق الحسابات:** الميل ٪ يُحسَب بأمتار الأرض (تصحيح mercator بـcos(lat))؛ nodata مُقنَّع
(`masked=True`)؛ الكنتور عبر مربّع مسير نقيّ (بلا اعتماد خارجيّ). اختبار سلوكيّ:
`services/raster-service/test_terrain_render.py` (DEM اصطناعيّ).

## 12. طبقة التربة (SoilGrids) — تفعيلها بتزويد مصدر Raster

طبقة خصائص التربة البصريّة (pH/طين/رمل/طمي/كربون عضويّ/CEC/نيتروجين/كثافة) جاهزة كوديّاً
وتعمل **fail-closed صادق بلا مصدر**: بلاطة شفّافة + `available:false` + تحذير إلزاميّ دائم
(«SoilGrids تقديريّ ~250م، لا يُغني عن المختبر»). **توجيهيّة لاختيار مواقع العيّنات فقط.**

للتفعيل:
1. **حمّل SoilGrids GeoTIFF** (ISRIC، CC‑BY 4.0) للخصائص/الأعماق المطلوبة عبر WCS
   (`https://maps.isric.org/mapserv?map=/map/<property>.map`) أو من مستودع SoilGrids،
   وقصّها على منطقتك. سمِّ كلّ ملفّ `<property>_<depth>.tif` (مثل `phh2o_0-5cm.tif`،
   `clay_0-30cm`… الأعماق: 0-5cm/5-15cm/15-30cm/30-60cm/60-100cm/100-200cm).
2. ضع الملفّات في مجلّد واحد واضبط `SOILGRIDS_DIR=/data/soilgrids` في بيئة `raster-service`
   (mount المجلّد). القيم تبقى بوحدة SoilGrids المُخزّنة — التحويل يجري في `soil_render`.
3. أعِد تشغيل `raster-service`. تحقّق:
   `GET /api/raster/v1/soil/tilejson?property=phh2o&depth=0-5cm` ⇒ `available:true` + `legend`.
4. في الواجهة: مبدّل «طبقة التربة (SoilGrids)» + منتقيا الخاصّيّة/العمق + الأسطورة + التحذير.

**تكامل مع أخذ العيّنات:** الطبقة توجيهيّة؛ مُخطِّط العيّنات القائم (v61: grid/zone/hybrid،
`/api/v1/sampling/strategy`) واستيعاب المختبر (`/api/v1/lab/*`) يبقيان مصدر القرار. اختبار
سلوكيّ: `services/raster-service/test_soil_render.py` (SoilGrids اصطناعيّ).

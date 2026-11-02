# دليل التحقّق: المؤشّرات بالبكسل فوق الخريطة · الصور التاريخيّة قبل إنشاء الحقل · أزرار المدد

> **الغرض:** التحقّق، بأوامر تُنسخ من الشاشة، من ثلاثة أمور ومن إصلاحات 2026-11-02 المرتبطة بها:
> 1. المؤشّرات (NDVI وغيره) تُعرَض فوق الخريطة **بكسلاً بكسلاً** من COG الحقل، لا متوسّطاً للحقل.
> 2. يمكن تحميل صور الأقمار **لثلاثة أشهر قبل إنشاء الحقل** (والمدد 6/12/24 شهراً).
> 3. **أزرار المدد** مفعّلة وتغيّر الطلب فعلاً، ولا يبقى في الواجهة زرّ مدّةٍ لا يغيّر شيئاً.
>
> **ما يُصلحه هذا الدليل نفسه ويتحقّق منه:**
> - `RASTER-INTEGER-RASTER-MASKED-FILL-NAN-SWALLOWED-01`: قراءة raster صحيح (SoilGrids Int16، DEM Int16) كانت تفشل بصمت.
> - مُحدِّد «7 أيام/30 يوم/3 أشهر/سنة» في لوحة المؤشّرات كان لا يغيّر الاستعلام، فأُزيل.
> - `SOILGRIDS-REST-OFFICIALLY-PAUSED-NO-ALTERNATE-PATH-01`: مسجَّلة `open`؛ علاجها نسخةٌ محلّيّة (القسم ٥).
>
> **حدود صريحة:** هذا الدليل لا يغيّر Railway ولا قاعدة البيانات ولا يشغّل المهاجر. الأوامر الحيّة
> قراءةٌ، عدا طلب backfill بـ`dry_run: true` (لا يكتب) وطلبٍ واحد اختياريّ بلا `dry_run` في ٣.٤.

---

## ٠. المتغيّرات (انسخ مرّةً واحدة، ثمّ عدّل القيم)

```bash
# واجهة staging (البوّابة نفسها تخدم /api و/api/raster)
export BASE="https://sahool-frontend-staging.up.railway.app"
# JWT المستخدم: من المتصفّح بعد الدخول — DevTools ⇒ Application ⇒ Cookies ⇒ sahool_at
export TOKEN="الصق_التوكن_هنا"
# معرّف حقلٍ تملكه (من رابط الحقل في الواجهة أو من القائمة في ٣.١)
export FIELD_ID="الصق_معرّف_الحقل"
export AUTH=(-H "Authorization: Bearer ${TOKEN}" -H "Cookie: sahool_at=${TOKEN}")
command -v jq >/dev/null || echo "ثبّت jq أوّلاً"
```

---

## ١. التحقّق من الدمج (محلّيّاً، قراءة git فقط)

```bash
git fetch -q origin main
git log --oneline -15 origin/main | grep -E "#13(2[2-9]|3[0-9])" || echo "لا دمج مطابق — حدّث القائمة"
# شجرة كلّ دمجٍ = شجرة رأسه المختبَر (أمثلة من 2026-11-02):
for pair in "37c6770ef e6a4e2fb6" "1a9c37323 d5a8b9d7c"; do
  set -- $pair
  [ "$(git rev-parse "$1^{tree}")" = "$(git rev-parse "$2^{tree}")" ] \
    && echo "OK   $1 == $2" || echo "FAIL $1 != $2"
done
```

**المتوقَّع:** `OK` لكلّ زوج.

---

## ٢. الاختبارات المحلّيّة (بلا شبكة)

### ٢.١ قراءة raster صحيح بـnodata (SoilGrids/DEM)

```bash
cd services/raster-service
python3 -m pytest -q -p no:cacheprovider test_raster_crs_window.py
cd - >/dev/null
```

**المتوقَّع:** `6 passed`. على `main` قبل الإصلاح تحمرّ الثلاثة الجديدة:
`test_read_field_window_int16_nodata_becomes_nan` و`test_soil_summary_and_zones_on_int16_soilgrids_layers` و`test_terrain_on_int16_dem`.

### ٢.٢ نافذة الصور التاريخيّة: 3 أشهر تسبق إنشاء الحقل

```bash
cd services/raster-service
python3 -m pytest -q -p no:cacheprovider test_historical_backfill.py -k "three_months or custom_range or policy"
cd - >/dev/null
```

**المتوقَّع:** نجاح `test_backfill_three_months_reaches_before_field_creation`. أقدم نطاق بحث STAC يبدأ قبل اليوم
بنحو 93 يوماً (31×3)، ولا يُقصّ عند تاريخ إنشاء الحقل (`raster_date_geo.py:46-58`).

### ٢.٣ أزرار المدد في الواجهة

```bash
cd frontend
npm ci --no-audit --no-fund --loglevel=error
npx vitest run \
  src/sections/MapHubBackfillMonthButtons.static.test.ts \
  src/sections/MapHubTwoYearBackfill.static.test.ts \
  src/sections/HybridIndexPage.noInertPeriod.static.test.ts
npx tsc --noEmit -p .
cd - >/dev/null
```

**المتوقَّع:** كلّ الاختبارات ناجحة، و`tsc` بلا مخرجات.

### ٢.٤ الجناح الكامل لخدمة raster (كما في CI)

```bash
cd services/raster-service
python3 -m pytest -q -p no:cacheprovider test_*.py
cd - >/dev/null
```

**المتوقَّع (2026-11-02):** `1169 passed, 2 skipped` على الأقلّ، بلا إخفاق.

---

## ٣. التحقّق الحيّ على staging (قراءة)

### ٣.١ الحقل موجود ولديه هندسة

```bash
curl -sS "${AUTH[@]}" "$BASE/api/v1/fields/$FIELD_ID" \
  | jq '{field_id, name, created_at, has_geometry: (.geometry != null)}'
curl -sS "${AUTH[@]}" "$BASE/api/v1/fields/$FIELD_ID" | jq '.geometry' > /tmp/field_geom.json
```

**المتوقَّع:** `has_geometry: true`. بلا هندسة تبقى أزرار المدد معطّلة (القسم ٤).

### ٣.٢ المؤشّر بالبكسل: TileJSON ثمّ بلاطة PNG

```bash
# TileJSON: مصدر البلاطات ومدى التكبير (حتّى 20) وتاريخ المشهد المحلول
curl -sS "${AUTH[@]}" "$BASE/api/raster/v1/fields/$FIELD_ID/tilejson?index=ndvi" \
  | jq '{available, resolved_date, minzoom, maxzoom, tiles}'
```

**المتوقَّع:** `available: true`، و`maxzoom: 20`، ورابط بلاطات `/v1/fields/{id}/tiles/{z}/{x}/{y}.png`.
إن عاد `available: false` فالحقل بلا COG محفوظ بعد: نفّذ ٣.٤ أوّلاً.

```bash
# بلاطة فوق مركز الحقل عند تكبير 17 (~1.2م/بكسل شاشة، أي أنّ بكسل Sentinel-2 ‏10م يظهر مربّعاً واضحاً)
read LON LAT < <(jq -r '[.coordinates[0][] ] | (map(.[0])|add/length|tostring) + " " + (map(.[1])|add/length|tostring)' /tmp/field_geom.json)
read Z X Y < <(python3 - "$LON" "$LAT" <<'PY'
import math, sys
lon, lat, z = float(sys.argv[1]), float(sys.argv[2]), 17
n = 2 ** z
x = int((lon + 180) / 360 * n)
y = int((1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n)
print(z, x, y)
PY
)
curl -sS "${AUTH[@]}" -o /tmp/ndvi_tile.png -w "HTTP %{http_code} · %{content_type} · %{size_download} بايت\n" \
  "$BASE/api/raster/v1/fields/$FIELD_ID/tiles/$Z/$X/$Y.png?index=ndvi"
python3 - <<'PY'
from PIL import Image
im = Image.open("/tmp/ndvi_tile.png").convert("RGBA")
px = list(im.getdata())
opaque = [p for p in px if p[3] > 0]
print("الأبعاد:", im.size, "· بكسلات مرئيّة:", len(opaque), "· ألوان مميّزة:", len(set(opaque)))
print("PASS: مؤشّر بكسليّ متباين" if len(set(opaque)) > 5 else "تحقّق: لون واحد/شفّافة (حقل متجانس أو بلا COG)")
PY
```

**المتوقَّع:** `HTTP 200 · image/png`، وأبعاد `(256, 256)`، وأكثر من 5 ألوان مميّزة داخل الحقل. التصيير على الخادم
بـ`Resampling.nearest` للمؤشّرات (`tile_render.py`)، فكلّ بكسل Sentinel-2 يبقى مربّعاً حادّاً لا مُنعَّماً، والبكسلات خارج
حدّ الحقل شفّافة.

### ٣.٣ نقطة قيمة البكسل `/pixel` (حالة معروفة)

```bash
curl -sS "${AUTH[@]}" -o /dev/null -w "HTTP %{http_code}\n" \
  "$BASE/api/raster/v1/fields/$FIELD_ID/pixel?lat=$LAT&lon=$LON&index=ndvi"
```

**المتوقَّع اليوم:** `403`. نقطة `/v1/fields/{id}/pixel` موجودة في raster-service (`routers/fields.py:1010`) لكنّها
**ليست** في قائمة مسموحات البوّابة (`compat_gateway.py:121`)، ولا تستدعيها الواجهة. فعرض قيمة البكسل بالنقر
على الخريطة **غير متاح** حاليّاً؛ اللون وحده يدلّ على القيمة. إتاحتها تحتاج إضافة المسار إلى القائمة وواجهة نقر.

### ٣.٤ الصور التاريخيّة: 3 أشهر قبل إنشاء الحقل (خطّة بلا كتابة)

```bash
jq -n --slurpfile g /tmp/field_geom.json '{
  preset: "custom", months: 3, dry_run: true,
  indices: ["truecolor","ndvi","ndmi","ndre","msavi","ndwi","ndsi"],
  max_cloud_pct: 50, limit_per_month: 8, apply_cloud_mask: true,
  clip_polygon_geojson: $g[0]
}' > /tmp/backfill_3m.json
curl -sS "${AUTH[@]}" -H "Content-Type: application/json" -X POST \
  --data @/tmp/backfill_3m.json "$BASE/api/v1/fields/$FIELD_ID/imagery/backfill" \
  | jq '{dry_run, preset, period, months_scanned, scenes_selected, jobs: (.jobs|length)}'
```

**المتوقَّع:** `dry_run: true`، و`period.months: 3`، و`period.from` قبل اليوم بنحو 93 يوماً — أي **قبل**
`created_at` في ٣.١ لحقلٍ أُنشئ حديثاً. `scenes_selected` > 0 إن وُجدت مشاهد بغيمٍ ≤ 50%.

**اختياريّ (يكتب: يجدول المعالجة فعلاً، مثل زرّ «3 شهر» في الواجهة):**

```bash
jq '.dry_run = false' /tmp/backfill_3m.json > /tmp/backfill_3m_run.json
RUN_ID=$(curl -sS "${AUTH[@]}" -H "Content-Type: application/json" -X POST \
  --data @/tmp/backfill_3m_run.json "$BASE/api/v1/fields/$FIELD_ID/imagery/backfill" | jq -r '.run_id // empty')
echo "run_id=$RUN_ID"
# استطلاع الحالة حتّى الاكتمال (كلّ 20 ثانية، 30 مرّة كحدّ)
for i in $(seq 1 30); do
  S=$(curl -sS "${AUTH[@]}" "$BASE/api/v1/fields/$FIELD_ID/imagery/backfill/$RUN_ID" \
      | jq -r '[.status, .items_persisted, .items_failed] | @tsv')
  echo "$(date -u +%H:%M:%S) $S"
  case "$S" in completed*|completed_with_errors*|failed*|cancelled*) break;; esac
  sleep 20
done
```

### ٣.٥ المحور الزمنيّ يتّسع للمدّة المختارة

```bash
curl -sS "${AUTH[@]}" \
  "$BASE/api/v1/fields/$FIELD_ID/available-dates?index=ndvi&limit=240&include_provider=true&months=3" \
  | jq '[(.dates // .items // .)[] | {date, has_cog}] | {count: length, oldest: (min_by(.date).date), newest: (max_by(.date).date), with_cog: (map(select(.has_cog))|length)}'
```

**المتوقَّع:** `oldest` قبل اليوم بنحو 3 أشهر. التواريخ بـ`has_cog: false` مشاهد من المزوّد لم تُعالَج بعد
(«ينتظر COG»)، وتصير `true` بعد اكتمال ٣.٤.

---

## ٤. التحقّق اليدويّ في المتصفّح (staging)

| # | الخطوة | المتوقَّع |
|---|---|---|
| 1 | افتح «شاشة الأقمار» (MapHub)، واختر الحقل. | يظهر الحقل بحدّه. |
| 2 | اختر مؤشّراً (NDVI). | تظهر طبقة ملوّنة داخل حدّ الحقل فقط. |
| 3 | كبّر حتّى 17–18. | مربّعات حادّة بحجم ~10م (بكسل Sentinel-2)، لا تدرّج مُنعَّم ولا لون واحد. |
| 4 | تحت الخريطة: «تجهيز 24 شهر» وبجانبه أزرار **3 شهر · 6 شهر · 12 شهر · 24 شهر** (`data-testid="imagery-backfill-month-options"`). | الأزرار ظاهرة ومفعّلة. تُعطَّل فقط أثناء التجهيز أو لحقلٍ بلا هندسة. |
| 5 | اضغط **3 شهر**. | رسالة «أُدرِجت تشغيلة 3 شهر في الطابور» ثمّ حالةٌ تتقدّم؛ وفي DevTools ⇒ Network طلب `POST …/imagery/backfill` بجسمٍ فيه `"months":3`. |
| 6 | بعد الاكتمال: الشريط الزمنيّ. | تواريخ تمتدّ ~3 أشهر للخلف، منها ما يسبق إنشاء الحقل؛ المصغّرات تظهر للمعالَج. |
| 7 | كرّر بـ6 ثمّ 12. | `months` في الطلب يطابق الزرّ، والمحور يتّسع. |
| 8 | افتح «لوحة المؤشّرات». | **لا** مُحدِّد «7 أيام/30 يوم/3 أشهر/سنة» (كان لا يغيّر شيئاً). زرّ التحديث والتصدير باقيان. |
| 9 | انقر على بكسل داخل الحقل. | لا تظهر قيمة رقميّة (حالة معروفة، ٣.٣). |

**إن فشل البند 4** (الأزرار غير ظاهرة): الشرط في `MapHub.tsx` أن يكون العرض ثنائيّ الأبعاد بلا مقارنة،
ومؤشّرٌ نشط مختار، وحقلٌ مختار. اختر مؤشّراً أوّلاً.

---

## ٥. خصائص التربة: النسخة المحلّيّة البديلة لـSoilGrids REST

واجهة SoilGrids REST معلّقة رسميّاً (ISRIC، 2026-01-27). `raster-service` يقرأ نسخةً محلّيّة عبر `SOILGRIDS_DIR`
بأسماء `{prop}_{depth}.tif` (`soil_render.py:179`). بعد إصلاح Int16 صار يقرأ ملفّات SoilGrids الأصليّة.

### ٥.١ اقتطاع نطاق اليمن (من جهازٍ بشبكة مفتوحة وGDAL ≥ 3.1)

```bash
OUT=./soilgrids_yemen_cog; BBOX="41.8 12.0 54.6 19.1"
BASE_SG="https://files.isric.org/soilgrids/latest/data"
read MINLON MINLAT MAXLON MAXLAT <<<"$BBOX"; mkdir -p "$OUT"
export GDAL_HTTP_TIMEOUT=120 GDAL_HTTP_MAX_RETRY=4 GDAL_DISABLE_READDIR_ON_OPEN=EMPTY_DIR
for p in phh2o clay sand silt soc cec nitrogen bdod wv0033 wv1500; do
  for d in 0-5cm 5-15cm 15-30cm 30-60cm 60-100cm 100-200cm; do
    [ -s "$OUT/${p}_${d}.tif" ] && continue
    gdal_translate -q -of COG -co COMPRESS=DEFLATE -co PREDICTOR=2 \
      -projwin_srs EPSG:4326 -projwin "$MINLON" "$MAXLAT" "$MAXLON" "$MINLAT" \
      "/vsicurl/${BASE_SG}/${p}/${p}_${d}_mean.vrt" "$OUT/${p}_${d}.tif" \
      && echo "تمّ ${p}_${d}" || echo "فشل/غير متاح ${p}_${d}"
  done
done
( cd "$OUT" && sha256sum *.tif > SHA256SUMS ) && ls "$OUT" | wc -l
```

**المتوقَّع:** حتّى 60 ملفّاً (10 خصائص × 6 أعماق) و`SHA256SUMS`. الإسقاط يبقى Homolosine الأصليّ؛ raster-service
يعيد الإسقاط عند القراءة. طبقتا `wv0033`/`wv1500` لميزان الريّ لاحقاً؛ raster-service يتجاهلهما اليوم.

### ٥.٢ التحقّق المحلّيّ من أنّ raster-service يقرأ الملفّات

```bash
SOILGRIDS_DIR="$PWD/soilgrids_yemen_cog" python3 - <<'PY'
import sys; sys.path.insert(0, "services/raster-service")
import soil_render as sr
print("configured:", sr.is_source_configured(), "· طبقات مقروءة:", sr.readable_layer_count() if hasattr(sr, "readable_layer_count") else "?")
r = sr.compute_field_soil_summary([43.30, 14.18, 43.36, 14.22], "0-5cm")   # وادي زبيد
print("computed:", r["computed"], "· source:", r["source"], "· texture:", r.get("texture_class"))
print({k: v["mean"] for k, v in r.get("properties", {}).items()})
PY
```

**المتوقَّع:** `computed: True` وثماني خصائص. على `main` قبل إصلاح Int16 كان الناتج `field-outside-source`.

### ٥.٣ النشر (قرار المالك — لا يُنفَّذ من هذا الدليل)

رفع المجلّد إلى وحدة تخزين لخدمة raster على Railway وضبط `SOILGRIDS_DIR` يغيّران Railway، وهذا للمالك وحده.

---

## ٦. حالة النشر على Railway (قراءة عبر GitHub فقط)

```bash
SHA=$(git rev-parse origin/main)
gh api "repos/kafaat/ai_platform_complete_v2.0.0_enhanced/commits/$SHA/statuses" --paginate \
  -q '.[] | select(.context|test("raster|frontend|migrate")) | "\(.context)\t\(.state)\t\(.description)"' | sort -u
```

**المتوقَّع:** `sahool-raster-service` و`sahool-frontend` بـ`success` بعد دمج الإصلاحين؛ و`sahool-migrate-main`
بـ«No deployment needed» (لا هجرة).

---

## ٧. جدول النتيجة (املأه وألصقه في الـPR أو سجلّ الدماغ)

```text
التاريخ (UTC):            ____
SHA على main:             ____
٢.١ Int16 raster:          PASS / FAIL
٢.٢ نافذة 3 أشهر:          PASS / FAIL
٢.٣ أزرار المدد (static):  PASS / FAIL
٣.٢ بلاطة بكسليّة:          PASS / FAIL  (ألوان مميّزة = __)
٣.٣ /pixel:                403 متوقَّع / غير ذلك = __
٣.٤ خطّة 3 أشهر:           period.from = ____ · scenes_selected = __
٣.٥ المحور الزمنيّ:         oldest = ____ · with_cog = __
٤   الواجهة (1–9):         ____
٥.٢ تربة محلّيّة:            computed = __ (إن نُفّذ ٥.١)
```

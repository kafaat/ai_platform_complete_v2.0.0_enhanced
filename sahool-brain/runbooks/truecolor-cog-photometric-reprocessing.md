# رَنبوك — إعادة معالجة انتقائيّة لأصول truecolor القديمة (وسم PHOTOMETRIC)

> **قابل للنسخ من الشاشة.** كتل الأوامر مُصمَّمة للصقّ في صدفة المُشغّل على البيئة الحيّة.
>
> **الخلفيّة الكوديّة (مدموجة):** `write_rgba_cog` صار يصرّح `photometric=RGB` (+`alpha=YES`
> للنطاق الرابع) **وقت الإنشاء** (`services/raster-service/cog_writer.py`). قبله كان الوسم
> الافتراضيّ MINISBLACK على القرص، فيحذّر GDAL عند القراءة:
> «Sum of Photometric type-related color channels and ExtraSamples doesn't match
> SamplesPerPixel» ويعيد تعريف نطاقات RGB كـExtraSamples.
>
> **صدق:** هذا التغيير الكوديّ يُصلح **الملفّات الجديدة فقط**. الأصول التي كُتبت قبله لا تتغيّر
> تلقائيّاً — تحتاج إعادة معالجة انتقائيّة. **لا إعادة كتابة شاملة (bulk) تلقائيّة** في هذا التغيير.

---

## 1) اكتشاف الأصول القديمة المتأثّرة (للقراءة فقط)

الأصول المتأثّرة = COGs من نوع truecolor كُتبت قبل نشر الإصلاح. تحقّق من الوسم فعليّاً
(`PHOTOMETRIC=MINISBLACK` بدل `RGB`) بدل الاعتماد على التاريخ فقط:

```bash
# داخل حاويّة raster-service (rasterio/gdal متوفّران):
docker exec -i v22-sahool-raster-service-1 python - <<'PY'
import glob, rasterio
from rasterio.enums import ColorInterp
bad=[]
for p in glob.glob("/data/rasters/**/*truecolor*.tif", recursive=True):
    try:
        with rasterio.open(p) as s:
            # RGBA سليم: 4 نطاقات وأوّلها أحمر. الخلل: أوّلها gray (MINISBLACK).
            if s.count>=3 and s.colorinterp[0]!=ColorInterp.red:
                bad.append(p)
    except Exception as e:
        bad.append(f"{p} (open-error: {e})")
print(f"affected={len(bad)}")
print("\n".join(map(str, bad[:50])))
PY
```

> بديل سريع لقاعدة البيانات (قائمة الأصول المرشَّحة، ثمّ افحص وسمها بالأمر أعلاه):
> ```bash
> docker exec -i v22-sahool-postgres-1 psql -U sahool_user -d sahool -c \
>   "SELECT field_id, acquisition_date, cog_uri FROM raster_assets
>      WHERE index_name='truecolor' AND created_at < '<تاريخ-نشر-الإصلاح>' ORDER BY created_at;"
> ```

## 2) إعادة المعالجة الانتقائيّة (idempotent)

أعِد المعالجة عبر مسار المنصّة العاديّ (نفس أنبوب backfill/process الذي يكتب الأصل)، حقلاً
حقلاً/تاريخاً تاريخاً — **لا إدراج يدويّ ولا إعادة كتابة مباشرة للملفّ**:

```bash
# مثال: إعادة معالجة تاريخ truecolor واحد لحقل (JWT-محميّ عبر البوّابة):
curl -sS -X POST "$PLATFORM/api/raster/v1/fields/<field_id>/process" \
  -H "Authorization: Bearer $SERVICE_JWT" \
  -H 'Content-Type: application/json' \
  -d '{"index":"truecolor","date":"<YYYY-MM-DD>","run_kind":"single_scene"}'
```

- **idempotent:** المعالجة تكتب أصلاً بنفس مفتاح الهُويّة (`tenant_id, field_id, product_date,
  index_type`) عبر `ON CONFLICT … DO UPDATE`؛ تكرار الأمر يُحدِّث لا يُكرّر. الملفّ الناتج الجديد
  يحمل `PHOTOMETRIC=RGB` (تحقّق بأمر القسم 1).
- **بعد النجاح:** أبطِل كاش البلاطات للحقل (عامل `raster_cache_invalidations` أو حذف
  `UPLOAD_DIR/tile_cache/<tenant>/<field>/…`) كي تُخدَم البلاطات من الأصل المُصحَّح.

## 3) الأولويّة (لا bulk تلقائيّ)

1. **عند الطلب** — أيّ حقل يُبلَّغ فيه عن تحذير/عرض لونيّ خاطئ.
2. **الحقول النشطة** — الحقول ذات المشاهدة الحيّة/الخطّ الزمنيّ المفتوح.
3. **الباقي** — يُترَك حتّى الطلب؛ الملفّات القديمة تعمل (المُصيِّر الداخليّ يقرأ النطاقات
   بالفهرس صراحةً)، والتحذير سجلّيّ لا كسر خدمة. **لا تشغّل مسحاً شاملاً يعيد كتابة كلّ الأصول.**

## 4) تحقّق بعد المعالجة

```bash
# لا مزيد من تحذير PHOTOMETRIC في سجلّ raster للحقل المُعاد:
docker logs --since 10m v22-sahool-raster-service-1 2>&1 | grep -c "SamplesPerPixel"   # ⇒ 0 للأصول المُصحَّحة
# والأصل الجديد يقرأ RGBA سليماً (القسم 1 يُرجِعه غير متأثّر).
```

**المصادر:** الإصلاح الكوديّ `services/raster-service/cog_writer.py` (`write_rgba_cog` → `photometric=RGB`,
`alpha=YES`) + اختباره `services/raster-service/test_rgba_cog_photometric.py` · تقرير تشخيص تصيير truecolor.

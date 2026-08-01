# نشر خادم استدلال SAM2 (GPU/CUDA) — تفعيل التقطيع التلقائيّ/الهجين

> **سياسة الصدق:** هذا الدليل لتشغيل خادم استدلال **حقيقيّ** على عتاد GPU لديك
> (مثل RTX 4090). الكود مكتوب وصحيح لكنّه **لم يُختبَر على عتاد** في بيئة التطوير
> (لا GPU/CUDA ولا أوزان). يجب التحقّق من: تحميل النموذج، جلب الصورة، وجودة
> القناع→المضلّع، على عتادك. الخدمة **لا تُلفّق** أقنعة أو هندسة: غياب النموذج أو
> تعذّر جلب الصورة يُرجِع **503/422 صادقاً**، لا مضلّعاً اصطناعيّاً.

## ما الذي يفعله هذا

`services/field-segmentation` جاهزة للنموذج: مساراها `auto`/`hybrid` يرسلان طلب
HTTP إلى `SEGMENTATION_INFERENCE_URL` ويتحقّقان من الهندسة العائدة عبر
`normalize_polygon`. بدون خادم استدلال مُهيّأ تردّ **503 صادقاً**. هذا الدليل ينشر
خادم الاستدلال (`services/sam2-inference`) خلف **profile=gpu** فقط — الحزمة
الافتراضيّة (CPU فقط) لا تتطلّب GPU ولا تتأثّر.

العقد بين الخدمتين (مطابق بلا تغيير كود):

- **الطلب** (يرسله `field-segmentation._post_inference`، ترويسة `X-Agent-Token`):
  ```json
  {
    "mode": "auto" | "hybrid",
    "field_bbox": [min_lon, min_lat, max_lon, max_lat],
    "image_ref": "<COG URL أو null>",
    "user_polygon": [[lon, lat], ...]
  }
  ```
- **الاستجابة** (يتحقّق منها `field-segmentation.normalize_polygon`):
  ```json
  { "geometry": { "type": "Polygon", "coordinates": [[[lon, lat], ...]] } }
  ```

## المتطلّبات المسبقة

1. **GPU + NVIDIA Container Toolkit** على المضيف (تمرير GPU للحاوية):
   ```bash
   # تثبيت toolkit (Ubuntu/Debian) — راجع توثيق NVIDIA الرسميّ للإصدار الأحدث.
   sudo apt-get install -y nvidia-container-toolkit
   sudo nvidia-ctk runtime configure --runtime=docker
   sudo systemctl restart docker
   # تحقّق:
   docker run --rm --gpus all nvidia/cuda:12.1.1-base-ubuntu22.04 nvidia-smi
   ```
2. **Docker Compose v2** (لدعم `deploy.resources.reservations.devices`).

## الخطوة ١ — تنزيل أوزان SAM2

نزّل checkpoint من مستودع Meta الرسميّ (facebookresearch/sam2). الافتراض في الكود
هو **hiera large**:

- صفحة الأوزان: <https://github.com/facebookresearch/sam2#model-description>
- الرابط المباشر (large):
  <https://dl.fbaipublicfiles.com/segment_anything_2/072824/sam2_hiera_large.pt>

```bash
# نزّل محلّيّاً
curl -L -o sam2_hiera_large.pt \
  https://dl.fbaipublicfiles.com/segment_anything_2/072824/sam2_hiera_large.pt
```

> إن استخدمت checkpoint بحجم مختلف (tiny/small/base_plus) فعدّل `SAM2_MODEL_CFG`
> ليطابقه (مثل `sam2_hiera_t.yaml`)، وعدّل `SAM2_CHECKPOINT` لاسم الملفّ.

## الخطوة ٢ — وضع الأوزان في volume `sam2-models`

الحاوية تركّب `sam2-models:/models:ro`. انسخ الأوزان إلى الـvolume:

```bash
# أنشئ الـvolume واملأه (حاوية مؤقّتة تنسخ من المضيف):
docker volume create ai_platform_complete_v200_enhanced_sam2-models 2>/dev/null || \
  docker volume create sam2-models
docker run --rm -v sam2-models:/models -v "$PWD":/src alpine \
  cp /src/sam2_hiera_large.pt /models/sam2_hiera_large.pt
```

> اسم الـvolume الفعليّ يحمل بادئة المشروع (مجلّد compose). تحقّق بـ
> `docker volume ls | grep sam2-models` بعد أوّل `up`، أو استخدم `docker compose`
> لإنشائه ثمّ انسخ إليه.

## الخطوة ٣ — اضبط البيئة (`.env`)

```dotenv
# توكن خدمة-لخدمة (نفس قيمة field-segmentation).
SAHOOL_AGENT_TOKEN=<توكن قويّ عشوائيّ>

# تفعيل المسار من field-segmentation نحو خادم SAM2.
SEGMENTATION_BACKEND=sam2
SEGMENTATION_INFERENCE_URL=http://sahool-sam2-inference:8080/predict

# (اختياريّ) تجاوز مسار/إعداد الأوزان لو غيّرت الحجم.
SAM2_CHECKPOINT=/models/sam2_hiera_large.pt
SAM2_MODEL_CFG=sam2_hiera_l.yaml
```

> **مهمّ:** `SEGMENTATION_BACKEND`/`SEGMENTATION_INFERENCE_URL` لا تؤثّران إلّا حين
> ترفع profile=gpu (خادم SAM2 قيد التشغيل). بدونه `field-segmentation` تردّ 503
> صادقاً كالمعتاد — لا انكسار في الحزمة الافتراضيّة.

## الخطوة ٤ — البناء والتشغيل (profile=gpu)

```bash
# v9 (المكدّس الكامل) — يرفع field-segmentation + خادم SAM2:
docker compose -f docker-compose.v9.yml --profile gpu up -d \
  sahool-sam2-inference sahool-field-segmentation

# أو fixed:
docker compose -f docker-compose.fixed.yml --profile gpu up -d \
  sahool-sam2-inference
```

تحقّق من تحميل النموذج:

```bash
# داخل الشبكة الداخليّة (أو عبر exec):
docker exec -it sahool-v9-sam2-inference \
  python -c "import urllib.request,json; print(urllib.request.urlopen('http://localhost:8080/readyz').read().decode())"
# المتوقّع بعد نجاح التحميل: {"status":"ready","model_loaded":true,"load_error":null}
# لو model_loaded=false، راجع load_error (لا CUDA؟ أوزان مفقودة؟).
```

## الخطوة ٥ — التحقّق عبر مسار المنصّة

استدعِ `POST /api/segmentation` (عبر البوّابة، تحقن البوّابة `X-Agent-Token`) أو
استدعِ `field-segmentation` مباشرة بمسار `/v1/segment`:

```bash
# auto: تقطيع كامل من صورة الـbbox.
curl -s -X POST http://sahool-field-segmentation:8000/v1/segment \
  -H "X-Agent-Token: $SAHOOL_AGENT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "mode": "auto",
    "field_bbox": [44.20, 15.30, 44.22, 15.32],
    "image_ref": null
  }'

# hybrid: مُوجَّه ببادرة المستخدم (مركز/مربّع user_polygon).
curl -s -X POST http://sahool-field-segmentation:8000/v1/segment \
  -H "X-Agent-Token: $SAHOOL_AGENT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "mode": "hybrid",
    "field_bbox": [44.20, 15.30, 44.22, 15.32],
    "user_polygon": [[44.205,15.305],[44.215,15.305],[44.215,15.315],[44.205,15.315]]
  }'
```

النجاح يردّ:
```json
{ "mode": "auto", "geometry": { "type": "Polygon", "coordinates": [[...]] }, "source": "sam2" }
```

## مصدر الصورة

- إن مرّرت `image_ref` رابط COG (http/https/s3/مسار محلّيّ) يقرؤه الخادم عبر
  `/vsicurl/` (rasterio/GDAL).
- إن كان `image_ref=null` (أو غير قابل للقراءة) يستعلم الخادم **Element84 STAC**
  (`sentinel-2-l2a`) عن أحدث صورة صافية للـ`field_bbox` ويستخدم أصل `visual` (RGB).
- تعذّر إيجاد/قراءة صورة ⇒ **503 صادق** (`no_imagery_for_bbox` /
  `image_read_failed`)، لا اختراع.

## مصفوفة الأخطاء الصادقة (لا تلفيق)

| الحالة | الردّ |
|---|---|
| النموذج غير محمّل (لا CUDA / أوزان مفقودة) | `503 model_not_loaded` (+ `load_error`) |
| لا توكن صالح | `401` |
| لا `image_ref` ولا `field_bbox` | `422 no_image_and_no_bbox` |
| لا صورة Sentinel صافية للنطاق | `503 no_imagery_for_bbox` |
| تعذّرت قراءة COG (شبكة/مصدر) | `503 image_read_failed` |
| SAM2 لم يُنتج قناعاً / قناع فارغ | `500 no_mask` / `500 empty_mask` |
| تعذّر تحويل القناع لمضلّع صالح | `500 no_polygon` / `degenerate_polygon` |

## ملاحظات الجودة (يجب التحقّق على عتادك)

- **جودة التقطيع تعتمد على النموذج + الصورة:** الغيوم، الدقّة (Sentinel-2 = 10م)،
  وتوقيت الصورة كلّها تؤثّر. SAM2 عامّ (segment-anything) لا مُدرَّب على الحقول
  تحديداً — البادرة (نقطة مركز/مربّع user_polygon) توجّهه، لكن دقّقها على بياناتك.
- **بادرة auto** نقطة مركز الـbbox الحاليّة؛ قد تحتاج لشبكة نقاط أو بادرة أذكى
  لحقول غير مركزيّة — وسّعها في `_build_prompt` بعد التحقّق.
- **decimation:** نحدّ أبعاد القراءة بـ`MAX_IMAGE_DIM` (افتراضاً 1024px) لحماية
  ذاكرة GPU. ارفعها لو احتجت تفاصيل أدقّ وذاكرتك تكفي.
- **pip-audit:** شغّله على صورة الـGPU النهائيّة لديك بعد البناء
  (`pip-audit` على `services/sam2-inference/requirements.txt` + ما يثبّته
  Dockerfile من torch/sam2). لا يمكن تثبيت torch بنسخة CUDA في بيئة بلا GPU.

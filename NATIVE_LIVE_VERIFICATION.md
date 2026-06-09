# تحقّق حيّ أصيل (Native) — بلا صور Docker

سياسة شبكة البيئة تحجب سحب صور Docker (registry 403)، لكن أدوات البنية التحتيّة
ثنائيّات على GitHub releases → شُغِّلت محلّيّاً وتُحقّق النظام فعليّاً.

## الستاك الحيّ المحلّي
| المكوّن | المصدر | الحالة |
|---------|--------|--------|
| Postgres 16 + PostGIS | محلّي | ✓ (كل الترحيلات 20/20) |
| Redis | محلّي | ✓ |
| **NATS 2.10 + JetStream** | GitHub release | ✓ (نشر/استقبال + stream حقيقي) |
| **Qdrant 1.12** | GitHub release | ✓ (collection+upsert+بحث) |
| **moto S3** (بديل MinIO) | PyPI | ✓ (رفع COG→s3://→قراءة /vsis3) |

## خدمات عبر uvicorn على socket حقيقي (HTTP فعلي)
- **raster-service** :8099 — `/process`→`/indicator-grid`(real_data=True, NDVI=0.556)
  →`/tilejson`→`/tiles/{z}/{x}/{y}.png` (PNG مُصيَّر 740B). خطّ الصور كامل + PG حيّ.
- **auth-service** :8120 — register→login→/me→**/refresh** (توكن Redis حيّ) + رفض كلمة خاطئة.
- **market-mcp** :8094 — حارس `require_scope("market:read")`: بلا توكن→401، خاطئ→403، صحيح→200.
- **guardrails** :8097 — `/validate` يفرض توكن الخدمة (401).

## أخطاء حقيقيّة كشفها التحقّق الحيّ وأُصلحت
1. **object_store S3**: كان يمرّر endpoint بلا scheme لـboto3 ⇒ كل رفع يسقط لـfile://.
   أُصلح (`_endpoint_url()`) ومُثبَت ضدّ moto. (commit 95109f6)
2. **عزل اختبارات mcp**: تلوّث sys.path/modules كسر اختبارات لاحقة. أُصلح. (92cf5e4)

## ملاحظة منهجيّة
تعثّر تشغيل uvicorn سابقاً لم يكن عيب خدمة، بل `pkill -f uvicorn` يطابق سطر أمر
الشِل نفسه فيقتله. الإيقاف الصحيح: بالـPID/المنفذ.

## ما يتطلّب بيئة بشبكة مفتوحة
بناء/تشغيل صور Docker الفعليّة + جلب صور أقمار حيّة (Element84/Sentinel Hub) — محجوبة هنا.

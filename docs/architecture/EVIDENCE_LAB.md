# SAHOOL Evidence Lab

## الهدف

تغلق هذه البيئة أكبر قدر ممكن من فجوات الاختبار من دون الاتصال بالإنتاج، ومن دون
تحويل المحاكاة إلى دليل حي. وهي لا تضيف خدمة تشغيلية جديدة ولا تغيّر
`docker-compose.v9.yml`.

تستخدم البيئة تبعيات حقيقية قصيرة العمر:

- PostgreSQL 16 + PostGIS لتطبيق الهجرات وإعادة تطبيقها واختبارات RLS والكاتب الواحد.
- Redis لاختبارات الكاش والحالة وidempotency.
- NATS JetStream لاختبارات outbox والتسليم وإعادة التشغيل.
- MinIO لاختبارات التخزين المتوافق مع S3.
- WireMock لإعادة تشغيل عقود Open-Meteo وSTAC وفشل المزود بصورة حتمية.

## مستويات الدليل

| المستوى | ما يثبته | الحد الأعلى للادعاء |
|---|---|---|
| Offline | سلامة المصدر والحراس والعقود | `source_verified` |
| Ephemeral | تكامل تبعيات حقيقية مؤقتة | `ephemeral_dependency_verified` |
| Connected sandbox | تكامل مزود غير إنتاجي معتمد | `sandbox_connected_verified` |
| Live | ingress والطرح والمزودون والأجهزة الحقيقية | يبقى خارج المختبر |

لا يستطيع المشغل إنتاج `production_certified`، ويرفض العمل عندما تكون
`SAHOOL_ENV=production` أو `staging`.

## التشغيل

تحقق سريع بلا Docker:

```bash
python scripts/certification/evidence_lab.py --validate
python scripts/certification/evidence_lab.py --mode offline
```

تشغيل التبعيات المؤقتة والتحقق منها ثم حذفها:

```bash
python scripts/certification/evidence_lab.py --mode ephemeral --provision
```

للتشخيص المحلي فقط يمكن إبقاء الحاويات مؤقتاً:

```bash
python scripts/certification/evidence_lab.py --mode ephemeral --provision --keep
docker compose -f docker-compose.evidence-lab.yml -p sahool-evidence-lab down --volumes
```

التقرير الناتج موجود تحت `certification/evidence-lab/<run-id>/`. هذا المجلد مستبعد
من بصمة حزمة المصدر لأن محتواه دليل تشغيل متغير، بينما ملفات تصميم المختبر نفسها
تبقى داخل البصمة.

## توصيل الخدمات بالمختبر

عند تشغيل خدمة الطقس محلياً:

```text
OPEN_METEO_FORECAST_URL=http://evidence-wiremock:8080/open-meteo/v1/forecast
OPEN_METEO_ARCHIVE_URL=http://evidence-wiremock:8080/open-meteo/v1/archive
```

وعند تشغيل raster-service بوضع Element84:

```text
HISTORICAL_SEARCH_PROVIDER=element84
EARTH_SEARCH_URL=http://evidence-wiremock:8080/earth-search/v1
```

ملفات WireMock ثابتة ومؤرخة، ولذلك يمكن إعادة الخطأ نفسه أو الاستجابة نفسها في CI.
يشمل المختبر استجابة نجاح للطقس وSTAC، وحالة فشل مزود حتمية عبر
`X-Evidence-Fault: upstream-timeout`.
يجب إضافة fixture جديدة عند تغيّر عقد المزود، وليس تعديل النتيجة القديمة بصمت.

## ما لا يمكن تجاوزه

يبقى الدليل الحي ضرورياً لـ:

- DNS العام وسلسلة TLS والـcookies عند الحافة.
- صلاحيات قاعدة الهدف والتحويل والرجوع الحقيقي.
- حصص المزودين وتوفرهم وتسليم SMS/WhatsApp/Email الفعلي.
- معايرة النماذج ودقتها على بيانات ممثلة.
- سلامة المعدات والـtelemetry والـkill switch في الحقل.
- المراقبة والتنبيهات والنسخ الاحتياطية المجدولة في الهدف.
- canary والـpost-deploy smoke والـrollback.

## أساس الممارسة

التصميم يتبع نمط الحاويات قصيرة العمر للتبعيات الحقيقية، ومحاكاة الخدمات الخارجية
القابلة لإعادة التشغيل، واختبارات عقود المستهلك التي تمر عبر العميل الحقيقي، ثم
تقرير أدلة مرتبط ببصمة المصدر. صيغة `slsa-inspired-local-v1` في التقرير وصف محلي
فقط وليست SLSA attestation موقعة.

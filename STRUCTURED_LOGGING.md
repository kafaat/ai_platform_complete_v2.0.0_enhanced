# تسجيل منظّم موحّد (JSON) — النتيجة

بنيتُ مكتبة logging موحّدة عبر الخدمات، تكمّل حملة exception hygiene في الرؤية.

## المشكلتان اللتان حلّهما
### ١. عدم الاتّساق
كانت كلّ خدمة تسجّل بطريقتها: بعضها basicConfig نصّي، بعضها getLogger بلا
تهيئة، بعضها (weather/supervisor) بلا تسجيل أصلاً.

### ٢. الهشاشة (الأخطر)
التنسيق القديم format-string كان **يُنتج JSON مكسوراً** حين تحوي الرسالة
اقتباساً أو سطراً جديداً:
```
الرسالة: حقل "A" فشل
القديم: {"msg":"حقل "A" فشل"}  ← JSON غير صالح! (يكسر أيّ log aggregator)
```

## الحلّ: shared/logging_config.py
`JSONFormatter` يستخدم `json.dumps` (يهرّب كلّ شيء صحيحاً) + حقول موحّدة:
```json
{"ts":"...","level":"INFO","service":"auth","logger":"auth",
 "message":"حقل \"A\" فشل","field_id":"F1","exception":"Traceback..."}
```
مزايا:
- **JSON صالح دائماً** (اقتباسات/أسطر/عربي مُهرَّبة صحيحاً)
- **العربي مقروء** (ensure_ascii=False، لا \uXXXX)
- **extra fields**: `logger.info("m", extra={"field_id":"F1"})` → حقل في JSON
- **الاستثناء كامل**: traceback في اللوق بدل ابتلاعه (يكمّل exception hygiene)
- **LOG_LEVEL** من البيئة (تحكّم بلا تغيير كود)

## الاستخدام
```python
from shared.logging_config import setup_logging
logger = setup_logging("auth")
logger.info("بدء الخدمة", extra={"port": 8089, "tenant_id": "T1"})
```

## الخدمات الموصولة (10)
auth · soil · vegetation · supervisor · odoo-bridge · local-ai-rag · tts ·
raster · video · actuator — كلّها **مع fallback آمن**: لو غاب shared (بناء
جزئي) → ترجع للـbasicConfig بدل الانهيار.

## تغييرات البنية
- 6 Dockerfiles جديدة تنسخ `shared/` (odoo-bridge/local-ai-rag/tts/raster/
  video/actuator) — كانت لا تنسخه.
- الخدمات السبع الأخرى كانت تنسخ shared أصلاً.

## التحقّق
- 622/622 roadmap (+6) · 0 خطأ ترجمة
- JSONFormatter مُختبَر: اقتباسات + عربي + أسطر + extra + استثناء = JSON صالح
- circuit breaker 8/8 · router 14/14 (لا تراجع)

## ملاحظة صدق
- المكتبة **مُختبَرة فعليّاً** (شغّلتُ setup_logging والتقطتُ المخرج → JSON صالح).
- **fallback مقصود**: لو لم يُنسَخ shared في بناء معيّن، الخدمة تعمل بالتنسيق
  القديم بدل الانهيار — لا أكسر ما يعمل.
- weather-service تُرك بلا تسجيل (stub رفيع صادق، لا منطق يستحقّ logging).
- **لم أختبر تجميع اللوق الحيّ** (Loki/ELK) — يحتاج بنية على جهازك. لكنّ
  الناتج JSON صالح قياسيّ يقبله أيّ aggregator.

# ترحيل RS256 — إنهاء shared trust domain (مراجعة 8 #5)

## المشكلة
8 خدمات تستخدم HS256 بنفس JWT_SECRET → اختراق خدمة = تزوير tokens للباقي.

## الحلّ (RS256 غير متماثل + fallback آمن)
- **auth** (المُصدِر الوحيد): يوقّع بـJWT_PRIVATE_KEY (سرّي، عنده وحده)
- **7 متحقّقين**: يتحقّقون بـJWT_PUBLIC_KEY (آمن للتوزيع)
- خدمة مخترقة تملك المفتاح العامّ فقط → **لا تستطيع تزوير tokens**

## الترحيل الآمن (بلا flag-day)
كلّ خدمة: لو JWT_PUBLIC_KEY مضبوط → RS256، وإلّا → HS256 (JWT_SECRET).
فالنشر تدريجي: تضبط المفاتيح متى شئت؛ حتّى ذلك يعمل HS256 كما هو.

## الملفّات
- auth/main.py: JWT_PRIVATE_KEY/PUBLIC_KEY + SIGNING/VERIFY key + guard
- 7 متحقّقين: اختيار public key مع fallback (supervisor/guardrails/actuator/
  odoo/rag/tts/video)
- scripts_v9/generate_jwt_keys.sh: توليد زوج RS256

## التفعيل (على جهازك)
```
bash scripts_v9/generate_jwt_keys.sh ./jwt_keys
# في .env لـauth فقط:
JWT_PRIVATE_KEY="$(cat jwt_keys/jwt_private.pem)"
JWT_PUBLIC_KEY="$(cat jwt_keys/jwt_public.pem)"
# في .env لكلّ الخدمات الأخرى:
JWT_PUBLIC_KEY="$(cat jwt_keys/jwt_public.pem)"
```

## التحقّق
- 365/365 · 8 خدمات تُترجم · كلّ المتحقّقين يدعمون RS256

## ⚠️ ملاحظات صدق
- الكود مُتحقَّق منه بنيويّاً ومنطقيّاً (اختيار المفتاح صحيح). **لم أختبره
  بمفاتيح RSA حقيقيّة + توكن حيّ** (لا jwt/cryptography في البيئة). اختبر
  دورة كاملة (إصدار→تحقّق) بعد توليد المفاتيح قبل الإنتاج.
- ما زال fallback لـHS256 قائماً عمداً (ترحيل آمن). لإغلاق shared trust
  domain **فعليّاً**، يجب ضبط مفاتيح RS256 ثمّ (اختياريّاً) إزالة fallback.
- المفتاح الخاصّ سرّي مطلق — auth فقط، لا git، تدوير دوري.
- per-service audience (scoped tokens) لم يُنفّذ — تحسين إضافي (كلّ خدمة
  تقبل aud خاصّاً بها بدل "sahool" العامّ). قرار لاحق إن أردت عزلاً أدقّ.

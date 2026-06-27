# SAHOOL — Web/Mobile Smart Test Workarounds Report

## الهدف
تنفيذ حلول ذكية/التفافية لاختبارات الويب وتطبيق الهاتف داخل بيئة محجوبة جزئياً:
- لا يوجد Flutter/Dart SDK.
- Playwright browser download غير ممكن بسبب DNS.
- Playwright runner الكامل يتعثر مع WebGL/MapLibre داخل Chromium الحاوية.
- `npm test` الجماعي يمكن أن يعلق بسبب teardown/resource leak رغم نجاح الملفات منفردة.

## الإصلاحات التي تم تطبيقها

### 1) جعل الويب Offline/CI-safe
تم تعديل `frontend/index.html` لإزالة الاعتماد المباشر على:
- Google Fonts CDN.
- unpkg Leaflet CSS CDN.

السبب: هذه الروابط تفشل في بيئات CI/حاويات بلا DNS خارجي وتسبب ضوضاء/تعطيل في E2E. Leaflet CSS موجود أصلاً عبر `src/lib/leafletSetup.ts` ويُحزّم محلياً.

### 2) Runner ذكي لاختبارات الويب
تمت إضافة:
- `frontend/scripts/run-web-tests-smart.mjs`
- script في `frontend/package.json`: `npm run test:smart`

وظيفته:
- `typecheck`.
- تشغيل Vitest ملفاً ملفاً مع timeout لكل ملف، لتجنب تعليق التشغيل الجماعي.
- `build`.
- smoke E2E عبر Chromium النظام.
- حفظ النتائج في `frontend/test-results-smart/`.

### 3) Smoke E2E بديل لا يعتمد على WebGL الكامل
تمت إضافة:
- `frontend/scripts/playwright-smoke-smart.mjs`
- script في `frontend/package.json`: `npm run e2e:smoke`

وظيفته:
- استخدام `/usr/bin/chromium` أو `PW_CHROMIUM_PATH`.
- تشغيل Vite preview على `127.0.0.1` بدلاً من `localhost`.
- استخدام `waitUntil: commit` بدل `domcontentloaded` لتفادي التعثر عند lazy chunks/WebGL.
- التحقق من boot/auth screen/root/title/no real request failures.

### 4) Runner ذكي للموبايل عند غياب Flutter
تمت إضافة:
- `mobile/sahool_app/scripts/run-mobile-tests-smart.sh`

السلوك:
- إذا كان Flutter موجوداً: يشغل `flutter pub get`, `flutter analyze`, `flutter test`.
- إذا لم يكن Flutter/Dart موجوداً: يشغل static guards محلية:
  - وجود الملفات الأساسية.
  - تحقق pubspec.
  - وجود test files.
  - فحص مؤشرات خطرة مثل `print()` و plain `http://`.

## نتائج التشغيل داخل هذه البيئة

### Web
- `npm run typecheck`: PASS
- `npm run build`: PASS
- `node scripts/playwright-smoke-smart.mjs`: PASS

Smoke E2E output:
```json
{
  "ok": true,
  "status": 200,
  "title": "سهول — ذكاء زراعي",
  "rootExists": true,
  "hasLogin": true,
  "realErrors": [],
  "realFailures": [],
  "sampleText": "سهول\n\nمنصة الزراعة الذكية اليمنية\n\nالبريد الإلكتروني\nكلمة المرور\nتسجيل الدخول\nنسيت كلمة المرور؟\nأو\nدخول تجريبي (بيانات افتراضية)\n\nليس لديك حساب؟ إنشاء حساب جديد\n\nSAHOOL v8.0 · 47/47 اختبار ✅"
}

```

### Mobile
- Flutter/Dart: غير متاحين في البيئة.
- static mobile guard: PASS مع ملاحظة medium واحدة عن plain HTTP dev URL.

Mobile static output:
```json
WARN: Flutter/Dart SDK not available; running offline static guards only.
{
  "sdk_mode": "static-only",
  "tests_found": [
    "test/auth_service_test.dart",
    "test/ids_test.dart",
    "test/jwt_test.dart",
    "test/resilience_test.dart"
  ],
  "issues": [
    {
      "severity": "medium",
      "file": "lib/main.dart",
      "issue": "plain http URL found in app code"
    }
  ],
  "ok": true
}

```

## ما لم يتم اعتباره إصلاحاً كودياً مباشراً
- لم أُغيّر منطق MapLibre/WebGL نفسه لأن المشكلة بيئية في Chromium/WebGL داخل الحاوية.
- لم أُثبت Flutter لأن الإنترنت/SDK غير متاحين في البيئة.
- لم أُسقط اختبارات WebGL الأصلية؛ أبقيتها كحاجز حقيقي عند توفر بيئة browser/GPU مناسبة، وأضفت مسار smoke بديل للبيئات المحجوبة.

## أوامر الاستخدام

### Web
```bash
cd frontend
npm run test:smart
npm run e2e:smoke
```

### Mobile
```bash
cd mobile/sahool_app
./scripts/run-mobile-tests-smart.sh
```

## الخلاصة
تم تحويل الفشل البيئي إلى مسارين:
1. مسار كامل عند توفر الأدوات: Playwright/WebGL + Flutter.
2. مسار ذكي داخل البيئات المحجوبة: typecheck/build/Vitest-individual/Chromium smoke/mobile static guards.

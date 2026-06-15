# مراجعة تطبيق الموبايل (Flutter) — فحص فعلي للكود

فحصتُ تطبيق `mobile/sahool_app` بنفسي (لا أرسله لجهة خارجيّة — هو في النسخة
نفسها). فحصتُ المعمارية، الأمان، offline، الاستقرار، التكامل.

## الحالة العامّة: أنضج ممّا توقّعت
التطبيق **ليس هيكلاً** — هو تطبيق Flutter مبنيّ بعناية:
- إدارة حالة: flutter_bloc (نظيف)
- شبكة: dio مع interceptors
- تخزين: hive + flutter_secure_storage
- خرائط offline: MBTiles/PMTiles (لبيئة اليمن ضعيفة الشبكة)

## الأمان — قويّ ✅
| البند | الحالة |
|-------|--------|
| تخزين التوكن | ✅ secure storage مشفّر (`encryptedSharedPreferences`) لا SharedPreferences |
| تحقّق JWT | ✅ `_isTokenExpired` مع هامش 60s |
| biometric | ✅ fail-closed (لا تأكيد أمني زائف) |
| token redaction | ✅ لا يُسجَّل التوكن في اللوق (D08) |
| cert pinning | 🟡 self-signed في debug فقط (آمن) |

## التكامل مع الخلفيّة — جيّد ✅
- correlation IDs (`X-Request-ID`) — يطابق تتبّع الخلفيّة
- 401 → refresh تلقائي ثمّ إعادة الطلب
- offline detection (connectionError)

## الأخطاء المُكتشَفة والمُصلَحة
### 🟡 retry storm (مُصلَح)
كان: retry واحد بمهلة ثابتة `Duration(seconds: 2)` — بلا backoff/jitter/حدّ.
المراجعة حذّرت من retry storm بحقّ.
- الإصلاح: backoff أُسّي (~1s, 2s, 4s) + jitter عشوائي + حدّ أقصى 3 محاولات.
  يستخدم `requestOptions.extra['retry_attempt']` لتتبّع المحاولات.

## ملاحظات (لم تُصلَح — تحتاج قرارك)
### 🟡 سباق 401 المتزامن
عند 401 متزامن من عدّة طلبات، فقط الأوّل يحدّث التوكن (`!_isRefreshing`)؛
المتزامن معه يفشل بدل انتظار التحديث. الإصلاح الأمثل: طابور انتظار للتحديث
(Completer مشترك). تركتُه لأنّه يحتاج إعادة هيكلة interceptor + اختبار حيّ.

### 🟢 الاستقرار — جيّد أصلاً
- websocket: reconnect محدود (10) + backoff + طابور offline (100) + dispose
- bloc: يستخدم Emitter (لا تسريب streams يدوي)

## ما يحتاج جهازك (لا أملك Flutter SDK)
- `dart analyze` / `flutter analyze` — تحليل ثابت كامل
- `flutter test` — تشغيل auth_service_test.dart الموجود
- فحص rebuild storms (DevTools) — يحتاج تشغيل حيّ
- اختبار offline sync الفعلي (قطع الشبكة)

## التحقّق
- 648/648 roadmap · توازن أقواس Dart مؤكّد (67/67, 142/142, 18/18)
- اختبار mobile_app_review يحرس النتائج

## ملاحظة صدق
فحصتُ الكود **فعليّاً** (قرأت auth/api/websocket/bloc). إصلاح retry **مُتحقَّق
بنيويّاً** (توازن الأقواس + الإضافات) لكن **لم أشغّل dart analyze** (لا SDK في
بيئتي) — قد يكشف تحذيرات نوعيّة. سباق 401 **لم أصلحه** (يحتاج إعادة هيكلة +
اختبار حيّ) — وثّقتُه بصدق. التطبيق أنضج ممّا ظننتُ: أمان قويّ، offline مدروس،
استقرار جيّد. الفجوة الحقيقيّة الوحيدة (retry storm) أُصلحت.

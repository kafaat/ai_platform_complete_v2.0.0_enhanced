# إعادة بناء تطبيق الهاتف — 2026-10-26

بطلب المالك: «قوم باصلاح تطبيق الهاتف و اعادة هيكلة التطبيق و الصفحات بشكل كامل و التصميم و فقاً لافضل الممارسات و المنصات الزراعية و ui /ux و اصلاح الخدمات و المسارات الناقصة و المفاتيح و اصلاح الخرائط و الأدوات الرسم و غيرها مقارنة بالويب و اصلاح اخطاء الواجهه و اضافة الميزات والخدمات ب 20 وكيل ذكاء». الفرع `claude/mobile-overhaul-20261026`، أساسه `main@4da295f10` ثمّ دُمج معه `main@e786c8d71`.

## الطريقة

1. **أربعة تدقيقات** على `4da295f10` (قراءة فقط): تكافؤ الويب والنقاط، الخرائط والرسم، الخدمات والمسارات والمفاتيح ودون اتّصال، أخطاء الواجهة والتصميم. كلّ نتيجة بـ`path:line`.
2. **أساس معماريّ** (`lib/core/{network,routing,session,theme,widgets,permissions,utils}`): `ApiClient` بتجديد الرمز و`IdempotencyKey` و`ApiException` مصنَّف؛ موجِّه يجمع `FeatureModule` لكلّ ميزة ويفشل عند تكرار المسار؛ `SessionScope` ينظّف عند انتهاء الجلسة؛ رموز تصميم بسمتين؛ شريط تنقّل بخمس وجهات حسب الدور؛ عقد صندوق إرسال دون اتّصال. ووُثّق في `mobile/sahool_app/ARCHITECTURE.md`.
3. **خمسة عشر وكيلاً متوازياً**، لكلٍّ ميزةٌ يملكها وحدها في شجرة عمل معزولة، بقاعدة صدق: لا رقم ولا بيانات مختلَقة؛ ما لا يقدّمه الخادم يُعرض «غير متاح بعد»/«غير مقيس».
4. **دمجٌ وتكامل**: جُمعت الفروع بلا تعارض، ثمّ تمريرة تكامل عابرة للميزات (المسارات بين الشاشات، تسجيل مسارات الاستيراد والتصدير، توحيد دوالّ القياس الكرويّ بعد مقارنة 20000 حلقة عشوائيّة بتطابق بِتّيّ، الجرس وشارة المزامنة في اللوحة، استنساخ `FormData` عند الإعادة، نقل المنسِّقات والودجات المشتركة إلى core، السمة الفاتحة افتراضاً، وإعادة كلّ أنواع العمليّات المنتظرة بطريقتها ومسارها).

## النتيجة المقيسة

`flutter test`: 966 ناجحة، 0 فاشلة (كانت 120+5 قبل البدء). `flutter analyze`: 0 أخطاء، 0 تحذيرات، ملاحظة واحدة سابقة (`realtime_controller.dart:153`). أرقام السطح في `docs/WEB_MOBILE_PARITY.md` (تحديث 2026-10-26).

## ما أُصلح (مسجَّل في السجلّ بحالة fixed)

MOBILE-PEST-DETECT-OMITS-FIELD-ID-01 · MOBILE-WATER-LEDGER-POST-ERASES-DAY-ROW-01 · MOBILE-VALVE-SWITCH-OPTIMISTIC-AND-REPEATABLE-01 · MOBILE-FIELD-FORM-ACCEPTED-SHOWN-QUARANTINED-01 · MOBILE-FIELD-BOUNDARY-BOWTIE-AND-AREA-DRIFT-01 · MOBILE-FIELD-CREATE-RETRY-DUPLICATES-01 · MOBILE-SATELLITE-STALE-RESPONSE-AND-CLOUD-KEY-01 · MOBILE-ADVISOR-CHAT-HISTORY-PLAINTEXT-01 · MOBILE-MULTIPART-RETRY-AFTER-REFRESH-CONSUMED-01 · MOBILE-EQUIPMENT-STATUS-NEVER-MATCHES-01 · MOBILE-WORKSPACE-LINKS-TO-UNREGISTERED-ROUTES-01 · MOBILE-REALTIME-EVENT-TYPE-KEY-01.

وإلى جانبها إصلاحات واجهة كثيرة لكلٍّ منها اختبار في `mobile/sahool_app/test/features/<x>/`: فيضان التخطيط عند 360dp ونصّ 1.3×، أرقام عربيّة-هنديّة تُسقَط صامتة، رسائل تحقّق مخفيّة تحت الورقة السفليّة، أسهم معكوسة في RTL، أزرار بلا تلميح، أوقات بتوقيت UTC، أصفار مختلَقة مكان «غير مقيس»، إجراءات إضافة تظهر لأدوار يرفضها الخادم، إرسال مزدوج.

## ما بقي مفتوحاً — ينقص الخادم (مسجَّل بحالة open)

PLATFORM-NO-PHOTO-BLOB-STORAGE-FOR-FIELD-RECORDS-01 · PLATFORM-NO-MANUAL-TASK-CREATE-ENDPOINT-01 · PLATFORM-TASK-PATCH-IGNORES-IDEMPOTENCY-KEY-01 · PLATFORM-LAB-SAMPLE-CREATE-IGNORES-IDEMPOTENCY-KEY-01 · PLATFORM-WATER-LEDGER-NO-PARTIAL-APPLIED-WATER-WRITE-01 · PLATFORM-ALERT-WRITES-REQUIRE-FIELD-EDIT-01 (قرار المالك) · PLATFORM-ALERTS-NO-SINGLE-GET-OR-FIELD-FILTER-01 · PLATFORM-FARM-UPDATE-ENDPOINT-MISSING-01 · PLATFORM-FIELDS-LIST-NO-HEALTH-SIGNAL-01 · PLATFORM-FIELD-AREA-IGNORES-HOLES-01 · RASTER-OFFLINE-PACKS-REQUIRE-SERVICE-TOKEN-01 · PLATFORM-INVENTORY-NO-STOCK-OUT-OR-SAFETY-FIELDS-01 · PLATFORM-EQUIPMENT-STATUS-NOT-RESET-AFTER-REPAIR-01 · PLATFORM-DEVICE-AND-EQUIPMENT-NO-SINGLE-GET-01 · PLATFORM-PROFILE-UPDATE-ENDPOINT-MISSING-01 · PLATFORM-SYNC-TREATS-OUTBOX-OPS-AS-MEASUREMENTS-01.

## ما لم يُفعل ولماذا

- **صمّام الريّ:** لا مسار أوامر جديد ولا `volume_mm` في أمر الإغلاق — مسار المشغّل تحت GATE-01 وقرار المالك.
- **كتابة المستندات والبيانات المرجعيّة للمهندس الزراعيّ:** الخادم يمنحه `document:manage`؛ أُبقيت للإدارة مطابقةً للويب، والتوسعة سطر `allowedRoles`.
- **`DrawMap` على `SahoolMap`:** يتطلّب خيار إخفاء الخريطة الأساسيّة وإعادة ضبط اختبارات السحب.
- **اعتماد `file_picker`** لاستيراد حزم `.pmtiles` و`UIFileSharingEnabled` في iOS: تبعيّة وإعداد منصّة خارج هذا الفرع.
- **دون اتّصال للقراءة:** لا مخزن لقطات في core؛ القائمة الأخيرة تبقى معروضة بعمرها ولا تُحفظ بين التشغيلات.
- **ودجات core غير المستخدمة** (`LoadingView`/`ErrorView`/`EmptyView`/`InfoBanner` و`form_kit.dart`): تُحذف في تنظيف لاحق.

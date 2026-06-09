# المراجعة السابعة — التشديد التشغيلي (3 بنود مكتملة)

## ✅ البند ١: قفل الموافقات المتزامنة (منع double-approval)
المشكلة: approve كان SELECT ثمّ check status ثمّ UPDATE — موافقتان متزامنتان
تقرآن "pending" معاً وتمرّان.
الإصلاح (human_in_loop.py):
- approve + reject داخل conn.transaction() + SELECT ... FOR UPDATE (قفل صفّي)
- الموافقة الثانية تنتظر حتّى تُنهى الأولى ثمّ ترى الحالة المحدّثة
- منع موافقة الخبير نفسه مرّتين (idempotency على مستوى الخبير)
- reject أيضاً يفحص الحالة (لا رفض ما حُسم)

## ✅ البند ٢: معالج edge/sync مع dedup خادمي
- جديد: POST /api/v1/edge/sync (+ /v1/edge/sync)
- ON CONFLICT (idempotency_key) DO NOTHING → إعادة الإرسال بعد انقطاع
  الشبكة لا تُكرّر الصفّ. التكرار يُرجع "duplicate_ignored" (نجاح idempotent)
- migration: v9_edge_idempotency.sql (عمود + UNIQUE index جزئي)
- عبر tenant_connection (RLS) + الهويّة من التوكن (أمان)
- يُكمل idempotency العميل (مراجعة 7 السابقة): العميل يولّد المفتاح،
  الخادم الآن يكشف التكرار. الحلقة مكتملة.

## ✅ البند ٣: اختبارات الفشل/الصمود (chaos)
جديد: tests_v9/test_chaos_resilience.py — 11 فحص:
- sync replay dedup (مفاتيح مميّزة، صيغة ثابتة)
- concurrent approval guard (FOR UPDATE + منع تكرار الخبير + فحص الحالة)
- edge handler dedup (ON CONFLICT، idempotent، RLS)
- corrupt payload (validate_field_geometry يرفض الهندسة الفاسدة)
- fail-closed (actuator 503 بلا سرّ، RLS صفر صفوف بلا tenant، firmware يرفض
  بلا HMAC)

## التحقّق
- 361/361 اختبار · 332 ملفّ يُترجم · 11 فحص chaos ناجح
- البند ١: 3 مواضع FOR UPDATE · البند ٢: 2 ON CONFLICT · البند ٣: 11 فحص

## ملاحظة صدق
- locking مُتحقَّق منه بنيويّاً (الكود صحيح: transaction + FOR UPDATE). لم
  أشغّله ضدّ PostgreSQL حقيقي (لا DB في البيئة) — اختبر التزامن الفعلي بعد النشر.
- اختبارات chaos تتحقّق بنيويّاً (تفحص أنّ الحماية موجودة في الكود) +
  منطقيّاً (sync dedup يُشغَّل فعليّاً). chaos كامل (Redis/NATS/DB فشل حيّ)
  يحتاج بيئة بنية تحتيّة — هذه تغطّي منطق الصمود لا فشل البنية الحيّة.
- كلّ الإصلاحات تشديد لمكوّنات موجودة، لا طبقات جديدة (تجنّب التكرار).

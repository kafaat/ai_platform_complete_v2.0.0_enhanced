# المراجعة الثامنة — تدقيق وتنفيذ

مراجعة عميقة من زوايا جديدة. دقّقتُ كلّ ادّعاء. النتيجة: مزيج من اكتشاف
جديد حقيقي، ومُعالَج مسبقاً، وادّعاء غير دقيق.

## ✅ نُفّذ: #4 biometric stub (اكتشاف جديد حقيقي)
- authenticateWithBiometric() كان `return true` دائماً → تأكيد أمني زائف.
- لم يكن مُستدعى بعد (لا ضرر فعلي حاليّاً) لكنّه فخّ لأوّل مستدعٍ.
- الإصلاح: `return false` (fail-closed) + isBiometricAvailable=false (الواجهة
  تُخفي الخيار) + تعليق التنفيذ بـlocal_auth. لا تأكيد زائف بعد الآن.

## ✅ مُعالَج مسبقاً (الجلسة السابقة — مراجعة 7)
- **#6 idempotency**: نُفّذ — sync_service مفاتيح + edge/sync ON CONFLICT.
- **#2 transaction boundaries**: نُفّذ — approve/reject بـFOR UPDATE + معاملة.
  المراجعة 8 لم تكن تعلم أنّنا عالجناهما للتوّ.

## ❌ ادّعاء غير دقيق: #1 outbox pattern "غائب"
الواقع: outbox **موجود بالكامل** في event_bus.py + v11_events_bus.sql:
- emit_event SQL: INSERT events + INSERT outbox في **معاملة واحدة** (atomic)
- OutboxWorker: background task يقرأ outbox → NATS → mark sent
- UNIQUE dedup index على events (idempotency مدمج)
هذا outbox نموذجي — بالضبط ما تقول المراجعة إنّه ناقص. قرأت الكود جزئيّاً.

## ⚠️ دقيق لكنّه قرار معماري (لا إصلاح عابر): #5 shared JWT_SECRET
- صحيح: 8 خدمات تستخدم HS256 بنفس JWT_SECRET → shared trust domain.
  اختراق خدمة = تزوير tokens للباقي.
- لكنّ الحلّ (RS256 غير متماثل + per-service audience + scoped tokens) تغيير
  معماري واسع: إعادة توليد مفاتيح، تعديل المُصدِر (auth) وكلّ متحقّق، توزيع
  المفتاح العامّ. **قرارك** — لا أطبّقه تخمينيّاً (يكسر المصادقة لو أخطأت خطوة).
- تخفيف حالي: JWT_SECRET fail-closed (يُرفَض إن <32 حرف) + يجب تدويره.

## ⚠️ دقيق لكنّه قرار/بنية: البقيّة
- **#3 JSON ديناميكي**: صحيح جزئيّاً — Pydantic في المداخل، dict.get داخليّاً.
  تشديد تدريجي (إضافة موديلات) يستحقّ، لكن واسع — بنداً بنداً عند طلبك.
- **#7 raster reproducibility**: صحيح — geometry يُفحَص، لكن tile provenance/
  version pinning ناقص. ميزة GIS كبيرة تحتاج تصميماً.
- **#8 source-of-truth ambiguity**: ملاحظة معماريّة وجيهة (lifecycle/journal/
  replay/events قد تمثّل نفس الحقيقة). تستحقّ توثيقاً يحدّد المرجع النهائي
  لكلّ نوع — مهمّة تنظيميّة، قرارك.
- **#10 تعقيد ميتا-معماري**: ملاحظة نموّ صحيحة، لا إصلاح كود.

## ✅ نقطة قوّة أكّدتها المراجعة: #9 fail-closed
defensive design (JWT فارغ→503، RLS صفر صفوف، firmware يرفض، biometric→false
الآن) — أكّدت المراجعة أنّه أفضل من المتوقّع.

## التحقّق
- 361/361 · biometric fail-closed · لا كسر

## ملاحظة صدق
- نفّذتُ الاكتشاف الجديد الحقيقي الوحيد القابل للإصلاح الفوري (biometric).
- #1 غير دقيق (outbox موجود) — لم أبنِ مكرّراً.
- #5 وبقيّة البنود قرارات معماريّة، لا إصلاحات. ادّعاء تنفيذها عابراً سيكون
  غير أمين ويخاطر بكسر العامل. حدّدتُها بوضوح لقرارك.
